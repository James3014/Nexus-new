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


def test_asi_constraint_extractor_ignores_successful_low_step_noise():
    records = [
        ASIRecord(
            run_id=1,
            hypothesis="minor retry tweak",
            family="flow:retry_delay",
            metric=0.0,
            status="discard",
            evidence="local smoke failed",
            rollback_reason="timeout still races",
            trajectory_step_count=3,
        ),
        ASIRecord(
            run_id=2,
            hypothesis="another minor retry tweak",
            family="flow:retry_delay",
            metric=0.0,
            status="discard",
            evidence="local smoke failed again",
            rollback_reason="timeout still races",
            trajectory_step_count=4,
        ),
    ]

    out = ASIConstraintExtractor(min_failures=2).extract(records, task_id="task-websocket")

    assert out["constraints_count"] == 0
    assert out["constraints"] == []


def test_asi_constraint_extractor_orders_families_and_preserves_evidence_refs():
    records = [
        ASIRecord(
            run_id=3,
            hypothesis="third family first",
            family="flow:zeta",
            metric=0.0,
            status="discard",
            evidence="zeta evidence one",
            rollback_reason="same zeta",
        ),
        ASIRecord(
            run_id=1,
            hypothesis="alpha first",
            family="flow:alpha",
            metric=0.0,
            status="discard",
            evidence="alpha evidence one",
            rollback_reason="same alpha",
        ),
        ASIRecord(
            run_id=4,
            hypothesis="zeta second",
            family="flow:zeta",
            metric=0.0,
            status="discard",
            evidence="zeta evidence two",
            rollback_reason="same zeta",
        ),
        ASIRecord(
            run_id=2,
            hypothesis="alpha second",
            family="flow:alpha",
            metric=0.0,
            status="discard",
            evidence="alpha evidence two",
            rollback_reason="same alpha",
        ),
        ASIRecord(
            run_id=5,
            hypothesis="unknown step first",
            family="flow:unknown_steps",
            metric=0.0,
            status="discard",
            evidence="unknown evidence one",
            rollback_reason="same unknown",
            trajectory_step_count=0,
        ),
        ASIRecord(
            run_id=6,
            hypothesis="unknown step second",
            family="flow:unknown_steps",
            metric=0.0,
            status="discard",
            evidence="unknown evidence two",
            rollback_reason="same unknown",
            trajectory_step_count=0,
        ),
        ASIRecord(
            run_id=7,
            hypothesis="low step first",
            family="flow:low_step",
            metric=0.0,
            status="discard",
            evidence="low evidence one",
            rollback_reason="low step",
            trajectory_step_count=1,
        ),
        ASIRecord(
            run_id=8,
            hypothesis="low step second",
            family="flow:low_step",
            metric=0.0,
            status="discard",
            evidence="low evidence two",
            rollback_reason="low step",
            trajectory_step_count=2,
        ),
    ]

    out = ASIConstraintExtractor(min_failures=2).extract(records, task_id="task-ordered")

    assert [item["blocked_pattern"] for item in out["constraints"]] == [
        "flow:alpha",
        "flow:unknown_steps",
        "flow:zeta",
    ]
    assert out["constraints"][0]["confidence"] == 0.75
    assert out["constraints"][0]["evidence_refs"] == ["alpha evidence one", "alpha evidence two"]
    assert out["constraints"][1]["source_run_ids"] == [5, 6]
    assert "flow:low_step" not in {item["blocked_pattern"] for item in out["constraints"]}


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
