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
        type(receipt).model_validate({
            **receipt.model_dump(mode="json"),
            "observed_outcome": "FAILURE",
        })
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


@pytest.mark.parametrize(
    ("observed_outcome", "observation_basis", "reason_code"),
    [
        ("SUCCESS", "NOT_OBSERVED", "NOT_PROVIDED"),
        ("NOT_OBSERVED", "OPERATOR_REPORT", "OPERATOR_CONFIRMED"),
        ("UNKNOWN", "NOT_OBSERVED", "NOT_PROVIDED"),
        ("NOT_OBSERVED", "NOT_OBSERVED", "OPERATOR_CONFIRMED"),
    ],
)
def test_receipt_rejects_cross_field_semantic_contradictions(
    observed_outcome, observation_basis, reason_code
):
    with pytest.raises(ValueError, match="SEMANTICS_INVALID"):
        _receipt(
            observed_outcome=observed_outcome,
            observation_basis=observation_basis,
            reason_code=reason_code,
        )


@pytest.mark.parametrize(
    ("observed_outcome", "observation_basis", "reason_code", "provenance"),
    [
        ("NOT_OBSERVED", "NOT_OBSERVED", "NOT_PROVIDED", "operator"),
        ("UNKNOWN", "OPERATOR_REPORT", "OUTCOME_UNKNOWN", "operator"),
        ("UNKNOWN", "SYSTEM_OBSERVATION", "OUTCOME_UNKNOWN", "system"),
    ],
)
def test_receipt_accepts_explicit_unknown_and_not_observed_semantics(
    observed_outcome, observation_basis, reason_code, provenance
):
    receipt = _receipt(
        observed_outcome=observed_outcome,
        observation_basis=observation_basis,
        reason_code=reason_code,
        field_provenance={
            field: {"provenance": provenance, "source_ref": "authenticated-submission"}
            for field in (
                "observed_outcome",
                "observation_basis",
                "reason_code",
                "observed_at",
                "source_revision",
                "runtime_receipt_hash",
            )
        },
    )
    assert receipt.observed_outcome == observed_outcome


@pytest.mark.parametrize(
    ("observed_outcome", "observation_basis", "reason_code", "provenance"),
    [
        ("SUCCESS", "OPERATOR_REPORT", "OPERATOR_CONFIRMED", "operator"),
        ("FAILURE", "OPERATOR_REPORT", "OPERATOR_CONFIRMED", "operator"),
        ("PARTIAL", "OPERATOR_REPORT", "REWORK_REQUIRED", "operator"),
        ("SUCCESS", "SYSTEM_OBSERVATION", "SYSTEM_RECORDED", "system"),
        ("FAILURE", "SYSTEM_OBSERVATION", "SYSTEM_RECORDED", "system"),
        ("PARTIAL", "SYSTEM_OBSERVATION", "SYSTEM_RECORDED", "system"),
    ],
)
def test_receipt_accepts_ordinary_outcome_basis_reason_and_provenance_matrix(
    observed_outcome, observation_basis, reason_code, provenance
):
    receipt = _receipt(
        observed_outcome=observed_outcome,
        observation_basis=observation_basis,
        reason_code=reason_code,
        field_provenance={
            field: {"provenance": provenance, "source_ref": "authenticated-submission"}
            for field in (
                "observed_outcome",
                "observation_basis",
                "reason_code",
                "observed_at",
                "source_revision",
                "runtime_receipt_hash",
            )
        },
    )
    assert receipt.observation_basis == observation_basis


@pytest.mark.parametrize(
    ("observed_outcome", "observation_basis", "reason_code", "provenance"),
    [
        ("SUCCESS", "SYSTEM_OBSERVATION", "OPERATOR_CONFIRMED", "system"),
        ("FAILURE", "OPERATOR_REPORT", "SYSTEM_RECORDED", "operator"),
        ("SUCCESS", "OPERATOR_REPORT", "REWORK_REQUIRED", "operator"),
        ("PARTIAL", "OPERATOR_REPORT", "OPERATOR_CONFIRMED", "operator"),
        ("SUCCESS", "OPERATOR_REPORT", "OPERATOR_CONFIRMED", "system"),
        ("FAILURE", "SYSTEM_OBSERVATION", "SYSTEM_RECORDED", "operator"),
    ],
)
def test_receipt_rejects_incompatible_outcome_basis_reason_or_provenance(
    observed_outcome, observation_basis, reason_code, provenance
):
    with pytest.raises(ValueError, match="SEMANTICS_INVALID"):
        _receipt(
            observed_outcome=observed_outcome,
            observation_basis=observation_basis,
            reason_code=reason_code,
            field_provenance={
                field: {
                    "provenance": provenance,
                    "source_ref": "authenticated-submission",
                }
                for field in (
                    "observed_outcome",
                    "observation_basis",
                    "reason_code",
                    "observed_at",
                    "source_revision",
                    "runtime_receipt_hash",
                )
            },
        )
