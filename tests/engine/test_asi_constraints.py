from nexus.engine.asi_constraints import ASIConstraintExtractor, ASIConstraintStore
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


def test_asi_constraint_store_persists_and_matches_cross_task_constraints(tmp_path):
    constraint = {
        "schema": "nexus_asi_constraint_v1",
        "blocked_pattern": "flow:retry_delay",
        "failure_signature": "timeout still races",
        "preferred_pattern": "change_family_or_architecture_seam",
    }
    store = ASIConstraintStore(tmp_path)

    path = store.append_constraints([constraint, constraint])
    matches = store.match("Fix websocket timeout without another retry delay")

    assert path.endswith(".nexus/reports/asi/global_constraints.jsonl")
    assert len(store.load_constraints()) == 1
    assert matches[0]["blocked_pattern"] == "flow:retry_delay"

    receipt = store.lookup_receipt("Fix websocket timeout without another retry delay", matches=matches)
    assert receipt["schema"] == "nexus_asi_constraint_lookup_v1"
    assert receipt["matched_count"] == 1
    assert receipt["constraint_refs"]
    assert receipt["applied_blocked_patterns"] == ["flow:retry_delay"]
