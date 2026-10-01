import hashlib
import json

import pytest

from nexus.core.task_continuity import (
    ContinuityEvent,
    build_rehydration_projection,
    events_from_attempt_records,
    project,
    resume,
)
from nexus.events.contracts import MAX_CONTINUITY_COLLECTION_ITEMS


def event(sequence, kind, previous="", **kwargs):
    source_revision = kwargs.pop("source_revision", "src-a")
    contract_revision = kwargs.pop("contract_revision", "contract-a")
    return ContinuityEvent(
        task_id="task-1",
        attempt_id="attempt-1",
        sequence=sequence,
        event_type=kind,
        summary=kwargs.pop("summary", kind),
        previous_hash=previous,
        source_revision=source_revision,
        contract_revision=contract_revision,
        **kwargs,
    )


def test_projection_preserves_rejected_strategy_and_next_action():
    first = event(1, "PLAN_FORMED", next_action="try B", claim_ceiling="evidence only")
    second = event(
        2,
        "ATTEMPT_REJECTED",
        first.event_hash,
        summary="A failed",
        do_not_repeat=("A",),
        evidence_refs=("ev-1",),
        unresolved_risks=("risk-1",),
        unknowns=("unknown-1",),
        next_action="try B",
        claim_ceiling="evidence only",
    )
    snapshot = project([first, second])
    assert snapshot.rejected_strategies == ("A",)
    assert snapshot.evidence_refs == ("ev-1",)
    assert snapshot.unresolved_risks == ("risk-1",)
    assert snapshot.unknowns == ("unknown-1",)
    assert (
        resume(
            snapshot,
            [],
            task_id="task-1",
            attempt_id="attempt-1",
            source_revision="src-a",
            contract_revision="contract-a",
        ).next_action
        == "try B"
    )


def test_snapshot_tail_matches_projection():
    first = event(1, "PLAN_FORMED", next_action="try A", claim_ceiling="bounded")
    second = event(
        2,
        "ATTEMPT_REJECTED",
        first.event_hash,
        summary="A failed",
        do_not_repeat=("A",),
        next_action="try B",
        claim_ceiling="bounded",
    )
    third = event(
        3,
        "OBSERVATION_RECORDED",
        second.event_hash,
        observation="B observed",
        next_action="finish",
        claim_ceiling="bounded",
    )
    assert resume(
        project([first, second]),
        [third],
        task_id="task-1",
        attempt_id="attempt-1",
        source_revision="src-a",
        contract_revision="contract-a",
    ).snapshot == project([first, second, third])


def test_snapshot_tail_preserves_and_deduplicates_risks():
    first = event(
        1,
        "PLAN_FORMED",
        unresolved_risks=("risk-1",),
        next_action="try A",
        claim_ceiling="bounded",
    )
    second = event(
        2,
        "OBSERVATION_RECORDED",
        first.event_hash,
        unresolved_risks=("risk-1", "risk-2"),
        next_action="finish",
        claim_ceiling="bounded",
    )
    resumed = resume(
        project([first]),
        [second],
        task_id="task-1",
        attempt_id="attempt-1",
        source_revision="src-a",
        contract_revision="contract-a",
    )
    assert resumed.unresolved_risks == ("risk-1", "risk-2")


@pytest.mark.parametrize("field", ["source_revision", "contract_revision"])
def test_resume_rejects_tail_revision_drift(field):
    first = event(1, "PLAN_FORMED")
    tail = event(2, "OBSERVATION_RECORDED", first.event_hash, observation="x", **{field: "forged"})
    with pytest.raises(ValueError, match="revision drift"):
        resume(
            project([first]),
            [tail],
            task_id="task-1",
            attempt_id="attempt-1",
            source_revision="src-a",
            contract_revision="contract-a",
        )


def test_project_empty_stream_fails_closed():
    with pytest.raises(ValueError, match="event stream is empty"):
        project([])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"task_id": "other"},
        {"attempt_id": "other"},
    ],
)
def test_resume_fails_closed_on_identity_or_hash(kwargs):
    first = event(1, "PLAN_FORMED", next_action="try A", claim_ceiling="bounded")
    snapshot = project([first])
    with pytest.raises(ValueError):
        resume(
            snapshot,
            [],
            task_id=kwargs.get("task_id", "task-1"),
            attempt_id=kwargs.get("attempt_id", "attempt-1"),
            source_revision="src-a",
            contract_revision="contract-a",
            snapshot_hash="tampered",
        )


