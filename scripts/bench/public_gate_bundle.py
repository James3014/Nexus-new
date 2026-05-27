from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CostEfficiencyDecision:
    status: str
    failures: list[str]


def derive_cost_efficiency_decision(
    *,
    delivery_gate_passed: bool,
    delivery_gate_failures: list[str],
    cost_gate_failures: list[str],
    wall_cost_ratio_with_over_without: float,
    token_cost_ratio_with_over_without: float,
    model_call_ratio_with_over_without: float,
    retry_cost_share_wall: float,
    retry_cost_share_tokens: float,
    wall_ledger_invalid: bool,
    warning_ledger_invalid: bool,
    valid_comparison_ready: bool,
    exclusion_candidate: bool = False,
    exclusion_reason_code: str = "",
    exclusion_provenance: str = "",
) -> CostEfficiencyDecision:
    failures: list[str] = []
    if not delivery_gate_passed:
        failures.extend(delivery_gate_failures)
    if cost_gate_failures:
        failures.extend(cost_gate_failures)
        
    allow_wall_exclusion = False
    if exclusion_candidate:
        if exclusion_provenance == "gateway_timeout" and exclusion_reason_code == "network_timeout_exceeded":
            allow_wall_exclusion = True
        elif exclusion_provenance == "background_replay_lane" and exclusion_reason_code == "background_offload_active":
            allow_wall_exclusion = True


    if wall_cost_ratio_with_over_without > 1.0:
        if not allow_wall_exclusion:
            failures.append("wall_cost_not_improved")
    if token_cost_ratio_with_over_without > 1.0:
        failures.append("token_cost_not_improved")
    if model_call_ratio_with_over_without > 1.0:
        failures.append("model_calls_not_improved")
    if retry_cost_share_wall > 0.0:
        failures.append("hidden_retry_wall_share_present")
    if retry_cost_share_tokens > 0.0:
        failures.append("hidden_retry_token_share_present")
    if retry_cost_share_wall >= 0.25 or retry_cost_share_tokens >= 0.25:
        failures.append("hidden_retry_second_attempt_dominant")
    if wall_ledger_invalid:
        failures.append("wall_ledger_telemetry_invalid")
    if warning_ledger_invalid:
        failures.append("warning_ledger_telemetry_invalid")

    status = "IMPROVED" if not failures else "REGRESSED"
    if wall_ledger_invalid or warning_ledger_invalid:
        status = "RETURN"
    if not valid_comparison_ready:
        status = "INCONCLUSIVE_PROVIDER_VARIANCE"
        failures.append("valid_comparison_not_ready")
    return CostEfficiencyDecision(status=status, failures=failures)


