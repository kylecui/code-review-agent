from __future__ import annotations

from agent_review.observability.metrics import RunMetrics


def test_run_metrics_to_dict_serialization() -> None:
    metrics = RunMetrics(
        run_id="run-1",
        classification_ms=10,
        collection_ms=20,
        normalization_ms=30,
        reasoning_ms=40,
        gate_ms=50,
        publishing_ms=60,
        total_ms=210,
        collector_metrics={"semgrep": {"status": "success", "duration_ms": 9}},
        finding_count=4,
        llm_cost_cents=1.25,
        verdict="pass",
        is_degraded=False,
    )

    serialized = metrics.to_dict()
    assert serialized["run_id"] == "run-1"
    assert serialized["classification_ms"] == 10
    assert serialized["collection_ms"] == 20
    assert serialized["collector_metrics"] == {"semgrep": {"status": "success", "duration_ms": 9}}
    assert serialized["llm_cost_cents"] == 1.25
    assert serialized["verdict"] == "pass"
    assert serialized["is_degraded"] is False