def test_sequence_gap_and_tamper_fail_closed():
    first = event(1, "PLAN_FORMED", next_action="try A", claim_ceiling="bounded")
    with pytest.raises(ValueError, match="sequence gap"):
        project([first, event(3, "OBSERVATION_RECORDED", first.event_hash, observation="x")])
    with pytest.raises(ValueError, match="tail"):
        resume(
            project([first]),
            [event(3, "OBSERVATION_RECORDED", first.event_hash, observation="x")],
            task_id="task-1",
            attempt_id="attempt-1",
            source_revision="src-a",
            contract_revision="contract-a",
        )


def test_empty_revision_is_rejected():
    with pytest.raises(ValueError):
        event(1, "PLAN_FORMED", source_revision="")


def test_forged_snapshot_is_rejected_without_optional_hash():
    first = event(1, "PLAN_FORMED", next_action="try A", claim_ceiling="bounded")
    snapshot = project([first])
    object.__setattr__(snapshot, "claim_ceiling", "forged")
    with pytest.raises(ValueError, match="snapshot tampered"):
        resume(
            snapshot,
            [],
            task_id="task-1",
            attempt_id="attempt-1",
            source_revision="src-a",
            contract_revision="contract-a",
        )


def test_canonical_attempt_records_are_consumed_after_record_validation():
    record = {
        "event_type": "attempt_transition",
        "payload": {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "state": "RUNNING",
            "source_revision": "src-a",
            "contract_revision": "contract-a",
            "evidence_refs": ["ev-1"],
        },
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    events = events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")
    assert project(events).evidence_refs == ("ev-1",)


def test_canonical_attempt_records_round_trip_protected_continuity_fields():
    record = {
        "event_type": "attempt_transition",
        "payload": {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "state": "REJECTED",
            "continuity_event_type": "ATTEMPT_REJECTED",
            "reason": "provider rejected",
            "strategy_delta": "switch provider",
            "do_not_repeat": ["provider-a"],
            "evidence_refs": ["ev-1"],
            "unresolved_risks": ["risk-1"],
            "unknowns": ["unknown-1"],
            "next_action": "try provider-b",
            "claim_ceiling": "evidence-only",
            "source_revision": "src-a",
            "contract_revision": "contract-a",
        },
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    decoded = events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")
    assert decoded[0].event_type == "ATTEMPT_REJECTED"
    assert decoded[0].do_not_repeat == ("provider-a",)
    snapshot = project(decoded)
    assert snapshot.rejected_strategies == ("provider-a",)
    assert snapshot.strategy_changes == ("switch provider",)
    assert snapshot.next_action == "try provider-b"
    assert snapshot.claim_ceiling == "evidence-only"


def test_rejected_attempt_without_explicit_continuity_type_fails_closed():
    record = {
        "event_type": "attempt_transition",
        "payload": {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "state": "ATTEMPT_REJECTED",
            "source_revision": "src-a",
            "contract_revision": "contract-a",
        },
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="rejected continuity event type"):
        events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")


def test_rejected_lifecycle_state_without_type_fails_closed():
    record = {
        "event_type": "attempt_transition",
        "payload": {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "state": "REJECTED",
            "source_revision": "src-a",
            "contract_revision": "contract-a",
        },
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="rejected continuity event type"):
        events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")


def test_rejected_lifecycle_state_with_observation_type_fails_closed():
    record = {
        "event_type": "attempt_transition",
        "payload": {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "state": "REJECTED",
            "continuity_event_type": "OBSERVATION_RECORDED",
            "source_revision": "src-a",
            "contract_revision": "contract-a",
        },
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="rejected state requires ATTEMPT_REJECTED"):
        events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")


def test_canonical_attempt_records_persist_failure_reason_through_replay():
    record = {
        "event_type": "attempt_transition",
        "payload": {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "state": "REJECTED",
            "continuity_event_type": "ATTEMPT_REJECTED",
            "reason": "provider rejected",
            "do_not_repeat": ["provider-a"],
            "evidence_refs": ["ev-1"],
            "unresolved_risks": ["risk-1"],
            "unknowns": ["unknown-1"],
            "next_action": "try provider-b",
            "claim_ceiling": "evidence-only",
            "source_revision": "src-a",
            "contract_revision": "contract-a",
        },
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    decoded = events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")
    assert decoded[0].failure_reason == "provider rejected"
    snapshot = project(decoded)
    assert snapshot.failure_reason == "provider rejected"
    context = resume(
        snapshot,
        [],
        task_id="task-1",
        attempt_id="attempt-1",
        source_revision="src-a",
        contract_revision="contract-a",
    )
    assert context.failure_reason == "provider rejected"


@pytest.mark.parametrize(
    "field,value",
    [
        ("do_not_repeat", {"a": 1}),
        ("unresolved_risks", {"a": 1}),
        ("unknowns", {"a": 1}),
    ],
)
def test_canonical_attempt_records_reject_malformed_continuity_lists(field, value):
    record = {
        "event_type": "attempt_transition",
        "payload": {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "state": "RUNNING",
            "source_revision": "src-a",
            "contract_revision": "contract-a",
        },
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    record["payload"][field] = value
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match=f"{field} must be a list"):
        events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", 7),
        ("state", ""),
        ("source_revision", 7),
        ("source_revision", ""),
        ("contract_revision", 7),
        ("contract_revision", ""),
    ],
)
def test_canonical_attempt_records_reject_malformed_continuity_fields(field, value):
    record = {
        "event_type": "attempt_transition",
        "payload": {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "sequence": 1,
            "state": "RUNNING",
            "source_revision": "src-a",
            "contract_revision": "contract-a",
        },
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    record["payload"][field] = value
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    with pytest.raises(ValueError):
        events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")


def _signed_record(payload):
    record = {
        "event_type": "attempt_transition",
        "payload": payload,
        "_attempt_parent_digest": "0" * 64,
        "_attempt_record_digest": "",
    }
    unsigned = dict(record)
    unsigned.pop("_attempt_record_digest")
    record["_attempt_record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return record


def _base_payload(**overrides):
    payload = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "sequence": 1,
        "state": "RUNNING",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
    }
    payload.update(overrides)
    return payload


def test_attempt_records_keep_failure_reason_out_of_observation_facts():
    record = _signed_record(
        _base_payload(
            state="REJECTED",
            continuity_event_type="ATTEMPT_REJECTED",
            reason="provider rejected",
            observation="provider-a latency observed",
        )
    )
    decoded = events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")
    assert decoded[0].failure_reason == "provider rejected"
    assert decoded[0].observation == "provider-a latency observed"
    snapshot = project(decoded)
    assert snapshot.verified_facts == ("provider-a latency observed",)
    assert "provider rejected" not in snapshot.verified_facts
    assert snapshot.failure_reason == "provider rejected"
    context = resume(
        snapshot,
        [],
        task_id="task-1",
        attempt_id="attempt-1",
        source_revision="src-a",
        contract_revision="contract-a",
    )
    assert context.failure_reason == "provider rejected"
    assert context.snapshot.verified_facts == ("provider-a latency observed",)


def test_attempt_records_reason_alone_does_not_become_an_observation():
    record = _signed_record(
        _base_payload(
            state="REJECTED",
            continuity_event_type="ATTEMPT_REJECTED",
            reason="provider rejected",
        )
    )
    decoded = events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")
    assert decoded[0].failure_reason == "provider rejected"
    assert decoded[0].observation == ""
    snapshot = project(decoded)
    assert snapshot.verified_facts == ()
    assert snapshot.failure_reason == "provider rejected"


@pytest.mark.parametrize(
    "field",
    ["do_not_repeat", "evidence_refs", "unresolved_risks", "unknowns"],
)
def test_attempt_records_reject_scalar_string_continuity_fields(field):
    record = _signed_record(_base_payload(**{field: "provider-a"}))
    with pytest.raises(ValueError, match=f"{field} must be a list"):
        events_from_attempt_records([record], task_id="task-1", attempt_id="attempt-1")


def test_attempt_records_enforce_bounded_collection_ceiling():
    over = _signed_record(
        _base_payload(do_not_repeat=["x"] * (MAX_CONTINUITY_COLLECTION_ITEMS + 1))
    )
    with pytest.raises(ValueError, match="exceeds bounded size"):
        events_from_attempt_records([over], task_id="task-1", attempt_id="attempt-1")
    boundary = _signed_record(_base_payload(do_not_repeat=["x"] * MAX_CONTINUITY_COLLECTION_ITEMS))
    decoded = events_from_attempt_records([boundary], task_id="task-1", attempt_id="attempt-1")
    assert decoded[0].do_not_repeat == ("x",) * MAX_CONTINUITY_COLLECTION_ITEMS


def test_continuity_event_rejects_over_limit_collection_and_accepts_boundary():
    with pytest.raises(ValueError, match="exceeds bounded size"):
        event(1, "PLAN_FORMED", do_not_repeat=("x",) * (MAX_CONTINUITY_COLLECTION_ITEMS + 1))
    bounded = event(1, "PLAN_FORMED", do_not_repeat=("x",) * MAX_CONTINUITY_COLLECTION_ITEMS)
    assert len(bounded.do_not_repeat) == MAX_CONTINUITY_COLLECTION_ITEMS


def test_build_rehydration_projection_basic_join():
    ev1 = event(1, "PLAN_FORMED", next_action="step-1", claim_ceiling="evidence only")
    ev2 = event(
        2,
        "ATTEMPT_REJECTED",
        ev1.event_hash,
        summary="A failed",
        do_not_repeat=("strategy-a",),
        evidence_refs=("ev-1",),
        unresolved_risks=("risk-1",),
        unknowns=("unknown-1",),
        next_action="step-2",
        claim_ceiling="evidence only",
    )
    snapshot = project([ev1, ev2])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "lifecycle_revision": "life-1",
        "candidate_commit_sha": "sha-c1",
        "claim_ceiling": "evidence only",
        "work_claim": {
            "claim_id": "claim-1",
            "generation": 1,
            "fencing_token": "claim-1:1",
            "status": "CLAIMED",
            "claimed_at": "2026-08-18T00:00:00Z",
            "identity": {
                "task_id": "task-1",
                "attempt_id": "attempt-1",
                "source_hash": "src-a",
            },
        },
    }
    task_action = {
        "action_state": "FINAL_BLOCK",
        "next_action": "step-2",
    }
    proj = build_rehydration_projection(
        task_state=task_state,
        continuity_snapshot=snapshot,
        task_action_envelope=task_action,
    )
    data = proj.to_dict()
    assert data["schema"] == "nexus.task_rehydration_projection.v1"
    assert data["task_identity"] == {"task_id": "task-1", "attempt_id": "attempt-1"}
    assert data["revision_binding"] == {
        "source_revision": "src-a",
        "contract_revision": "contract-a",
    }
    assert data["continuation"]["rejected_strategies"] == ["strategy-a"]
    assert data["continuation"]["do_not_repeat"] == ["strategy-a"]
    assert data["continuation"]["next_action"] == "step-2"
    assert data["continuation"]["evidence_refs"] == ["ev-1"]
    assert data["candidate_binding"]["candidate_commit_sha"] == "sha-c1"
    assert data["work_claim_binding"]["claim_id"] == "claim-1"
    assert "completed_actions" in data["missing_durable_bindings"]
    assert "verified_observations" in data["missing_durable_bindings"]
    assert "phase_receipts" in data["missing_durable_bindings"]


def test_build_rehydration_projection_missing_facts_stay_missing():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
    }
    proj = build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)
    data = proj.to_dict()
    assert "completed_actions" in data["missing_durable_bindings"]
    assert "verified_observations" in data["missing_durable_bindings"]
    assert "authority_revision" in data["missing_durable_bindings"]
    assert "phase_receipts" in data["missing_durable_bindings"]
    assert data["candidate_binding"] is None
    assert data["work_claim_binding"] is None


