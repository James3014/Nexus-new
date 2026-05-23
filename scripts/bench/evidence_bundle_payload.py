from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.bench.public_lane_contract import (
    build_external_provider_claim_boundary_contract,
    build_public_promotion_readiness_contract,
)


def _rate_for(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if bool(row.get(key, False))) / len(rows), 4)


def build_evidence_bundle_header_section(
    *,
    created_at_unix: int,
    run_identity: Mapping[str, Any],
    model_lock: Mapping[str, Any],
    task_manifest: Mapping[str, Any],
    taskset_contract: Mapping[str, Any],
    public_disclosure_manifest: Mapping[str, Any] | None,
    timeouts: Mapping[str, Any],
    config: Mapping[str, Any],
    raw_files: Mapping[str, Any],
    artifact_files: Mapping[str, Any],
    row_count: int,
    row_counts: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "nexus_public_benchmark_evidence_bundle_v2",
        "created_at_unix": created_at_unix,
        "run_identity": run_identity,
        "model_lock": model_lock,
        "task_manifest": task_manifest,
        "taskset_contract": taskset_contract,
        "public_disclosure_manifest": public_disclosure_manifest
        or {"path": "", "sha256": "", "status": "not_provided", "failures": []},
        "timeouts": timeouts,
        "config": config,
        "raw_files": raw_files,
        "artifact_files": artifact_files,
        "row_count": row_count,
        "row_counts": row_counts,
    }


def build_evidence_bundle_computed_sections(
    *,
    route_cost_ledger: Mapping[str, Any],
    route_cost_trace_report: Mapping[str, Any],
    commercial_model_roi_shadow_hooks: Mapping[str, Any],
    infra_quarantine_report: Mapping[str, Any],
    session_worker_contamination: Mapping[str, Any],
    outbound_prompt_ledger_summary: Mapping[str, Any],
    public_lane_contract: Mapping[str, Any],
    route_policy_evidence_contract: Mapping[str, Any],
    expected_capability_evidence_contract: Mapping[str, Any],
    skill_mount_evidence_contract: Mapping[str, Any],
    s2t_shadow_report: Mapping[str, Any],
    s2t_policy_draft: Mapping[str, Any],
    product_kpis: Mapping[str, Any],
    openseeker_kpis: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "route_cost_ledger": route_cost_ledger,
        "route_cost_trace_report": route_cost_trace_report,
        "commercial_model_roi_shadow_hooks": commercial_model_roi_shadow_hooks,
        "infra_quarantine_report": infra_quarantine_report,
        "session_worker_contamination": session_worker_contamination,
        "outbound_prompt_ledger_gate": outbound_prompt_ledger_summary,
        "public_lane_contract": public_lane_contract,
        "route_policy_evidence_contract": route_policy_evidence_contract,
        "expected_capability_evidence_contract": expected_capability_evidence_contract,
        "skill_mount_evidence_contract": skill_mount_evidence_contract,
        "s2t_shadow_report": s2t_shadow_report,
        "s2t_policy_draft": s2t_policy_draft,
        "product_kpis": product_kpis,
        "openseeker_alignment": openseeker_kpis,
    }


def build_evidence_bundle_claim_posture_sections(
    *,
    public_claim_gates: Mapping[str, Any],
    valid_comparison_readiness_gate: Mapping[str, Any],
    direction_magnitude_gate: Mapping[str, Any],
    x3_promotion_gate: Mapping[str, Any],
    mutation_hardening_gate: Mapping[str, Any],
    posture_finalization_gate: Mapping[str, Any],
    public_claim_posture: Mapping[str, Any],
    training_eligibility_posture: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **dict(public_claim_gates),
        "valid_comparison_readiness_gate": valid_comparison_readiness_gate,
        "direction_magnitude_gate": direction_magnitude_gate,
        "x3_promotion_gate": x3_promotion_gate,
        "mutation_hardening_gate": mutation_hardening_gate,
        "posture_finalization_gate": posture_finalization_gate,
        "public_claim_posture": public_claim_posture,
        "training_eligibility_posture": training_eligibility_posture,
    }


def build_evidence_bundle_payload(
    *,
    header_section: Mapping[str, Any],
    telemetry_completeness: Mapping[str, Any],
    rubric_contract: Mapping[str, Any],
    wall_ledger_conservation: Mapping[str, Any],
    warning_clean_gate: Mapping[str, Any],
    computed_sections: Mapping[str, Any],
    nexus_wearing: Mapping[str, Any],
    claim_posture_sections: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **dict(header_section),
        "telemetry_completeness": telemetry_completeness,
        "rubric_contract": rubric_contract,
        "wall_ledger_conservation": wall_ledger_conservation,
        "warning_clean_gate": warning_clean_gate,
        **dict(computed_sections),
        "nexus_wearing": nexus_wearing,
        **dict(claim_posture_sections),
    }


