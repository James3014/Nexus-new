from __future__ import annotations

import pytest

from nexus.contracts.evidence_dataset import (
    EvidenceDatasetRecord,
    build_evidence_dataset_manifest,
    evidence_record_from_benchmark_row,
    evidence_record_from_sf_smoke_case,
    validate_evidence_dataset_record,
)
from nexus.contracts.optimization_report import ClaimClass, ProviderTokenCleanliness


def _clean_receipt_chain() -> dict[str, bool]:
    return {
        "selected": True,
        "injected": True,
        "used": True,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
    }


def test_sf_smoke_case_becomes_runtime_apply_review_record() -> None:
    record = evidence_record_from_sf_smoke_case(
        {
            "capability": "artifact_gate",
            "expected_skill": "sf-systematic-artifact_gate-differential-review-461fbd0c",
            "runtime_final_receipt_chain": _clean_receipt_chain(),
            "blocking_skill_mount_violations": [],
            "status": "PASS",
        },
        source_path="docs/reports/sf-smoke.json",
    )

    payload = record.to_dict()
    assert payload["claim_class"] == ClaimClass.RUNTIME_APPLY_REVIEW.value
    assert payload["provider_token_cleanliness"] == ProviderTokenCleanliness.NOT_APPLICABLE.value
    assert payload["capability_outcome"] == "contributed"
    assert payload["skill_effect_status"] == "receipt_confirmed"
    assert payload["gate_status"]["selected"] == "PASS"
    assert payload["blockers"] == []


def test_sf_smoke_incomplete_runtime_chain_is_blocked() -> None:
    chain = _clean_receipt_chain()
    chain["used"] = False

    record = evidence_record_from_sf_smoke_case(
        {
            "capability": "artifact_gate",
            "expected_skill": "sf-systematic-artifact_gate-differential-review-461fbd0c",
            "runtime_final_receipt_chain": chain,
            "blocking_skill_mount_violations": [],
            "status": "PASS",
        },
        source_path="docs/reports/sf-smoke.json",
    )

    payload = record.to_dict()
    assert "runtime_receipt_chain_incomplete" in payload["blockers"]
    assert payload["capability_outcome"] == "not_confirmed"
    assert payload["skill_effect_status"] == "not_confirmed"
    assert payload["gate_status"]["used"] == "RETURN"


def test_benchmark_row_keeps_token_cleanliness_separate_from_outcome() -> None:
    record = evidence_record_from_benchmark_row(
        {
            "task_id": "flash-001",
            "capability": "repair_loop",
            "skill_id": "tdd",
            "status": "SUCCESS",
            "trust_mismatch": False,
            "modelcalls": 1,
            "totaltokens": None,
            "evidence_bundle_file": "artifacts/evidence.json",
            "receipt_file": "artifacts/receipt.json",
        },
        source_path="docs/reports/flash.json",
        claim_class=ClaimClass.INTERNAL_DIAGNOSTIC,
    )

    payload = record.to_dict()
    assert payload["provider_token_cleanliness"] == ProviderTokenCleanliness.MISSING.value
    assert payload["capability_outcome"] == "verified"
    assert payload["skill_effect_status"] == "candidate_effective"
    assert payload["gate_status"]["provider_token"] == ProviderTokenCleanliness.MISSING.value


def test_benchmark_row_uses_capability_receipts_as_receipt_ref() -> None:
    record = evidence_record_from_benchmark_row(
        {
            "task_id": "flash-001",
            "capability": "claim_gate",
            "status": "SUCCESS",
            "trust_mismatch": False,
            "modelcalls": 0,
            "evidence_record_file": "artifacts/evidence.json",
            "capability_receipts": [
                {
                    "name": "claim_gate",
                    "selected": True,
                    "invoked": True,
                    "evidence_present": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                }
            ],
        },
        source_path="docs/reports/flash.json",
        claim_class=ClaimClass.INTERNAL_DIAGNOSTIC,
    )

    assert record.to_dict()["receipt_refs"] == ["capability_receipts:flash-001"]