def test_build_rehydration_projection_task_mismatch_fails_closed():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-other",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
    }
    with pytest.raises(ValueError, match="REHYDRATION_TASK_MISMATCH"):
        build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)


def test_build_rehydration_projection_attempt_mismatch_fails_closed():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
    }
    with pytest.raises(ValueError, match="REHYDRATION_ATTEMPT_MISMATCH"):
        build_rehydration_projection(
            task_state=task_state,
            continuity_snapshot=snapshot,
            requested_attempt_id="attempt-other",
        )


def test_build_rehydration_projection_source_revision_mismatch_fails_closed():
    ev = event(1, "PLAN_FORMED", source_revision="src-1")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-2",
        "contract_revision": "contract-a",
    }
    with pytest.raises(ValueError, match="REHYDRATION_SOURCE_REVISION_MISMATCH"):
        build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)


def test_build_rehydration_projection_contract_revision_mismatch_fails_closed():
    ev = event(1, "PLAN_FORMED", contract_revision="contract-1")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-2",
    }
    with pytest.raises(ValueError, match="REHYDRATION_CONTRACT_REVISION_MISMATCH"):
        build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)


def test_build_rehydration_projection_work_claim_mismatch_fails_closed():
    ev = event(1, "PLAN_FORMED", source_revision="src-a")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "work_claim": {
            "claim_id": "claim-1",
            "generation": 1,
            "fencing_token": "claim-1:1",
            "identity": {
                "task_id": "task-1",
                "attempt_id": "attempt-foreign",
                "source_hash": "src-a",
            },
        },
    }
    with pytest.raises(ValueError, match="REHYDRATION_WORK_CLAIM_MISMATCH"):
        build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)