def build_telemetry_completeness_section(
    *,
    token_measured_rate_without: float,
    token_measured_rate_with: float,
    provider_token_measured_rate_without: float,
    provider_token_measured_rate_with: float,
    without_rows: Sequence[Mapping[str, Any]],
    with_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "token_measured_rate_without": token_measured_rate_without,
        "token_measured_rate_with": token_measured_rate_with,
        "provider_token_measured_rate_without": provider_token_measured_rate_without,
        "provider_token_measured_rate_with": provider_token_measured_rate_with,
        "gateway_stats_source_rate_without": _rate_for(without_rows, "gateway_stats_present"),
        "gateway_stats_source_rate_with": _rate_for(with_rows, "gateway_stats_present"),
    }


@dataclass(frozen=True)
class NexusWearingContext:
    nexus_valid_rate: float
    model_uses_nexus_rate: float
    legacy_gemini_uses_nexus_rate: float
    nexus_context_delivered_rate: float
    nexus_usage_valid_rate: float
    claim_verified_rate: float
    route_decision_present_rate: float
    local_reflex_verified_rate: float
    nexus_system_execution_valid_rate: float
    nexus_system_usage_valid_rate: float
    payload: dict[str, Any]


def _is_local_reflex_verified(row: Mapping[str, Any]) -> bool:
    return (
        bool(row.get("local_success_source"))
        and bool(row.get("semantic_completed"))
        and bool(row.get("hidden_verifier_passed", True))
        and not bool(row.get("report_trust_mismatch"))
        and bool(row.get("nexus_wearing_valid"))
        and bool(row.get("nexus_context_delivered"))
        and bool(row.get("capability_claim_verified"))
    )


def build_nexus_wearing_context(with_rows: Sequence[Mapping[str, Any]]) -> NexusWearingContext:
    nexus_valid_rate = _rate_for(with_rows, "nexus_wearing_valid")
    model_uses_nexus_rate = _rate_for(with_rows, "model_uses_nexus")
    legacy_gemini_uses_nexus_rate = _rate_for(with_rows, "gemini_uses_nexus")
    nexus_context_delivered_rate = _rate_for(with_rows, "nexus_context_delivered")
    nexus_usage_valid_rate = _rate_for(with_rows, "nexus_usage_valid")
    claim_verified_rate = _rate_for(with_rows, "capability_claim_verified")
    route_decision_present_rate = _rate_for(with_rows, "route_decision_schema_version")
    local_reflex_verified_count = sum(1 for row in with_rows if _is_local_reflex_verified(row))
    local_reflex_verified_rate = round(local_reflex_verified_count / len(with_rows), 4) if with_rows else 0.0
    nexus_system_execution_valid_rate = (
        round(
            sum(
                1
                for row in with_rows
                if bool(row.get("model_uses_nexus"))
                or bool(row.get("gemini_uses_nexus"))
                or _is_local_reflex_verified(row)
            )
            / len(with_rows),
            4,
        )
        if with_rows
        else 0.0
    )
    nexus_system_usage_valid_rate = (
        round(
            sum(1 for row in with_rows if bool(row.get("nexus_usage_valid")) or _is_local_reflex_verified(row))
            / len(with_rows),
            4,
        )
        if with_rows
        else 0.0
    )
    payload = {
        "valid_rate": nexus_valid_rate,
        "gemini_uses_nexus_rate": legacy_gemini_uses_nexus_rate,
        "model_uses_nexus_rate": model_uses_nexus_rate,
        "nexus_context_delivered_rate": nexus_context_delivered_rate,
        "nexus_usage_valid_rate": nexus_usage_valid_rate,
        "claim_verified_rate": claim_verified_rate,
    }
    return NexusWearingContext(
        nexus_valid_rate=nexus_valid_rate,
        model_uses_nexus_rate=model_uses_nexus_rate,
        legacy_gemini_uses_nexus_rate=legacy_gemini_uses_nexus_rate,
        nexus_context_delivered_rate=nexus_context_delivered_rate,
        nexus_usage_valid_rate=nexus_usage_valid_rate,
        claim_verified_rate=claim_verified_rate,
        route_decision_present_rate=route_decision_present_rate,
        local_reflex_verified_rate=local_reflex_verified_rate,
        nexus_system_execution_valid_rate=nexus_system_execution_valid_rate,
        nexus_system_usage_valid_rate=nexus_system_usage_valid_rate,
        payload=payload,
    )


