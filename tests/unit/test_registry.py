import asyncio
import time
from typing import TYPE_CHECKING, cast

import pytest

from agent_review.collectors.base import (
    AbstractCollector,
    CollectorContext,
    CollectorResult,
    CollectorStatus,
)
from agent_review.collectors.registry import CollectorRegistry
from agent_review.schemas.classification import Classification
from agent_review.schemas.policy import CollectorPolicyConfig, PolicyConfig, ProfilePolicyConfig

if TYPE_CHECKING:
    from agent_review.scm.github_client import GitHubClient


class SleepCollector(AbstractCollector):
    name = "sleep"

    def __init__(self, collector_name: str, delay: float, status: CollectorStatus = "success"):
        self._collector_name = collector_name
        self._delay = delay
        self._status = status
        self.calls = 0

    async def collect(self, context: CollectorContext) -> CollectorResult:
        _ = context
        self.calls += 1
        await asyncio.sleep(self._delay)
        return CollectorResult(
            collector_name=self._collector_name,
            status=self._status,
            raw_findings=[],
            duration_ms=int(self._delay * 1000),
        )


class FlakyCollector(AbstractCollector):
    name = "flaky"

    def __init__(self):
        self.calls = 0

    async def collect(self, context: CollectorContext) -> CollectorResult:
        _ = context
        self.calls += 1
        status: CollectorStatus = "failure" if self.calls == 1 else "success"
        return CollectorResult(
            collector_name=self.name,
            status=status,
            raw_findings=[],
            duration_ms=1,
        )


def _context() -> CollectorContext:
    return CollectorContext(
        repo="o/r",
        pr_number=1,
        head_sha="a" * 40,
        base_sha="b" * 40,
        changed_files=["src/main.py"],
        github_client=cast("GitHubClient", object()),
    )


def _classification(profiles: list[str]) -> Classification:
    return Classification(
        change_type="code",
        domains=[],
        risk_level="low",
        profiles=profiles,
        file_categories={},
    )


@pytest.mark.asyncio
async def test_all_registered_collectors_run() -> None:
    semgrep = SleepCollector("semgrep", 0)
    secrets = SleepCollector("secrets", 0)
    extra = SleepCollector("extra", 0)
    registry = CollectorRegistry({"semgrep": semgrep, "secrets": secrets, "extra": extra})
    policy = PolicyConfig()

    _ = await registry.run_collectors(_classification([]), _context(), policy)

    assert semgrep.calls == 1
    assert secrets.calls == 1
    assert extra.calls == 1


@pytest.mark.asyncio
async def test_profile_require_checks_adds_missing_collectors() -> None:
    semgrep = SleepCollector("semgrep", 0)
    secrets = SleepCollector("secrets", 0)
    github_ci = SleepCollector("github_ci", 0)
    registry = CollectorRegistry({"semgrep": semgrep, "secrets": secrets, "github_ci": github_ci})
    policy = PolicyConfig(
        profiles={"core_quality": ProfilePolicyConfig(require_checks=["github_ci"])},
    )

    _ = await registry.run_collectors(_classification(["core_quality"]), _context(), policy)

    assert semgrep.calls == 1
    assert secrets.calls == 1
    assert github_ci.calls == 1


@pytest.mark.asyncio
async def test_parallel_execution_wall_clock_close_to_max() -> None:
    semgrep = SleepCollector("semgrep", 0.2)
    secrets = SleepCollector("secrets", 0.2)
    github_ci = SleepCollector("github_ci", 0.2)
    registry = CollectorRegistry({"semgrep": semgrep, "secrets": secrets, "github_ci": github_ci})
    policy = PolicyConfig(
        profiles={"core_quality": ProfilePolicyConfig(require_checks=["github_ci"])},
    )

    start = time.perf_counter()
    _ = await registry.run_collectors(_classification(["core_quality"]), _context(), policy)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.45


@pytest.mark.asyncio
async def test_timeout_handling() -> None:
    semgrep = SleepCollector("semgrep", 0.2)
    secrets = SleepCollector("secrets", 0)
    registry = CollectorRegistry({"semgrep": semgrep, "secrets": secrets})
    policy = PolicyConfig(
        collectors={"semgrep": CollectorPolicyConfig(timeout_seconds=0, retries=0)},
    )

    results = await registry.run_collectors(_classification([]), _context(), policy)
    statuses = {result.collector_name: result.status for result in results}

    assert statuses["semgrep"] == "timeout"
    assert statuses["secrets"] == "success"


@pytest.mark.asyncio
async def test_retry_logic_fail_then_succeed() -> None:
    semgrep = SleepCollector("semgrep", 0)
    secrets = SleepCollector("secrets", 0)
    flaky = FlakyCollector()
    registry = CollectorRegistry({"semgrep": semgrep, "secrets": secrets, "flaky": flaky})
    policy = PolicyConfig(
        collectors={"flaky": CollectorPolicyConfig(retries=1, timeout_seconds=1)},
    )

    results = await registry.run_collectors(_classification(["core_quality"]), _context(), policy)
    statuses = {result.collector_name: result.status for result in results}

    assert statuses["flaky"] == "success"
    assert flaky.calls == 2