def build_public_gate_checks(context: Mapping[str, Any]) -> dict[str, Any]:
    c = context
    return {
        "same_model": bool(c["with_models"] and c["without_models"] and c["with_models"] == c["without_models"]),
        "same_task_trials": c["same_task_trials"],
        "hidden_verifier_mode": c["hidden_verifier_mode"],
        "run_eligibility_complete": c["eligibility_complete"],
        "eligible_with_nexus": len(c["eligible_with"]),
        "eligible_without_nexus": len(c["eligible_without"]),
        "trust_mismatch_free": c["with_trust_mismatch_rate"] == 0.0 and c["without_trust_mismatch_rate"] == 0.0,
        "with_trust_mismatch_rate": c["with_trust_mismatch_rate"],
        "without_trust_mismatch_rate": c["without_trust_mismatch_rate"],
        "with_semantic_verified_rate": c["with_semantic_verified_rate"],
        "without_semantic_verified_rate": c["without_semantic_verified_rate"],
        "verified_equal_without_lift": c["verified_equal_without_lift"],
        "avg_wall_sec_with": c["with_avg_wall_sec"],
        "avg_wall_sec_without": c["without_avg_wall_sec"],
        "wall_cost_ratio_with_over_without": c["wall_cost_ratio_with_over_without"],
        "median_paired_wall_cost_ratio_with_over_without": c["median_paired_wall_cost_ratio"],
        "paired_wall_cost_ratio_count": len(c["paired_wall_ratios"]),
        "cost_efficiency_pair_count": c["efficiency_pair_count"],
        "cost_efficiency_sample_sufficient": c["cost_efficiency_sample_sufficient"],
        "valid_comparison_ready": c["valid_comparison_ready"],
        "valid_comparison_required_min_bare": c["valid_comparison_readiness_gate"].get("required_min_eligible_without", 0),
        "valid_comparison_bare_eligible": c["valid_comparison_readiness_gate"].get("eligible_without_count", 0),
        "infra_valid_pair_count": c["infra_quarantine_report"].get("infra_valid_pair_count", 0),
        "infra_invalid_pair_count": c["infra_quarantine_report"].get("infra_invalid_pair_count", 0),
        "infra_valid_pair_rate": c["infra_quarantine_report"].get("infra_valid_pair_rate", 0.0),
        "session_worker_contamination_rate": c.get("session_worker_contamination_rate", 0.0),
        "session_worker_contaminated_rows": c["session_worker_contamination"].get("contaminated_row_count", 0),
        "session_worker_clean": c["session_worker_contamination"].get("clean", True),
        "wall_ledger_with_conserved_rate": c["wall_ledger_summary_with"].get("conserved_rate", 1.0),
        "wall_ledger_without_conserved_rate": c["wall_ledger_summary_without"].get("conserved_rate", 1.0),
        "wall_ledger_with_invalid_rows": c["wall_ledger_summary_with"].get("telemetry_invalid_rows", 0),
        "wall_ledger_without_invalid_rows": c["wall_ledger_summary_without"].get("telemetry_invalid_rows", 0),
        "wall_ledger_telemetry_invalid": c["wall_ledger_invalid"],
        "warning_ledger_required": c["warning_ledger_required"],
        "warning_ledger_telemetry_invalid": c["warning_ledger_invalid"],
        "warning_capture_completeness": c["warning_ledger_summary"].get("warning_capture_completeness", 1.0),
        "warning_source_resolved_rate": c["warning_ledger_summary"].get("warning_source_resolved_rate", 1.0),
        "unresolved_warning_count": c["warning_ledger_summary"].get("unresolved_warning_count", 0),
        "warning_clean": c["warning_ledger_summary"].get("warning_clean", True),
        "uncaptured_warning_count": c["warning_ledger_summary"].get("uncaptured_warning_count", 0),
        "outbound_prompt_ledger_status": c["outbound_prompt_ledger_summary"].get("status", ""),
        "outbound_prompt_ledger_record_count": c["outbound_prompt_ledger_summary"].get("record_count", 0),
        "outbound_prompt_ledger_sha256": c["outbound_prompt_ledger_summary"].get("sha256", ""),
        "outbound_prompt_ledger_forbidden_literal_count": c["outbound_prompt_ledger_summary"].get("forbidden_literal_count", 0),
        "min_required_pairs_for_efficiency_claim": c["min_required_pairs_for_efficiency_claim"],
        "route_cost_regression_wall_ratio_threshold": c["route_cost_regression_wall_ratio_threshold"],
        "avg_tokens_with": c["with_avg_tokens"],
        "avg_tokens_without": c["without_avg_tokens"],
        "token_cost_ratio_with_over_without": c["token_cost_ratio_with_over_without"],
        "median_paired_token_cost_ratio_with_over_without": c["median_paired_token_cost_ratio"],
        "paired_token_cost_ratio_count": len(c["paired_token_ratios"]),
        "route_cost_regression_token_ratio_threshold": c["route_cost_regression_token_ratio_threshold"],
        "verified_lift_rate": c["verified_lift_rate"],
        "verified_lift_per_1k_with_tokens": c["verified_lift_per_1k_with_tokens"],
        "marginal_token_utility": c["marginal_token_utility"],
        "token_roi_status": c["token_roi_status"],
        "avg_prompt_system_instruction_chars_with": c["with_avg_prompt_system_instruction_chars"],
        "avg_prompt_task_constraint_chars_with": c["with_avg_prompt_task_constraint_chars"],
        "avg_prompt_source_payload_chars_with": c["with_avg_prompt_source_payload_chars"],
        "avg_prompt_test_payload_chars_with": c["with_avg_prompt_test_payload_chars"],
        "avg_prompt_candidate_payload_chars_with": c["with_avg_prompt_candidate_payload_chars"],
        "avg_prompt_nexus_control_chars_with": c["with_avg_prompt_nexus_control_chars"],
        "avg_prompt_governance_contract_chars_with": c["with_avg_prompt_governance_contract_chars"],
        "avg_gateway_total_sec_with": c["with_avg_gateway_total_sec"],
        "avg_gateway_total_sec_without": c["without_avg_gateway_total_sec"],
        "avg_gateway_process_sec_with": c["with_avg_gateway_process_sec"],
        "avg_gateway_process_sec_without": c["without_avg_gateway_process_sec"],
        "avg_gateway_provider_wait_sec_with": c["with_avg_gateway_provider_wait_sec"],
        "avg_gateway_provider_wait_sec_without": c["without_avg_gateway_provider_wait_sec"],
        "avg_gateway_parse_sec_with": c["with_avg_gateway_parse_sec"],
        "avg_gateway_parse_sec_without": c["without_avg_gateway_parse_sec"],
        "avg_context_hydration_sec_with": c["with_avg_context_hydration_sec"],
        "wall_attribution_known_share_with": c["wall_attribution_known_share_with"],
        "wall_attribution_known_share_uncapped_with": c["wall_attribution_known_share_uncapped_with"],
        "wall_attribution_overlap_suspected": c["wall_attribution_known_share_uncapped_with"] > 1.0,
        "prompt_purity_threshold": c["prompt_purity_threshold"],
        "prompt_purity_gate_passed": c["prompt_purity_gate_passed"],
        "prompt_purity_index_median": c["median_prompt_purity_index"],
        "prompt_purity_index_max": c["max_prompt_purity_index"],
        "prompt_purity_pair_count": len(c["paired_prompt_purity_ratios"]),
        "avg_model_calls_with": c["with_avg_model_calls"],
        "avg_model_calls_without": c["without_avg_model_calls"],
        "model_call_ratio_with_over_without": c["model_call_ratio_with_over_without"],
        "retry_cost_share_wall": c["retry_cost_share_wall"],
        "retry_cost_share_tokens": c["retry_cost_share_tokens"],
        "avg_phase_wall_r_sec_with": c["with_avg_phase_wall_r_sec"],
        "avg_r_phase_hyper_sprint_sec_with": c["with_avg_r_phase_hyper_sprint_sec"],
        "nexus_wearing_valid_rate": c["nexus_valid_rate"],
        "model_uses_nexus_rate": max(c["model_uses_nexus_rate"], c["legacy_gemini_uses_nexus_rate"]),
        "local_reflex_verified_rate": c["local_reflex_verified_rate"],
        "nexus_system_execution_valid_rate": c["nexus_system_execution_valid_rate"],
        "nexus_context_delivered_rate": c["nexus_context_delivered_rate"],
        "nexus_usage_valid_rate": c["nexus_usage_valid_rate"],
        "nexus_system_usage_valid_rate": c["nexus_system_usage_valid_rate"],
        "claim_verified_rate": c["claim_verified_rate"],
        "route_decision_present_rate": c["route_decision_present_rate"],
        "token_measured_rate_with": c["token_measured_rate_with"],
        "token_measured_rate_without": c["token_measured_rate_without"],
        "provider_token_measured_rate_with": c["provider_token_measured_rate_with"],
        "provider_token_measured_rate_without": c["provider_token_measured_rate_without"],
        "runner_command_present": bool(c["config"].get("runner_command")),
        "manifest_hash_present": bool(c["config"].get("tasks_manifest_hash")),
        "raw_file_hashes_present": True,
        "artifact_hash_count": len(c["artifact_files"]),
        "route_cost_ledger_present": bool(c["route_cost_ledger"]),
        "route_cost_ledger_schema": c["route_cost_ledger"].get("schema", ""),
        "route_cost_trace_report_present": bool(c["route_cost_trace_report"]),
        "route_cost_trace_report_schema": c["route_cost_trace_report"].get("schema", ""),
        "s2t_shadow_report_present": bool(c["s2t_shadow_report"]),
        "s2t_shadow_report_schema": c["s2t_shadow_report"].get("schema", ""),
        "s2t_policy_draft_schema": c["s2t_policy_draft"].get("schema", ""),
        "s2t_policy_draft_status": c["s2t_policy_draft"].get("status", ""),
        "product_kpis_present": bool(c["product_kpis"]),
        "product_kpis_schema": c["product_kpis"].get("schema", ""),
        "openseeker_alignment_present": bool(c["openseeker_kpis"]),
        "openseeker_alignment_schema": c["openseeker_kpis"].get("schema", ""),
        "commercial_model_roi_shadow_hooks_present": bool(c["commercial_model_roi_shadow_hooks"]),
        "commercial_model_roi_shadow_signal_count": c["commercial_model_roi_shadow_hooks"].get("signal_count", 0),
    }


