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
        "lifecycle_revision": "life-1",
        "source_revision": "a" * 40,
        "runtime_identity": "b" * 64,
        "outcome": "SUCCESS",
        "idempotency_key": "idem-1",
    }
    values.update(overrides)
    return build_operator_outcome_receipt(**values)


def test_receipt_is_hashed_and_strict():
    receipt = _receipt()
    assert len(receipt.payload_hash) == 64
    with pytest.raises(ValueError, match="PAYLOAD_HASH"):
        type(receipt).model_validate({**receipt.model_dump(mode="json"), "outcome": "FAILURE"})
    with pytest.raises(ValueError):
        type(receipt).model_validate({**receipt.model_dump(mode="json"), "free_text": "no"})


def test_receipt_binds_identity_and_freshness():
    receipt = _receipt()
    assert (
        validate_operator_outcome_receipt(
            receipt,
            task_id="task-1",
            attempt_id="attempt-1",
            lifecycle_revision="life-1",
            source_revision="a" * 40,
            runtime_identity="b" * 64,
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
    with pytest.raises(ValueError, match="RUNTIME_IDENTITY"):
        _receipt(runtime_identity="runtime-text")
    with pytest.raises(ValueError, match="HASH"):
        _receipt(supersedes_receipt_hash="not-a-hash")
