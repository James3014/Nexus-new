from __future__ import annotations

import pytest

from nexus.contracts.state_owner_transition import (
    ReceiptState,
    TransitionReceipt,
    TransitionSelection,
    TransitionValidationError,
    WriterTransitionRequest,
)


def _raw() -> dict:
    digest = "a" * 64
    return {
        "schema": "nexus.state_owner_transition_request.v1",
        "operation": "PREFLIGHT",
        "request_id": "r",
        "transaction_id": "t",
        "idempotency_key": "i",
        "task_id": "task",
        "card_path": "tasks/card.md",
        "card_sha256": digest,
        "expected_source_head": "b" * 40,
        "expected_source_tree": "c" * 40,
        "accepted_source_receipt": "accepted",
        "root_id": "root",
        "expected_root_identity": digest,
        "expected_owner_id": "owner",
        "expected_generation": None,
        "expected_writer_id": "old",
        "expected_manifest_sha256": None,
        "next_generation": 1,
        "next_writer_id": "new",
        "selections": [
            {
                "entry_id": "e",
                "role": "task_state",
                "relative_path": "state.json",
                "expected_sha256": digest,
                "size": 1,
            }
        ],
        "authority_receipt_id": "authority",
        "authority_receipt_hash": digest,
        "drain_receipt_id": "drain",
        "drain_receipt_hash": digest,
        "snapshot_receipt_id": "snapshot",
        "snapshot_receipt_hash": digest,
        "rollback_receipt_id": "rollback",
        "rollback_receipt_hash": digest,
        "loaded_writer_plan_id": "plan",
        "loaded_writer_plan_hash": digest,
    }


def test_closed_request_digest_is_stable():
    request = WriterTransitionRequest.from_mapping(_raw())
    assert len(request.request_digest) == 64
    assert (
        request.request_digest
        == WriterTransitionRequest.from_mapping(request.to_dict()).request_digest
    )


@pytest.mark.parametrize("field", ["unexpected", "authority_receipt_hash"])
def test_closed_or_invalid_request_rejected(field):
    raw = _raw()
    if field == "unexpected":
        raw[field] = True
    else:
        raw[field] = "bad"
    with pytest.raises(TransitionValidationError):
        WriterTransitionRequest.from_mapping(raw)


def test_selection_traversal_rejected():
    raw = _raw()
    raw["selections"][0]["relative_path"] = "../state.json"
    with pytest.raises(TransitionValidationError):
        WriterTransitionRequest.from_mapping(raw)


@pytest.mark.parametrize(
    ("role", "path"),
    [("unknown", "state.json"), ("task_state", "/state.json"), ("task_state", "a//b")],
)
def test_direct_selection_constructor_rejects_unowned_role_and_path(role, path):
    with pytest.raises(TransitionValidationError):
        TransitionSelection("entry", role, path, "a" * 64, 1)


def test_direct_request_constructor_rejects_untyped_selection_and_invalid_git_tree():
    raw = _raw()
    raw["expected_source_tree"] = "c" * 64
    with pytest.raises(TransitionValidationError):
        WriterTransitionRequest.from_mapping(raw)
    raw = _raw()
    raw["selections"] = (object(),)
    with pytest.raises(TransitionValidationError):
        WriterTransitionRequest(**raw)


def test_source_acceptance_hash_is_bound_in_request_digest():
    first = WriterTransitionRequest.from_mapping(_raw())
    raw = _raw()
    raw["accepted_source_receipt_hash"] = "f" * 64
    second = WriterTransitionRequest.from_mapping(raw)
    assert second.accepted_source_receipt_hash == "f" * 64
    assert first.request_digest != second.request_digest
    assert second.to_dict()["accepted_source_receipt_hash"] == "f" * 64


def test_claim_receipt_requires_full_authority_root_cas_and_collector_bindings():
    minimal = TransitionReceipt("a" * 64, "tx", ReceiptState.COMMITTED, True, False, False, False)
    with pytest.raises(TransitionValidationError, match="RECEIPT_FIELDS_INCOMPLETE"):
        minimal.require_claim_fields()

    full = TransitionReceipt(
        "a" * 64,
        "tx",
        ReceiptState.COMMITTED,
        True,
        False,
        False,
        False,
        task_id="task",
        card_path="tasks/card.md",
        card_sha256="b" * 64,
        source_head="c" * 40,
        source_tree="d" * 40,
        accepted_source_receipt="receipt",
        accepted_source_receipt_hash="0" * 64,
        authority_receipt_id="authority",
        authority_receipt_hash="e" * 64,
        authorization_intent_digest="f" * 64,
        grant_id="grant",
        grant_hash="1" * 64,
        effect_hash="2" * 64,
        root_id="root",
        expected_root_identity="3" * 64,
        expected_owner_id="owner",
        expected_generation=1,
        expected_writer_id="old",
        next_generation=2,
        next_writer_id="new",
        selection_digest="4" * 64,
        expected_manifest_sha256="5" * 64,
        observed_before_manifest_sha256="6" * 64,
        observed_after_manifest_sha256="7" * 64,
        drain_receipt_id="drain",
        drain_receipt_hash="8" * 64,
        snapshot_receipt_id="snapshot",
        snapshot_receipt_hash="9" * 64,
        rollback_receipt_id="rollback",
        rollback_receipt_hash="a" * 64,
        loaded_writer_plan_id="plan",
        loaded_writer_plan_hash="b" * 64,
    )
    payload = full.require_claim_fields()
    assert payload["schema"] == "nexus.state_owner_transition_receipt.v1"
    assert payload["receipt_digest"] == full.to_dict()["receipt_digest"]


def test_claim_receipt_allows_explicit_absent_initial_manifest_without_fake_hash():
    receipt = TransitionReceipt(
        "a" * 64,
        "tx-initial",
        ReceiptState.COMMITTED,
        True,
        False,
        False,
        False,
        task_id="task",
        card_path="tasks/card.md",
        card_sha256="b" * 64,
        source_head="c" * 40,
        source_tree="d" * 40,
        accepted_source_receipt="receipt",
        accepted_source_receipt_hash="0" * 64,
        authority_receipt_id="authority",
        authority_receipt_hash="e" * 64,
        authorization_intent_digest="f" * 64,
        grant_id="grant",
        grant_hash="1" * 64,
        effect_hash="2" * 64,
        root_id="root",
        expected_root_identity="3" * 64,
        expected_owner_id="owner",
        expected_generation=None,
        expected_writer_id="old",
        next_generation=1,
        next_writer_id="new",
        selection_digest="4" * 64,
        expected_manifest_sha256=None,
        observed_before_manifest_sha256=None,
        observed_after_manifest_sha256="5" * 64,
        before_manifest_present=False,
        drain_receipt_id="drain",
        drain_receipt_hash="6" * 64,
        snapshot_receipt_id="snapshot",
        snapshot_receipt_hash="7" * 64,
        rollback_receipt_id="rollback",
        rollback_receipt_hash="8" * 64,
        loaded_writer_plan_id="plan",
        loaded_writer_plan_hash="9" * 64,
    )
    assert receipt.require_claim_fields()["before_manifest_present"] is False
