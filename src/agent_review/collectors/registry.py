import asyncio

from agent_review.collectors.base import AbstractCollector, CollectorContext, CollectorResult
from agent_review.schemas.classification import Classification
from agent_review.schemas.policy import CollectorPolicyConfig, PolicyConfig


class CollectorRegistry:
    def __init__(self, collectors: dict[str, AbstractCollector]):
        self._collectors = collectors

    async def run_collectors(
        self,
        classification: Classification,
        context: CollectorContext,
        policy: PolicyConfig,
    ) -> list[CollectorResult]:
        effective = set(self._collectors.keys())
        for profile_name in classification.profiles:
            profile = policy.profiles.get(profile_name)
            if profile:
                effective.update(profile.require_checks)

        to_run = {name: self._collectors[name] for name in effective if name in self._collectors}

        task_policies: dict[str, CollectorPolicyConfig] = {}
        for name in to_run:
            task_policies[name] = policy.collectors.get(name, CollectorPolicyConfig())

        async def _run_single(
            name: str,
            collector: AbstractCollector,
            timeout: int,
            retries: int,
        ) -> CollectorResult:
            for attempt in range(retries + 1):
                try:
                    result = await asyncio.wait_for(collector.collect(context), timeout=timeout)
                    if result.status == "success" or attempt == retries:
                        return result
                except TimeoutError:
                    if attempt == retries:
                        return CollectorResult(
                            collector_name=name,
                            status="timeout",
                            raw_findings=[],
                            duration_ms=timeout * 1000,
                            error="Timeout",
                        )
            return CollectorResult(
                collector_name=name,
                status="failure",
                raw_findings=[],
                duration_ms=0,
                error="Unknown failure",
            )

        coroutines = [
            _run_single(
                name,
                collector,
                task_policies[name].timeout_seconds,
                task_policies[name].retries,
            )
            for name, collector in to_run.items()
        ]

        return list(await asyncio.gather(*coroutines))
