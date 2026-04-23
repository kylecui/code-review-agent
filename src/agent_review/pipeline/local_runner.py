from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from agent_review.models import ReviewRun, ReviewState
from agent_review.observability import PipelineLogger, RunMetrics, get_logger
from agent_review.pipeline.analysis import AnalysisResult, run_analysis

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from agent_review.config import Settings

logger = get_logger(__name__)


class LocalBaselineRunner:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: httpx.AsyncClient,
    ):
        self._settings = settings
        self._session_factory = session_factory
        self._http_client = http_client

    async def run(self, run_id: str, local_path: str) -> AnalysisResult | None:
        metrics = RunMetrics(run_id=run_id)
        plog = PipelineLogger(run_id)
        started_total = time.perf_counter()
        run: ReviewRun | None = None
        try:
            async with self._session_factory() as db:
                run_uuid = uuid.UUID(run_id)
                run = await db.get(ReviewRun, run_uuid)
                if run is None or run.is_terminal:
                    return None

                plog.info("INIT", "Local pipeline started", local_path=local_path, repo=run.repo)

                result = await run_analysis(
                    run=run,
                    db=db,
                    settings=self._settings,
                    http_client=self._http_client,
                    github=None,
                    changed_files=[],
                    pr_labels=[],
                    metrics=metrics,
                    local_path=local_path,
                    plog=plog,
                )

                metrics.total_ms = int((time.perf_counter() - started_total) * 1000)
                plog.stage_start("PUBLISHING")
                run.transition(ReviewState.PUBLISHING)
                await db.commit()
                plog.stage_end("PUBLISHING")
                run.transition(ReviewState.COMPLETED)
                run.metrics = metrics.to_dict()
                run.run_logs = plog.entries
                plog.info("COMPLETED", "Pipeline completed", total_ms=metrics.total_ms)
                run.run_logs = plog.entries
                await db.commit()
                return result
        except Exception as exc:
            logger.error("local_baseline_pipeline_failed", run_id=run_id, error=str(exc))
            plog.error("FAILED", f"Pipeline failed: {exc}")
            if run is None:
                return None
            try:
                async with self._session_factory() as db:
                    run_in_db = await db.get(ReviewRun, run.id)
                    if run_in_db is None or run_in_db.is_terminal:
                        return None
                    metrics.total_ms = int((time.perf_counter() - started_total) * 1000)
                    run_in_db.transition(ReviewState.FAILED)
                    run_in_db.error = str(exc)[:1000]
                    run_in_db.metrics = metrics.to_dict()
                    run_in_db.run_logs = plog.entries
                    await db.commit()
            except Exception:
                pass
            return None