def test_build_rehydration_projection_authority_revision_never_inferred_from_lifecycle_revision():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "lifecycle_revision": "lifecycle-rev-1",
    }
    proj = build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)
    data = proj.to_dict()
    assert data["authority_binding"]["lifecycle_revision"] == "lifecycle-rev-1"
    assert "authority_revision" in data["missing_durable_bindings"]


@pytest.mark.parametrize(
    ("key", "val", "expected_match"),
    [
        ("candidate", "malformed", "REHYDRATION_MALFORMED_STATE"),
        ("promotion_packet", "malformed", "REHYDRATION_MALFORMED_STATE"),
        ("verified_receipt", "malformed", "REHYDRATION_MALFORMED_STATE"),
        ("contract", "malformed", "REHYDRATION_MALFORMED_STATE"),
        ("work_claim", "malformed", "REHYDRATION_WORK_CLAIM_MISMATCH"),
    ],
)
def test_build_rehydration_projection_malformed_durable_objects_fail_closed(
    key, val, expected_match
):
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        key: val,
    }
    with pytest.raises(ValueError, match=expected_match):
        build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)


def test_build_rehydration_projection_malformed_work_claim_identity_fails_closed():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "work_claim": {
            "claim_id": "claim-1",
            "generation": 1,
            "fencing_token": "claim-1:1",
            "identity": "malformed_not_a_dict",
        },
    }
    with pytest.raises(ValueError, match="REHYDRATION_WORK_CLAIM_MISMATCH"):
        build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)


