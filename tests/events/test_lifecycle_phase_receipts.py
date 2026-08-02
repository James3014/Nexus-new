from __future__ import annotations

import pytest

from nexus.events.contracts import PHASE_OBSERVER_HOOKS, build_phase_observer_event
from nexus.engine.phase_handshake import build_phase_receipt, validate_phase_receipt


def test_phase_observer_hook_vocabulary_is_symmetric():
    expected = {
        "on_phase_start",
        "on_phase_end",
        "on_phase_fail",
        "on_phase_retry",
        "on_phase_block",
        "on_phase_cancel",
        "on_phase_timeout",
        "on_phase_reconcile",
        "on_task_terminal",
    }
    assert PHASE_OBSERVER_HOOKS == expected
    event = build_phase_observer_event(task_id="t1", phase="R", hook="on_phase_retry", payload={"attempt": 2})
    assert event.event_type == "lifecycle_hook"
    assert event.payload["hook"] == "on_phase_retry"
    assert event.payload["attempt"] == 2


def test_unknown_observer_hook_fails_closed_at_contract_boundary():
    with pytest.raises(ValueError, match="unknown_phase_observer_hook"):
        build_phase_observer_event(task_id="t1", phase="R", hook="auto_transition")


def test_phase_receipt_is_machine_readable_and_complete():
    receipt = build_phase_receipt(
        task_id="t1",
        attempt_id="a1",
        action_id="x1",
        phase="A",
        phase_attempt=1,
        input_payload={"patch": "before"},
        output_payload={"audit_success": True},
        authority_revision="rev-1",
        status="SUCCESS",
        transition="A:start->end",
        evidence_refs=["evidence:a1"],
        verifier_refs=["verifier:a1"],
        timeout_telemetry={"timed_out": False},
        next_action="crystallize",
    )
    validate_phase_receipt(receipt)
    assert len(receipt["input_hash"]) == 64
    assert receipt["evidence_refs"] == ["evidence:a1"]


def test_incomplete_phase_receipt_fails_closed():
    with pytest.raises(RuntimeError, match="PHASE_RECEIPT_INCOMPLETE"):
        validate_phase_receipt({"task_id": "t1"})
