from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any


class PipelineLogger:
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._entries: list[dict[str, Any]] = []
        self._stage_start: float | None = None
        self._current_stage: str | None = None

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def info(self, stage: str, msg: str, **details: Any) -> None:
        self._append("INFO", stage, msg, details)

    def warn(self, stage: str, msg: str, **details: Any) -> None:
        self._append("WARN", stage, msg, details)

    def error(self, stage: str, msg: str, **details: Any) -> None:
        self._append("ERROR", stage, msg, details)

    def debug(self, stage: str, msg: str, **details: Any) -> None:
        self._append("DEBUG", stage, msg, details)

    def stage_start(self, stage: str) -> None:
        self._current_stage = stage
        self._stage_start = time.perf_counter()
        self.info(stage, f"Stage {stage} started")

    def stage_end(self, stage: str, **details: Any) -> None:
        elapsed_ms = 0
        if self._stage_start is not None and self._current_stage == stage:
            elapsed_ms = int((time.perf_counter() - self._stage_start) * 1000)
        self.info(
            stage, f"Stage {stage} completed in {elapsed_ms}ms", elapsed_ms=elapsed_ms, **details
        )
        self._stage_start = None
        self._current_stage = None

    def _append(self, level: str, stage: str, msg: str, details: dict[str, Any]) -> None:
        entry: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "stage": stage,
            "level": level,
            "msg": msg,
        }
        if details:
            entry["details"] = {k: _safe_serialize(v) for k, v in details.items()}
        self._entries.append(entry)


def _safe_serialize(val: Any) -> Any:
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if isinstance(val, (list, tuple)):
        return [_safe_serialize(v) for v in val]
    if isinstance(val, dict):
        return {str(k): _safe_serialize(v) for k, v in val.items()}
    return str(val)
