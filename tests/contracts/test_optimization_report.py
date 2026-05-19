import pytest

from nexus.contracts.optimization_report import (
    ClaimClass,
    ProviderTokenCleanliness,
    RetentionClass,
    build_optimization_report_contract,
    optimization_report_contract_from_payload,
    report_contract_readout,
    validate_optimization_report_contract,
)


def test_plan_only_report_contract_blocks_runtime_and_public_unlocks() -> None:
    payload = {
        "claim_class": "PLAN_ONLY",
        "retention_class": "keep_current_evidence",
        "claim_boundary": ["Architecture plan only; no runtime claim."],
        "runtime_update_allowed": True,
        "public_benchmark_allowed": True,
    }

    assert validate_optimization_report_contract(payload) == [
        "plan_only_must_not_unlock_runtime_or_public_benchmark",
        "public_benchmark_requires_public_ready_claim_class",
        "runtime_update_requires_runtime_apply_review_claim_class",
    ]
    assert report_contract_readout(payload)["status"] == "RETURN"


def test_sf_discovery_requires_evidence_and_never_updates_runtime() -> None:
    payload = {
        "claim_class": "SF_DISCOVERY",
        "retention_class": "keep_current_evidence",
        "claim_boundary": ["Skill comparison only."],
        "runtime_update_allowed": True,
        "public_benchmark_allowed": False,
    }

    assert validate_optimization_report_contract(payload) == [
        "missing_evidence_paths",
        "runtime_update_requires_runtime_apply_review_claim_class",
        "sf_discovery_must_not_update_runtime",
    ]


def test_runtime_apply_review_allows_runtime_update_with_receipts() -> None:
    contract = build_optimization_report_contract(
        claim_class=ClaimClass.RUNTIME_APPLY_REVIEW,
        retention_class=RetentionClass.PINNED_BY_CATALOG,
        claim_boundary=["Runtime apply review only; no public benchmark claim."],
        evidence_paths=["docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json"],
        runtime_update_allowed=True,
        public_benchmark_allowed=False,
        provider_token_cleanliness=ProviderTokenCleanliness.NOT_APPLICABLE,
    )

    assert validate_optimization_report_contract(contract) == []
    assert contract["runtime_update_allowed"] is True
    assert contract["public_benchmark_allowed"] is False
    round_trip = optimization_report_contract_from_payload(contract)
    assert round_trip.to_dict() == contract


def test_public_ready_requires_measured_tokens_or_not_applicable() -> None:
    payload = {
        "claim_class": "PUBLIC_READY",
        "retention_class": "keep_current_evidence",
        "claim_boundary": ["Public delivery/cost claim."],
        "evidence_paths": ["docs/reports/NEXUS_7R_BUNDLE.json"],
        "runtime_update_allowed": False,
        "public_benchmark_allowed": True,
        "provider_token_cleanliness": "missing",
    }

    assert validate_optimization_report_contract(payload) == [
        "public_ready_requires_measured_or_not_applicable_tokens"
    ]


def test_delete_candidate_is_never_valid_in_optimization_contract() -> None:
    payload = {
        "claim_class": "INTERNAL_DIAGNOSTIC",
        "retention_class": "delete_candidate",
        "claim_boundary": ["Dry-run retention only."],
    }

    assert validate_optimization_report_contract(payload) == [
        "delete_candidate_requires_explicit_separate_command"
    ]


def test_builder_rejects_missing_claim_boundary() -> None:
    with pytest.raises(ValueError, match="missing_claim_boundary"):
        build_optimization_report_contract(
            claim_class="INTERNAL_DIAGNOSTIC",
            retention_class="archive_candidate",
            claim_boundary=[],
        )
