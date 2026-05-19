from __future__ import annotations

from nexus.contracts.claim_evidence_read_model import (
    CLAIM_EVIDENCE_READ_MODEL_SCHEMA,
    build_claim_evidence_read_model,
    validate_claim_evidence_read_model,
)
from nexus.contracts.optimization_report import ClaimClass, ProviderTokenCleanliness


def _record(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "delivery_status": "PASS",
        "trust_status": "PASS",
        "provider_token_cleanliness": ProviderTokenCleanliness.NOT_APPLICABLE.value,
        "evidence_refs": ["docs/reports/evidence.json"],
        "receipt_refs": ["docs/reports/receipt.json"],
        "blockers": [],
    }
    payload.update(overrides)
    return payload


def test_runtime_apply_read_model_summarizes_gate_refs_without_mutating_runtime() -> None:
    payload = build_claim_evidence_read_model(
        claim_class=ClaimClass.RUNTIME_APPLY_REVIEW,
        records=[_record()],
        evidence_bundle_refs=["docs/reports/evidence.json"],
        receipt_refs=["docs/reports/receipt.json"],
    )

    assert payload["schema"] == CLAIM_EVIDENCE_READ_MODEL_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["runtime_update_allowed"] is False
    assert payload["public_benchmark_allowed"] is False
    assert payload["blockers"] == []
    assert {gate["name"]: gate["status"] for gate in payload["gates"]} == {
        "delivery": "PASS",
        "trust": "PASS",
        "artifact": "PASS",
        "receipt": "PASS",
        "claim": "PASS",
    }


def test_read_model_blocks_runtime_review_without_bundle_and_receipts() -> None:
    payload = build_claim_evidence_read_model(
        claim_class=ClaimClass.RUNTIME_APPLY_REVIEW,
        records=[_record(evidence_refs=[], receipt_refs=[])],
    )

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == [
        "artifact:gate_not_pass",
        "claim:gate_not_pass",
        "missing_evidence_bundle_refs",
        "missing_receipt_refs",
        "receipt:gate_not_pass",
    ]


def test_public_read_model_requires_clean_provider_tokens() -> None:
    payload = build_claim_evidence_read_model(
        claim_class=ClaimClass.PUBLIC_READY,
        records=[_record(provider_token_cleanliness=ProviderTokenCleanliness.MISSING.value)],
        evidence_bundle_refs=["docs/reports/evidence.json"],
        receipt_refs=["docs/reports/receipt.json"],
    )

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == ["public_ready_requires_measured_or_not_applicable_tokens"]


def test_validate_rejects_attempted_unlocks_from_read_model_payload() -> None:
    blockers = validate_claim_evidence_read_model(
        {
            "claim_class": ClaimClass.PUBLIC_READY.value,
            "provider_token_cleanliness": ProviderTokenCleanliness.MEASURED.value,
            "evidence_bundle_refs": ["docs/reports/evidence.json"],
            "receipt_refs": ["docs/reports/receipt.json"],
            "runtime_update_allowed": True,
            "public_benchmark_allowed": True,
            "gates": [{"name": "delivery", "status": "PASS"}],
        }
    )

    assert blockers == [
        "read_model_must_not_unlock_public_benchmark",
        "read_model_must_not_update_runtime",
    ]
