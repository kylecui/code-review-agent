from typing import TYPE_CHECKING, Literal, cast

from agent_review.collectors.base import CollectorContext, CollectorResult

if TYPE_CHECKING:
    from agent_review.scm.github_client import GitHubClient


def test_collector_result_status_values() -> None:
    statuses: list[Literal["success", "failure", "timeout", "skipped"]] = [
        "success",
        "failure",
        "timeout",
        "skipped",
    ]

    results = [
        CollectorResult(
            collector_name="dummy",
            status=status,
            raw_findings=[],
            duration_ms=10,
        )
        for status in statuses
    ]

    assert [result.status for result in results] == statuses


def test_collector_context_construction() -> None:
    context = CollectorContext(
        repo="o/r",
        pr_number=7,
        head_sha="a" * 40,
        base_sha="b" * 40,
        changed_files=["src/a.py"],
        github_client=cast("GitHubClient", object()),
    )

    assert context.repo == "o/r"
    assert context.pr_number == 7
    assert context.changed_files == ["src/a.py"]
