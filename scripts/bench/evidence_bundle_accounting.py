from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from scripts.bench.cost_evidence_classifier import row_has_measured_provider_tokens
from scripts.bench.evidence_bundle_posture import derive_valid_comparison_readiness_gate
from scripts.bench.public_gate_metrics import (
    mean_number,
    median,
    paired_metric_ratios,
    paired_prompt_purity_ratios,
    safe_ratio,
)


@dataclass(frozen=True)
class PublicCostAccountingContext:
    token_measured_rate_with: float
    token_measured_rate_without: float
    provider_token_measured_rate_with: float
    provider_token_measured_rate_without: float
    with_avg_wall_sec: float
    without_avg_wall_sec: float
    with_avg_tokens: float
    without_avg_tokens: float
    with_avg_model_calls: float
    without_avg_model_calls: float
    with_avg_prompt_system_instruction_chars: float
    with_avg_prompt_task_constraint_chars: float
    with_avg_prompt_source_payload_chars: float
    with_avg_prompt_test_payload_chars: float
    with_avg_prompt_candidate_payload_chars: float
    with_avg_prompt_nexus_control_chars: float
    with_avg_prompt_governance_contract_chars: float
    with_avg_gateway_total_sec: float
    without_avg_gateway_total_sec: float
    with_avg_gateway_process_sec: float
    without_avg_gateway_process_sec: float
    with_avg_gateway_provider_wait_sec: float
    without_avg_gateway_provider_wait_sec: float
    with_avg_gateway_parse_sec: float
    without_avg_gateway_parse_sec: float
    with_avg_context_hydration_sec: float
    with_avg_phase_wall_r_sec: float
    with_avg_r_phase_hyper_sprint_sec: float
    wall_attribution_known_share_uncapped_with: float
    wall_attribution_known_share_with: float
    wall_cost_ratio_with_over_without: float
    token_cost_ratio_with_over_without: float
    model_call_ratio_with_over_without: float
    verified_lift_rate: float
    token_overhead: float
    verified_lift_per_1k_with_tokens: float
    marginal_token_utility: float
    token_roi_status: str
    retry_cost_share_wall: float
    retry_cost_share_tokens: float
    paired_wall_ratios: list[float]
    paired_token_ratios: list[float]
    paired_prompt_purity_ratios: list[float]
    median_paired_wall_cost_ratio: float
    median_paired_token_cost_ratio: float
    median_prompt_purity_index: float
    max_prompt_purity_index: float
    prompt_purity_threshold: float
    prompt_purity_gate_passed: bool
    min_required_pairs_for_efficiency_claim: int
    efficiency_pair_count: int
    cost_efficiency_sample_sufficient: bool
    valid_comparison_readiness_gate: dict[str, Any]
    valid_comparison_ready: bool
    route_cost_regression_wall_ratio_threshold: float
    route_cost_regression_token_ratio_threshold: float
    verified_equal_without_lift: bool
    eligibility_complete: bool
    wall_regression_systemic: bool
    token_regression_systemic: bool

    def as_context(self) -> dict[str, Any]:
        return asdict(self)


