from __future__ import annotations

from nexus.contracts.optimization_report import ClaimClass, ProviderTokenCleanliness
from nexus.contracts.publication_readiness import build_publication_readiness_gate


def _benchmark(**overrides):
    payload = {
        "same_model": True,
        "paired_comparison": True,
        "taskset_frozen": True,
        "hidden_verifier_mode": True,
        "public_claim_gate_pass": True,
        "wearing_evidence_valid": True,
        "evidence_bundle_sealed": True,
        "evidence_hash_valid": True,
        "completion_envelope_status": "PASS",
        "eligible_without_n": 12,
        "eligible_with_n": 12,
        "infra_invalid_without_n": 0,
        "infra_invalid_with_n": 0,
        "trust_mismatch_with_rate": 0,
        "provider_token_cleanliness": ProviderTokenCleanliness.MEASURED.value,
    }
    payload.update(overrides)
    return payload


def _read_model(**overrides):
    payload = {
        "status": "PASS",
        "claim_class": ClaimClass.PUBLIC_READY.value,
        "provider_token_cleanliness": ProviderTokenCleanliness.MEASURED.value,
        "sealed_evidence_required": True,
        "evidence_bundle_refs": ["docs/reports/evidence_bundle.json"],
        "receipt_refs": ["docs/reports/receipt.json"],
        "records": [{"evidence_seal_status": "PASS", "evidence_hash_status": "PASS"}],
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "gates": [
            {"name": "delivery", "status": "PASS"},
            {"name": "trust", "status": "PASS"},
            {"name": "artifact", "status": "PASS"},
            {"name": "receipt", "status": "PASS"},
            {"name": "claim", "status": "PASS"},
        ],
    }
    payload.update(overrides)
    return payload


def test_publication_readiness_passes_complete_public_evidence() -> None:
    gate = build_publication_readiness_gate(_benchmark(), _read_model())

    assert gate["status"] == "PASS"
    assert gate["publication_ready"] is True
    assert gate["public_benchmark_allowed"] is True
    assert gate["runtime_update_allowed"] is False
    assert gate["blockers"] == []


def test_publication_readiness_blocks_internal_or_single_arm_evidence() -> None:
    gate = build_publication_readiness_gate(
        _benchmark(paired_comparison=False, hidden_verifier_mode=False),
        _read_model(claim_class=ClaimClass.RUNTIME_APPLY_REVIEW.value),
    )

    assert gate["status"] == "RETURN"
    assert gate["publication_ready"] is False
    assert "paired_comparison_required" in gate["blockers"]
    assert "hidden_verifier_required" in gate["blockers"]
    assert "read_model:public_ready_claim_class_required" in gate["blockers"]


def test_publication_readiness_blocks_dirty_cost_or_unsealed_evidence() -> None:
    gate = build_publication_readiness_gate(
        _benchmark(provider_token_cleanliness=ProviderTokenCleanliness.MISSING.value, evidence_bundle_sealed=False),
        _read_model(records=[{"evidence_seal_status": "RETURN", "evidence_hash_status": "PASS"}]),
    )

    assert gate["status"] == "RETURN"
    assert "provider_tokens_not_public_clean" in gate["blockers"]
    assert "evidence_bundle_not_sealed" in gate["blockers"]
    assert "read_model:record_0:evidence_seal_not_pass" in gate["blockers"]
