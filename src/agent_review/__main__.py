"""CLI entry point for baseline repository scanning.

Usage:
    python -m agent_review scan --repo owner/name --installation-id 12345
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import TYPE_CHECKING

import httpx

from agent_review.config import Settings
from agent_review.database import create_engine, create_session_factory
from agent_review.models import ReviewRun, RunKind
from agent_review.pipeline.baseline_runner import BaselineRunner
from agent_review.scm.github_auth import GitHubAppAuth
from agent_review.scm.github_client import GitHubClient

if TYPE_CHECKING:
    from agent_review.pipeline.analysis import AnalysisResult


async def _resolve_head_sha(
    github: GitHubClient, repo: str, ref: str | None, branch: str | None
) -> str:
    if ref:
        return ref
    if branch:
        return await github.get_branch_sha(repo, branch)
    default_branch = await github.get_default_branch(repo)
    return await github.get_branch_sha(repo, default_branch)


async def _run_scan(
    *,
    repo: str,
    installation_id: int,
    branch: str | None,
    ref: str | None,
    config_path: str | None,
) -> AnalysisResult:
    settings = (
        Settings(_env_file=config_path) if config_path else Settings()  # type: ignore[call-arg]
    )

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    async with httpx.AsyncClient(timeout=120.0) as http_client:
        auth = GitHubAppAuth(
            settings.github_app_id,
            settings.github_private_key.get_secret_value(),
        )
        github = GitHubClient(http_client, auth, installation_id)

        head_sha = await _resolve_head_sha(github, repo, ref, branch)

        run = ReviewRun(
            id=uuid.uuid4(),
            repo=repo,
            run_kind=RunKind.BASELINE,
            pr_number=None,
            head_sha=head_sha,
            base_sha=None,
            installation_id=installation_id,
            trigger_event=None,
            delivery_id=None,
        )

        async with session_factory() as db:
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = str(run.id)

        runner = BaselineRunner(
            settings=settings,
            session_factory=session_factory,
            http_client=http_client,
        )
        result = await runner.run(run_id)

    await engine.dispose()

    if result is None:
        raise RuntimeError("Baseline scan returned no result")

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agent_review",
        description="Agent Review CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Run a baseline repository scan")
    scan_parser.add_argument(
        "--repo",
        required=True,
        help="Repository in owner/name format",
    )
    scan_parser.add_argument(
        "--installation-id",
        type=int,
        required=True,
        help="GitHub App installation ID",
    )
    scan_parser.add_argument(
        "--branch",
        default=None,
        help="Branch to scan (defaults to repo default branch)",
    )
    scan_parser.add_argument(
        "--ref",
        default=None,
        help="Exact commit SHA (takes precedence over --branch)",
    )
    scan_parser.add_argument(
        "--output",
        choices=["json", "github-issue"],
        default="json",
        help="Output format (default: json)",
    )
    scan_parser.add_argument(
        "--config",
        default=None,
        help="Path to .env file for Settings override",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command != "scan":
        parser.print_help()
        sys.exit(1)

    try:
        result = asyncio.run(
            _run_scan(
                repo=args.repo,
                installation_id=args.installation_id,
                branch=args.branch,
                ref=args.ref,
                config_path=args.config,
            )
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.output == "json":
        from agent_review.reporting.json_report import format_json_report

        report = format_json_report(result)
        print(json.dumps(report, indent=2, default=str))
    elif args.output == "github-issue":
        from agent_review.reporting.github_issue import publish_github_issue

        url = asyncio.run(
            publish_github_issue(
                result,
                repo=args.repo,
                installation_id=args.installation_id,
                config_path=args.config,
            )
        )
        print(url)

    sys.exit(0)


if __name__ == "__main__":
    main()