def test_manifest_counts_and_runtime_update_gate() -> None:
    record = evidence_record_from_sf_smoke_case(
        {
            "capability": "forecast_pregate",
            "expected_skill": "create-plan",
            "runtime_final_receipt_chain": _clean_receipt_chain(),
            "blocking_skill_mount_violations": [],
            "status": "PASS",
        },
        source_path="docs/reports/sf-smoke.json",
    )

    manifest = build_evidence_dataset_manifest(
        [record],
        source_path="docs/reports/sf-smoke.json",
        claim_class=ClaimClass.RUNTIME_APPLY_REVIEW,
    )

    assert manifest["record_count"] == 1
    assert manifest["runtime_update_allowed"] is True
    assert manifest["public_benchmark_allowed"] is False
    assert manifest["provider_token_cleanliness_counts"] == {
        ProviderTokenCleanliness.NOT_APPLICABLE.value: 1
    }


def test_public_ready_record_requires_evidence_refs() -> None:
    blockers = validate_evidence_dataset_record(
        {
            "record_id": "evidence:test",
            "source_path": "docs/reports/public.json",
            "task_id": "task-001",
            "capability": "research_control_plane",
            "claim_class": ClaimClass.PUBLIC_READY.value,
            "provider_token_cleanliness": ProviderTokenCleanliness.MEASURED.value,
            "evidence_refs": [],
        }
    )

    assert blockers == [
        "public_ready_requires_evidence_hash",
        "public_ready_requires_evidence_refs",
        "public_ready_requires_evidence_seal",
    ]


def test_public_ready_record_requires_sealed_hash_valid_evidence() -> None:
    blockers = validate_evidence_dataset_record(
        {
            "record_id": "evidence:test",
            "source_path": "docs/reports/public.json",
            "task_id": "task-001",
            "capability": "research_control_plane",
            "claim_class": ClaimClass.PUBLIC_READY.value,
            "provider_token_cleanliness": ProviderTokenCleanliness.MEASURED.value,
            "evidence_refs": ["docs/reports/public.json"],
            "evidence_seal_status": "RETURN",
            "evidence_hash_status": "PASS",
            "partial_telemetry_detected": True,
        }
    )

    assert blockers == [
        "partial_telemetry_detected",
        "public_ready_requires_evidence_seal",
    ]


def test_enum_inputs_are_accepted() -> None:
    record = EvidenceDatasetRecord(
        record_id="evidence:enum",
        source_path="docs/reports/internal.json",
        source_schema="unit",
        task_id="task-001",
        capability="repair_loop",
        skill_id="tdd",
        route_id="repair_loop",
        claim_class=ClaimClass.INTERNAL_DIAGNOSTIC,
        provider_token_cleanliness=ProviderTokenCleanliness.MEASURED,
        delivery_status="PASS",
        trust_status="PASS",
        capability_outcome="verified",
        skill_effect_status="candidate_effective",
        evidence_refs=("docs/reports/internal.json",),
    )

    manifest = build_evidence_dataset_manifest(
        [record],
        source_path="docs/reports/internal.json",
        claim_class=ClaimClass.INTERNAL_DIAGNOSTIC,
    )

    assert manifest["claim_class"] == ClaimClass.INTERNAL_DIAGNOSTIC.value


def test_invalid_claim_class_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid_claim_class"):
        EvidenceDatasetRecord(
            record_id="evidence:bad",
            source_path="docs/reports/internal.json",
            source_schema="unit",
            task_id="task-001",
            capability="repair_loop",
            skill_id="tdd",
            route_id="repair_loop",
            claim_class="not-a-claim",  # type: ignore[arg-type]
            provider_token_cleanliness=ProviderTokenCleanliness.MEASURED,
            delivery_status="PASS",
            trust_status="PASS",
            capability_outcome="verified",
            skill_effect_status="candidate_effective",
            evidence_refs=("docs/reports/internal.json",),
        )