def build_wall_ledger_conservation_section(
    *,
    wall_ledger_summary_with: Mapping[str, Any],
    wall_ledger_summary_without: Mapping[str, Any],
    wall_ledger_invalid: bool,
) -> dict[str, Any]:
    return {
        "schema": "nexus_wall_ledger_conservation_bundle_v1",
        "with_nexus": wall_ledger_summary_with,
        "without_nexus": wall_ledger_summary_without,
        "telemetry_invalid": wall_ledger_invalid,
        "claim_boundary": [
            "Telemetry-invalid wall ledger rows are excluded from cost-efficiency claims.",
            "A conserved ledger requires complete required components and reconciliation error below 5 percent.",
        ],
    }


def build_warning_clean_gate_section(
    *,
    warning_ledger_summary: Mapping[str, Any],
    warning_ledger_invalid: bool,
    warning_ledger_required: bool,
) -> dict[str, Any]:
    return {
        "schema": "nexus_warning_clean_gate_v1",
        "verdict": "PASS" if not warning_ledger_invalid else "RETURN",
        "required": warning_ledger_required,
        "checks": warning_ledger_summary,
        "claim_boundary": [
            "Public candidate runs require process-level warning capture.",
            "Warnings that are present but uncaptured or unclassified force RETURN.",
        ],
    }


def build_posture_finalization_gate_section(
    *,
    cost_efficiency_status: str,
    cost_efficiency_sample_sufficient: bool,
    valid_comparison_ready: bool,
    training_eligibility_posture: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "nexus_posture_finalization_gate_v1",
        "public_efficiency_wording_allowed": bool(
            cost_efficiency_status == "IMPROVED" and cost_efficiency_sample_sufficient and valid_comparison_ready
        ),
        "training_eligible_requires": [
            "non_regressed",
            "full_contracts",
            "telemetry_clean",
            "sample_sufficient",
        ],
        "current_training_status": training_eligibility_posture.get("status"),
    }


def summarize_rubric_contract_rows(source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not source_rows:
        return {
            "rows": 0,
            "overall_pass_rate": 0.0,
            "plan_pass_rate": 0.0,
            "evidence_pass_rate": 0.0,
            "delivery_pass_rate": 0.0,
            "cost_pass_rate": 0.0,
            "hard_fail_reasons": [],
        }

    def section_pass(row: dict[str, Any], section: str) -> bool:
        rubric = row.get("rubric_contract")
        rubric = rubric if isinstance(rubric, dict) else {}
        payload = rubric.get(section)
        payload = payload if isinstance(payload, dict) else {}
        return str(payload.get("status") or "") == "PASS"

    reasons: set[str] = set()
    for row in source_rows:
        for reason in row.get("rubric_contract_hard_fail_reasons", []) or []:
            text = str(reason).strip()
            if text:
                reasons.add(text)

    row_count = len(source_rows)
    return {
        "rows": row_count,
        "overall_pass_rate": round(
            sum(1 for row in source_rows if str(row.get("rubric_contract_status") or "") == "PASS") / row_count,
            4,
        ),
        "plan_pass_rate": round(sum(1 for row in source_rows if section_pass(row, "plan_rubric")) / row_count, 4),
        "evidence_pass_rate": round(
            sum(1 for row in source_rows if section_pass(row, "evidence_rubric")) / row_count,
            4,
        ),
        "delivery_pass_rate": round(
            sum(1 for row in source_rows if section_pass(row, "delivery_rubric")) / row_count,
            4,
        ),
        "cost_pass_rate": round(sum(1 for row in source_rows if section_pass(row, "cost_rubric")) / row_count, 4),
        "hard_fail_reasons": sorted(reasons),
    }


def build_rubric_contract_bundle(
    *,
    with_rows: list[dict[str, Any]],
    without_rows: list[dict[str, Any]],
    eligible_with: list[dict[str, Any]],
    eligible_without: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "nexus_rubric_contract_bundle_v1",
        "with_nexus": summarize_rubric_contract_rows(with_rows),
        "without_nexus": summarize_rubric_contract_rows(without_rows),
        "eligible_with_nexus": summarize_rubric_contract_rows(eligible_with),
        "eligible_without_nexus": summarize_rubric_contract_rows(eligible_without),
        "claim_boundary": [
            "Rubric PASS is required before public or training claims.",
            "Behavioral success with missing required artifacts remains observation-only.",
            "Cost efficiency wording requires cost rubric PASS plus sample sufficiency.",
        ],
    }


def finalize_evidence_bundle_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    finalized = dict(payload)
    finalized["external_provider_claim_boundary_contract"] = build_external_provider_claim_boundary_contract(finalized)
    finalized["public_promotion_readiness_contract"] = build_public_promotion_readiness_contract(finalized)
    return finalized


def write_evidence_bundle_payload(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