def test_build_rehydration_projection_unrelated_evidence_refs_do_not_falsely_fail_receipt():
    unrelated_hash = "b" * 64
    ev = event(1, "PLAN_FORMED", evidence_refs=(unrelated_hash,))
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "verified_receipt_hash": "a" * 64,
    }
    proj = build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)
    data = proj.to_dict()
    assert data["candidate_binding"]["verified_receipt_hash"] == "a" * 64


def test_rehydration_no_completed_actions_does_not_invent_them():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "completed_actions": ["free_standing_action_not_in_continuity"],
    }
    proj = build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)
    data = proj.to_dict()
    assert "completed_actions" not in data["continuation"]
    assert "completed_actions" in data["missing_durable_bindings"]


def test_rehydration_no_verified_observations_does_not_invent_them():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "verified_observations": ["free_standing_obs_not_in_continuity"],
    }
    proj = build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)
    data = proj.to_dict()
    assert "verified_observations" not in data["continuation"]
    assert "verified_observations" in data["missing_durable_bindings"]


def test_rehydration_freestanding_task_state_actions_and_observations_rejected_without_continuity():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "completed_actions": ["unauthorized_action_1", "unauthorized_action_2"],
        "verified_observations": ["unauthorized_obs_1"],
    }
    proj = build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)
    data = proj.to_dict()
    assert "completed_actions" not in data["continuation"]
    assert "verified_observations" not in data["continuation"]
    assert "completed_actions" in data["missing_durable_bindings"]
    assert "verified_observations" in data["missing_durable_bindings"]


def test_rehydration_projects_authority_revision_and_phase_receipts_when_present():
    ev = event(1, "PLAN_FORMED")
    snapshot = project([ev])
    phase_receipt = {"phase": "A", "status": "SUCCESS", "authority_revision": "auth-1"}
    task_state = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_revision": "src-a",
        "contract_revision": "contract-a",
        "authority_revision": "auth-1",
        "phase_receipts": [phase_receipt],
    }
    proj = build_rehydration_projection(task_state=task_state, continuity_snapshot=snapshot)
    data = proj.to_dict()
    assert data["authority_binding"]["authority_revision"] == "auth-1"
    assert data["authority_binding"]["phase_receipts"] == [phase_receipt]
    assert "authority_revision" not in data["missing_durable_bindings"]
    assert "phase_receipts" not in data["missing_durable_bindings"]