def validate_observation_vs_public_claim_boundary(
    *,
    capability_receipts: list[dict[str, Any]],
    public_promotion_readiness: bool
) -> bool:
    """🛡️ Task A.1 & 10: 驗證 observation-only 與 public claim 邊界物理隔離。
    若發現有離線 (offline_vector_sync_lite)、背景隔離 (background_replay_lane)、
    或是任何包含 shadow_/observation_ 前綴欄位的 receipt 被標記為 public_claim_safe，
    或當 promotion readiness 為 True 時包含了這些 rows，必須立刻 Fail-closed 拋出 ValueError 阻斷偷渡。
    """
    for rcpt in capability_receipts:
        is_offline = rcpt.get("selection_source") == "offline_vector_sync_lite"
        is_background = rcpt.get("offload_provenance") == "background_replay_lane" or rcpt.get("status") == "OFFLOADED_TO_BACKGROUND"
        is_shadow = any(str(k).startswith("shadow_") or str(k).startswith("observation_") for k in rcpt.keys())
        
        # 隔離守則 1：離線、背景或 shadow offload row 絕不允許被標記為 public_claim_safe
        if (is_offline or is_background or is_shadow) and rcpt.get("public_claim_safe", False):
            raise ValueError(
                f"Security Violation: Observation-only artifact (source: {rcpt.get('selection_source') or 'shadow_telemetry'}) "
                f"attempted to bypass quarantine and claim public_claim_safe."
            )
            
        # 隔離守則 2：若當前 promotion 準備就緒，代表整個 bundle 是 public ready，
        # 此時 bundle 內絕對不允許含有任何離線、背景或 shadow telemetry 等未經 formal audit 的 receipt
        if public_promotion_readiness and (is_offline or is_background or is_shadow):
            raise ValueError(
                f"Security Violation: Offline, background-offloaded, or shadow evidence "
                f"found inside a public promotion ready bundle."
            )
            
    return True