def build_public_cost_accounting_context(
    *,
    with_rows: list[dict[str, Any]],
    without_rows: list[dict[str, Any]],
    eligible_with: list[dict[str, Any]],
    eligible_without: list[dict[str, Any]],
    config: Mapping[str, Any],
    with_semantic_verified_rate: float,
    without_semantic_verified_rate: float,
    with_trust_mismatch_rate: float,
    without_trust_mismatch_rate: float,
) -> PublicCostAccountingContext:
    token_measured_rate_with = _rate_for(with_rows, "token_measured")
    token_measured_rate_without = _rate_for(without_rows, "token_measured")
    provider_token_measured_rate_with = _provider_token_rate(with_rows)
    provider_token_measured_rate_without = _provider_token_rate(without_rows)
    with_avg_wall_sec = mean_number(eligible_with, "wall_duration_sec", "duration_sec")
    without_avg_wall_sec = mean_number(eligible_without, "wall_duration_sec", "duration_sec")
    with_avg_tokens = mean_number(eligible_with, "total_tokens", "model_total_tokens")
    without_avg_tokens = mean_number(eligible_without, "total_tokens", "model_total_tokens")
    with_avg_model_calls = mean_number(eligible_with, "model_calls")
    without_avg_model_calls = mean_number(eligible_without, "model_calls")
    with_avg_prompt_system_instruction_chars = mean_number(eligible_with, "prompt_system_instruction_chars")
    with_avg_prompt_task_constraint_chars = mean_number(eligible_with, "prompt_task_constraint_chars")
    with_avg_prompt_source_payload_chars = mean_number(eligible_with, "prompt_source_payload_chars")
    with_avg_prompt_test_payload_chars = mean_number(eligible_with, "prompt_test_payload_chars")
    with_avg_prompt_candidate_payload_chars = mean_number(eligible_with, "prompt_candidate_payload_chars")
    with_avg_prompt_nexus_control_chars = mean_number(eligible_with, "prompt_nexus_control_chars")
    with_avg_prompt_governance_contract_chars = mean_number(eligible_with, "prompt_governance_contract_chars")
    with_avg_gateway_total_sec = mean_number(eligible_with, "gateway_total_sec")
    without_avg_gateway_total_sec = mean_number(eligible_without, "gateway_total_sec")
    with_avg_gateway_process_sec = mean_number(eligible_with, "gateway_process_sec")
    without_avg_gateway_process_sec = mean_number(eligible_without, "gateway_process_sec")
    with_avg_gateway_provider_wait_sec = mean_number(eligible_with, "gateway_provider_wait_sec")
    without_avg_gateway_provider_wait_sec = mean_number(eligible_without, "gateway_provider_wait_sec")
    with_avg_gateway_parse_sec = mean_number(eligible_with, "gateway_parse_sec")
    without_avg_gateway_parse_sec = mean_number(eligible_without, "gateway_parse_sec")
    with_avg_context_hydration_sec = mean_number(eligible_with, "timing_context_pack_sec")
    with_avg_phase_wall_r_sec = mean_number(eligible_with, "phase_wall_r_sec")
    with_avg_r_phase_hyper_sprint_sec = mean_number(eligible_with, "r_phase_hyper_sprint_sec")
    wall_attribution_known_share_uncapped_with = safe_ratio(
        with_avg_gateway_total_sec + with_avg_context_hydration_sec + with_avg_phase_wall_r_sec,
        with_avg_wall_sec,
    )
    wall_attribution_known_share_with = min(1.0, wall_attribution_known_share_uncapped_with)
    wall_cost_ratio_with_over_without = safe_ratio(with_avg_wall_sec, without_avg_wall_sec)
    token_cost_ratio_with_over_without = safe_ratio(with_avg_tokens, without_avg_tokens)
    model_call_ratio_with_over_without = safe_ratio(with_avg_model_calls, without_avg_model_calls)
    verified_lift_rate = round(with_semantic_verified_rate - without_semantic_verified_rate, 4)
    token_overhead = max(0.0, with_avg_tokens - without_avg_tokens)
    verified_lift_per_1k_with_tokens = round(verified_lift_rate / (with_avg_tokens / 1000.0), 6) if with_avg_tokens > 0 else 0.0
    marginal_token_utility = round(verified_lift_rate / (token_overhead / 1000.0), 6) if token_overhead > 0 else 0.0
    token_roi_status = _token_roi_status(
        token_cost_ratio_with_over_without=token_cost_ratio_with_over_without,
        verified_lift_rate=verified_lift_rate,
    )
    hidden_retry_wall_total = sum(float(row.get("hidden_retry_wall_sec", 0.0) or 0.0) for row in eligible_with)
    hidden_retry_token_total = sum(float(row.get("hidden_retry_tokens", 0.0) or 0.0) for row in eligible_with)
    with_wall_total = sum(float(row.get("wall_duration_sec", row.get("duration_sec", 0.0)) or 0.0) for row in eligible_with)
    with_token_total = sum(float(row.get("total_tokens", row.get("model_total_tokens", 0.0)) or 0.0) for row in eligible_with)
    retry_cost_share_wall = safe_ratio(hidden_retry_wall_total, with_wall_total)
    retry_cost_share_tokens = safe_ratio(hidden_retry_token_total, with_token_total)
    paired_wall_ratios = paired_metric_ratios(eligible_with, eligible_without, "wall_duration_sec")
    paired_token_ratios = paired_metric_ratios(eligible_with, eligible_without, "total_tokens")
    paired_prompt_purity_ratios = paired_prompt_purity_ratios_fn(eligible_with, eligible_without)
    median_paired_wall_cost_ratio = median(paired_wall_ratios)
    median_paired_token_cost_ratio = median(paired_token_ratios)
    median_prompt_purity_index = median(paired_prompt_purity_ratios)
    max_prompt_purity_index = round(max(paired_prompt_purity_ratios), 4) if paired_prompt_purity_ratios else 0.0
    prompt_purity_threshold = float(config.get("prompt_purity_threshold") or 1.02)
    prompt_purity_gate_passed = not paired_prompt_purity_ratios or max_prompt_purity_index <= prompt_purity_threshold
    min_required_pairs_for_efficiency_claim = int(config.get("min_required_pairs_for_efficiency_claim") or 3)
    efficiency_pair_count = min(len(paired_wall_ratios), len(paired_token_ratios))
    cost_efficiency_sample_sufficient = efficiency_pair_count >= min_required_pairs_for_efficiency_claim
    valid_comparison_readiness_gate = derive_valid_comparison_readiness_gate(
        eligible_without_count=len(eligible_without),
        without_row_count=len(without_rows),
    )
    valid_comparison_ready = valid_comparison_readiness_gate.get("status") == "PASS"
    route_cost_regression_wall_ratio_threshold = float(config.get("route_cost_regression_wall_ratio_threshold") or 1.8)
    route_cost_regression_token_ratio_threshold = float(config.get("route_cost_regression_token_ratio_threshold") or 1.5)
    verified_equal_without_lift = bool(
        eligible_with
        and eligible_without
        and with_semantic_verified_rate >= 1.0
        and without_semantic_verified_rate >= 1.0
        and with_semantic_verified_rate <= without_semantic_verified_rate
        and with_trust_mismatch_rate >= without_trust_mismatch_rate
    )
    eligibility_complete = len(eligible_with) == len(with_rows) and len(eligible_without) == len(without_rows)
    wall_regression_systemic = (
        median_paired_wall_cost_ratio > route_cost_regression_wall_ratio_threshold
        if len(paired_wall_ratios) >= 3
        else wall_cost_ratio_with_over_without > route_cost_regression_wall_ratio_threshold
    )
    token_regression_systemic = (
        median_paired_token_cost_ratio > route_cost_regression_token_ratio_threshold
        if len(paired_token_ratios) >= 3
        else token_cost_ratio_with_over_without > route_cost_regression_token_ratio_threshold
    )
    return PublicCostAccountingContext(
        token_measured_rate_with=token_measured_rate_with,
        token_measured_rate_without=token_measured_rate_without,
        provider_token_measured_rate_with=provider_token_measured_rate_with,
        provider_token_measured_rate_without=provider_token_measured_rate_without,
        with_avg_wall_sec=with_avg_wall_sec,
        without_avg_wall_sec=without_avg_wall_sec,
        with_avg_tokens=with_avg_tokens,
        without_avg_tokens=without_avg_tokens,
        with_avg_model_calls=with_avg_model_calls,
        without_avg_model_calls=without_avg_model_calls,
        with_avg_prompt_system_instruction_chars=with_avg_prompt_system_instruction_chars,
        with_avg_prompt_task_constraint_chars=with_avg_prompt_task_constraint_chars,
        with_avg_prompt_source_payload_chars=with_avg_prompt_source_payload_chars,
        with_avg_prompt_test_payload_chars=with_avg_prompt_test_payload_chars,
        with_avg_prompt_candidate_payload_chars=with_avg_prompt_candidate_payload_chars,
        with_avg_prompt_nexus_control_chars=with_avg_prompt_nexus_control_chars,
        with_avg_prompt_governance_contract_chars=with_avg_prompt_governance_contract_chars,
        with_avg_gateway_total_sec=with_avg_gateway_total_sec,
        without_avg_gateway_total_sec=without_avg_gateway_total_sec,
        with_avg_gateway_process_sec=with_avg_gateway_process_sec,
        without_avg_gateway_process_sec=without_avg_gateway_process_sec,
        with_avg_gateway_provider_wait_sec=with_avg_gateway_provider_wait_sec,
        without_avg_gateway_provider_wait_sec=without_avg_gateway_provider_wait_sec,
        with_avg_gateway_parse_sec=with_avg_gateway_parse_sec,
        without_avg_gateway_parse_sec=without_avg_gateway_parse_sec,
        with_avg_context_hydration_sec=with_avg_context_hydration_sec,
        with_avg_phase_wall_r_sec=with_avg_phase_wall_r_sec,
        with_avg_r_phase_hyper_sprint_sec=with_avg_r_phase_hyper_sprint_sec,
        wall_attribution_known_share_uncapped_with=wall_attribution_known_share_uncapped_with,
        wall_attribution_known_share_with=wall_attribution_known_share_with,
        wall_cost_ratio_with_over_without=wall_cost_ratio_with_over_without,
        token_cost_ratio_with_over_without=token_cost_ratio_with_over_without,
        model_call_ratio_with_over_without=model_call_ratio_with_over_without,
        verified_lift_rate=verified_lift_rate,
        token_overhead=token_overhead,
        verified_lift_per_1k_with_tokens=verified_lift_per_1k_with_tokens,
        marginal_token_utility=marginal_token_utility,
        token_roi_status=token_roi_status,
        retry_cost_share_wall=retry_cost_share_wall,
        retry_cost_share_tokens=retry_cost_share_tokens,
        paired_wall_ratios=paired_wall_ratios,
        paired_token_ratios=paired_token_ratios,
        paired_prompt_purity_ratios=paired_prompt_purity_ratios,
        median_paired_wall_cost_ratio=median_paired_wall_cost_ratio,
        median_paired_token_cost_ratio=median_paired_token_cost_ratio,
        median_prompt_purity_index=median_prompt_purity_index,
        max_prompt_purity_index=max_prompt_purity_index,
        prompt_purity_threshold=prompt_purity_threshold,
        prompt_purity_gate_passed=prompt_purity_gate_passed,
        min_required_pairs_for_efficiency_claim=min_required_pairs_for_efficiency_claim,
        efficiency_pair_count=efficiency_pair_count,
        cost_efficiency_sample_sufficient=cost_efficiency_sample_sufficient,
        valid_comparison_readiness_gate=valid_comparison_readiness_gate,
        valid_comparison_ready=valid_comparison_ready,
        route_cost_regression_wall_ratio_threshold=route_cost_regression_wall_ratio_threshold,
        route_cost_regression_token_ratio_threshold=route_cost_regression_token_ratio_threshold,
        verified_equal_without_lift=verified_equal_without_lift,
        eligibility_complete=eligibility_complete,
        wall_regression_systemic=wall_regression_systemic,
        token_regression_systemic=token_regression_systemic,
    )


def _rate_for(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if bool(row.get(key, False))) / len(rows), 4)


def _provider_token_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row_has_measured_provider_tokens(row)) / len(rows), 4)


def _token_roi_status(*, token_cost_ratio_with_over_without: float, verified_lift_rate: float) -> str:
    if token_cost_ratio_with_over_without <= 1.0:
        return "EFFICIENT"
    if verified_lift_rate > 0.0:
        return "LIFT_WITH_OVERHEAD"
    return "UNPROFITABLE_LESSON"


def paired_prompt_purity_ratios_fn(
    with_rows: list[dict[str, Any]],
    without_rows: list[dict[str, Any]],
) -> list[float]:
    return paired_prompt_purity_ratios(with_rows, without_rows)
