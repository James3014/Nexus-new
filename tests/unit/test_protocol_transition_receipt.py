"""Tests for protocol_transition_receipt module."""

import pytest
from nexus.services.local_heal.protocol_transition_receipt import (
    create_receipt,
    to_dict,
    ProtocolTransitionReceipt,
)


def test_create_receipt():
    r = create_receipt(
        receipt_id="PTR_TEST",
        task_id="test_task",
        model="test_model",
        source_stage="advisor_v4_v5",
        old_path={"protocol": "old"},
        new_path={"protocol": "new"},
        comparison={"delta": "NEUTRAL"},
    )
    assert isinstance(r, ProtocolTransitionReceipt)
    assert r.receipt_id == "PTR_TEST"
    assert r.governance["dry_run_only"] is True
    assert r.governance["routing_changed"] is False


def test_to_dict():
    r = create_receipt(
        receipt_id="PTR_TEST",
        task_id="test_task",
        model="test_model",
        source_stage="advisor_v4_v5",
        old_path={"protocol": "old"},
        new_path={"protocol": "new"},
        comparison={"delta": "NEUTRAL"},
    )
    d = to_dict(r)
    assert isinstance(d, dict)
    assert d["schema"] == "nexus.protocol_transition_receipt.v0"
    assert d["receipt_id"] == "PTR_TEST"
    assert d["governance"]["m6_executed"] is False


def test_governance_enforced():
    r = create_receipt(
        receipt_id="PTR_TEST",
        task_id="test_task",
        model="test_model",
        source_stage="advisor_v4_v5",
        old_path={},
        new_path={},
        comparison={},
    )
    assert r.governance["training_export"] is False
    assert r.governance["public_claim_allowed"] is False
    assert r.governance["llm_calls"] is False
    assert r.governance["patch_apply"] is False
