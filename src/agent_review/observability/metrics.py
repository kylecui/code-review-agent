from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field


@dataclass
class RunMetrics:
    run_id: str
    started_at: float = field(default_factory=time.time)
    classification_ms: int = 0
    collection_ms: int = 0
    normalization_ms: int = 0
    reasoning_ms: int = 0
    gate_ms: int = 0
    publishing_ms: int = 0
    total_ms: int = 0
    collector_metrics: dict[str, dict[str, object]] = field(default_factory=dict)
    finding_count: int = 0
    llm_cost_cents: float = 0.0
    verdict: str = ""
    is_degraded: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
