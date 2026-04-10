from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_review.models import ReviewRun, ReviewState


async def supersede_active_runs(
    db: AsyncSession,
    repo: str,
    pr_number: int,
    current_head_sha: str,
) -> list[str]:
    result = await db.execute(
        select(ReviewRun).where(
            ReviewRun.repo == repo,
            ReviewRun.pr_number == pr_number,
            ReviewRun.head_sha != current_head_sha,
            ReviewRun.state.notin_(
                [
                    ReviewState.COMPLETED,
                    ReviewState.FAILED,
                    ReviewState.SUPERSEDED,
                ]
            ),
        )
    )
    superseded_ids: list[str] = []
    for run in result.scalars().all():
        run.transition(ReviewState.SUPERSEDED)
        superseded_ids.append(str(run.id))
    return superseded_ids
