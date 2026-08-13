from datetime import datetime, timedelta, timezone

import pytest

from nexus.contracts.operator_outcome_receipt import (
    build_operator_outcome_receipt,
    validate_operator_outcome_receipt,
)


def _receipt(**overrides):
    values = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "lifecycle_revision": "life-1",
        "source_revision": "a" * 40,
        "runtime_receipt_hash": "b" * 64,
        "observed_outcome": "SUCCESS",
        "observation_basis": "OPERATOR_REPORT",
        "reason_code": "OPERATOR_CONFIRMED",
        "idempotency_key": "idem-1",
        "field_provenance": {
            field: {"provenance": "operator", "source_ref": "authenticated-submission"}
            for field in (
                "observed_outcome",
                "observation_basis",
                "reason_code",
                "observed_at",
                "source_revision",
                "runtime_receipt_hash",
            )
        },
    }
    values.update(overrides)
    return build_operator_outcome_receipt(**values)


def test_receipt_is_hashed_and_strict():
    receipt = _receipt()
    assert len(receipt.receipt_id) == 64
    with pytest.raises(ValueError, match="PAYLOAD_HASH"):
        type(receipt).model_validate(
            {**receipt.model_dump(mode="json"), "observed_outcome": "FAILURE"}
        )
    with pytest.raises(ValueError):
        type(receipt).model_validate({**receipt.model_dump(mode="json"), "free_text": "no"})


def test_receipt_binds_identity_and_freshness():
    receipt = _receipt()
    assert (
        validate_operator_outcome_receipt(
            receipt,
            task_id="task-1",
            attempt_id="attempt-1",
            action_id="action-1",
            lifecycle_revision="life-1",
            source_revision="a" * 40,
            runtime_receipt_hash="b" * 64,
        )
        == receipt
    )
    with pytest.raises(ValueError, match="ATTEMPT_ID"):
        validate_operator_outcome_receipt(receipt, attempt_id="other")
    stale = _receipt(observed_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    with pytest.raises(ValueError, match="STALE"):
        validate_operator_outcome_receipt(stale)


def test_receipt_rejects_free_text_hash_substitutes_and_invalid_supersession():
    with pytest.raises(ValueError, match="SOURCE_REVISION"):
        _receipt(source_revision="source-text")
    with pytest.raises(ValueError, match="HASH_INVALID"):
        _receipt(runtime_receipt_hash="runtime-text")
    with pytest.raises(ValueError, match="HASH"):
        _receipt(supersedes_receipt_id="not-a-hash")


def test_receipt_settled_schema_enums_and_provenance_are_strict():
    receipt = _receipt(
        observed_outcome="NOT_OBSERVED",
        observation_basis="NOT_OBSERVED",
        reason_code="NOT_PROVIDED",
        source_revision=None,
        runtime_receipt_hash=None,
    )
    assert receipt.recorded_at.tzinfo is not None
    with pytest.raises(ValueError, match="observed_outcome"):
        _receipt(observed_outcome="CANCELLED")
    with pytest.raises(ValueError, match="observation_basis"):
        _receipt(observation_basis="free text")
    with pytest.raises(ValueError, match="REASON"):
        _receipt(reason_code="arbitrary free text")
    with pytest.raises(ValueError):
        _receipt(field_provenance={"observed_outcome": {"provenance": "operator", "secret": "no"}})
    with pytest.raises(ValueError, match="RECORDED_BEFORE_OBSERVED"):
        _receipt(
            observed_at=datetime.now(timezone.utc),
            recorded_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    future_recorded = _receipt(recorded_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    with pytest.raises(ValueError, match="STALE"):
        validate_operator_outcome_receipt(future_recorded)
