from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nexus.contracts.claim_evidence_read_model import validate_claim_evidence_read_model
from nexus.contracts.optimization_report import ClaimClass, ProviderTokenCleanliness


PUBLICATION_READINESS_GATE_SCHEMA = "nexus.publication_readiness_gate.v1"


@dataclass(frozen=True)
class PublicationReadinessInput:
    benchmark_summary: Mapping[str, Any]
    read_model: Mapping[str, Any]


def build_publication_readiness_gate(
    benchmark_summary: Mapping[str, Any],
    read_model: Mapping[str, Any],
) -> dict[str, Any]:
    blockers = _benchmark_blockers(benchmark_summary)
    blockers.extend(_read_model_blockers(read_model))
    blockers = sorted(set(blockers))
    return {
        "schema": PUBLICATION_READINESS_GATE_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "publication_ready": not blockers,
        "public_benchmark_allowed": not blockers,
        "runtime_update_allowed": False,
        "blockers": blockers,
        "benchmark_summary": dict(benchmark_summary),
        "read_model_summary": _read_model_summary(read_model),
        "claim_boundary": [
            "Publication readiness requires same-model paired public evidence, hidden verifier, sealed evidence, and a PUBLIC_READY read model.",
            "It does not apply runtime policy or replace the raw benchmark bundle.",
        ],
    }


def _benchmark_blockers(summary: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not bool(summary.get("same_model", False)):
        blockers.append("same_model_required")
    if not bool(summary.get("paired_comparison", False)):
        blockers.append("paired_comparison_required")
    if not bool(summary.get("taskset_frozen", False)):
        blockers.append("frozen_taskset_required")
    if not bool(summary.get("hidden_verifier_mode", False)):
        blockers.append("hidden_verifier_required")
    if not bool(summary.get("public_claim_gate_pass", False)):
        blockers.append("public_claim_gate_not_pass")
    if not bool(summary.get("wearing_evidence_valid", False)):
        blockers.append("wearing_evidence_not_valid")
    if not bool(summary.get("evidence_bundle_sealed", False)):
        blockers.append("evidence_bundle_not_sealed")
    if not bool(summary.get("evidence_hash_valid", False)):
        blockers.append("evidence_hash_not_valid")
    if str(summary.get("completion_envelope_status") or "NOT_APPLICABLE").upper() not in {"PASS", "NOT_APPLICABLE"}:
        blockers.append("completion_envelope_not_pass")
    if _number(summary.get("eligible_without_n")) <= 0:
        blockers.append("eligible_without_rows_required")
    if _number(summary.get("eligible_with_n")) <= 0:
        blockers.append("eligible_with_rows_required")
    if _number(summary.get("infra_invalid_without_n")) > 0 or _number(summary.get("infra_invalid_with_n")) > 0:
        blockers.append("infra_invalid_rows_present")
    if _number(summary.get("trust_mismatch_with_rate")) > 0 and not bool(summary.get("trust_mismatch_explained", False)):
        blockers.append("trust_mismatch_unexplained")
    token_cleanliness = str(summary.get("provider_token_cleanliness") or ProviderTokenCleanliness.NOT_APPLICABLE.value)
    if token_cleanliness not in {ProviderTokenCleanliness.MEASURED.value, ProviderTokenCleanliness.NOT_APPLICABLE.value}:
        blockers.append("provider_tokens_not_public_clean")
    return blockers


def _read_model_blockers(read_model: Mapping[str, Any]) -> list[str]:
    blockers = [f"read_model:{item}" for item in validate_claim_evidence_read_model(read_model)]
    if str(read_model.get("status") or "RETURN") != "PASS":
        blockers.append("read_model:not_pass")
    if str(read_model.get("claim_class") or "") != ClaimClass.PUBLIC_READY.value:
        blockers.append("read_model:public_ready_claim_class_required")
    if bool(read_model.get("runtime_update_allowed", False)):
        blockers.append("read_model:runtime_update_attempt")
    if bool(read_model.get("public_benchmark_allowed", False)):
        blockers.append("read_model:public_benchmark_unlock_attempt")
    return blockers


def _read_model_summary(read_model: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": str(read_model.get("status") or "RETURN"),
        "claim_class": str(read_model.get("claim_class") or ""),
        "provider_token_cleanliness": str(read_model.get("provider_token_cleanliness") or ""),
        "gate_count": len(read_model.get("gates", []) or []),
        "evidence_bundle_ref_count": len(read_model.get("evidence_bundle_refs", []) or []),
        "receipt_ref_count": len(read_model.get("receipt_refs", []) or []),
    }


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
