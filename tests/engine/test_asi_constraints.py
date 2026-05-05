from nexus.engine.asi_constraints import ASIConstraintExtractor
from nexus.engine.pipeline_outcome import ASIRecord


def test_asi_constraint_extractor_crystallizes_repeated_failures():
    records = [
        ASIRecord(
            run_id=1,
            hypothesis="fix websocket timeout by tweaking retry delay",
            family="flow:retry_delay",
            metric=0.0,
            status="discard",
            evidence="pytest failed",
            rollback_reason="timeout still races",
        ),
        ASIRecord(
            run_id=2,
            hypothesis="fix websocket timeout with another retry delay",
            family="flow:retry_delay",
            metric=0.0,
            status="discard",
            evidence="pytest failed again",
            rollback_reason="timeout still races",
        ),
    ]

    out = ASIConstraintExtractor(min_failures=2).extract(records, task_id="task-websocket")

    assert out["schema"] == "nexus_asi_constraints_v1"
    assert out["constraints_count"] == 1
    constraint = out["constraints"][0]
    assert constraint["blocked_pattern"] == "flow:retry_delay"
    assert constraint["failure_signature"] == "timeout still races"
    assert constraint["source_task_ids"] == ["task-websocket"]
    assert constraint["confidence"] >= 0.7


def test_asi_constraint_extractor_ignores_single_failure_noise():
    records = [
        ASIRecord(
            run_id=1,
            hypothesis="one bad attempt",
            family="flow:local_patch",
            metric=0.0,
            status="discard",
            evidence="failed",
            rollback_reason="syntax error",
        )
    ]

    out = ASIConstraintExtractor(min_failures=2).extract(records, task_id="task-one")

    assert out["constraints_count"] == 0
    assert out["constraints"] == []
