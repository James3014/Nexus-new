from __future__ import annotations

from scripts.bench.evidence_bundle_gates import build_evidence_bundle_gate_outputs


def _base_context():
    with_row = {
        "mode": "with_nexus",
        "task_id": "task-a",
        "trial_index": 1,
        "run_eligible": True,
        "route_execution_policy": {"reason_codes": []},
    }
    without_row = {"mode": "without_nexus", "task_id": "task-a", "trial_index": 1, "run_eligible": True}
    return {
        "rows": [with_row, without_row],
        "with_rows": [with_row],
        "without_rows": [without_row],
        "with_models": {"same-model"},
        "without_models": {"same-model"},
        "same_task_trials": True,
        "hidden_verifier_mode": True,
        "eligibility_complete": True,
        "eligible_with": [with_row],
        "eligible_without": [without_row],
        "with_trust_mismatch_rate": 0.0,
        "without_trust_mismatch_rate": 0.0,
        "with_semantic_verified_rate": 1.0,
        "without_semantic_verified_rate": 1.0,
        "verified_equal_without_lift": True,
        "with_avg_wall_sec": 1.0,
        "without_avg_wall_sec": 1.0,
        "wall_cost_ratio_with_over_without": 1.0,
        "median_paired_wall_cost_ratio": 1.0,
        "paired_wall_ratios": [1.0],
        "efficiency_pair_count": 1,
        "cost_efficiency_sample_sufficient": False,
        "valid_comparison_ready": True,
        "valid_comparison_readiness_gate": {
            "status": "PASS",
            "required_min_eligible_without": 1,
            "eligible_without_count": 1,
        },
        "infra_quarantine_report": {
            "infra_valid_pair_count": 1,
            "infra_invalid_pair_count": 0,
            "infra_valid_pair_rate": 1.0,
        },
        "session_worker_contamination_rate": 0.0,
        "session_worker_contamination": {"clean": True, "contaminated_row_count": 0},
        "wall_ledger_summary_with": {"conserved_rate": 1.0, "telemetry_invalid_rows": 0},
        "wall_ledger_summary_without": {"conserved_rate": 1.0, "telemetry_invalid_rows": 0},
        "wall_ledger_invalid": False,
        "warning_ledger_required": False,
        "warning_ledger_invalid": False,
        "warning_ledger_summary": {
            "warning_capture_completeness": 1.0,
            "warning_source_resolved_rate": 1.0,
            "unresolved_warning_count": 0,
            "warning_clean": True,
            "uncaptured_warning_count": 0,
        },
        "outbound_prompt_ledger_invalid": False,
        "outbound_prompt_ledger_summary": {"status": "PASS"},
        "min_required_pairs_for_efficiency_claim": 3,
        "route_cost_regression_wall_ratio_threshold": 1.8,
        "with_avg_tokens": 10.0,
        "without_avg_tokens": 10.0,
        "token_cost_ratio_with_over_without": 1.0,
        "median_paired_token_cost_ratio": 1.0,
        "paired_token_ratios": [1.0],
        "route_cost_regression_token_ratio_threshold": 1.5,
        "verified_lift_rate": 0.0,
        "verified_lift_per_1k_with_tokens": 0.0,
        "marginal_token_utility": 0.0,
        "token_roi_status": "EFFICIENT",
        "with_avg_prompt_system_instruction_chars": 1.0,
        "with_avg_prompt_task_constraint_chars": 1.0,
        "with_avg_prompt_source_payload_chars": 1.0,
        "with_avg_prompt_test_payload_chars": 1.0,
        "with_avg_prompt_candidate_payload_chars": 0.0,
        "with_avg_prompt_nexus_control_chars": 1.0,
        "with_avg_prompt_governance_contract_chars": 1.0,
        "with_avg_gateway_total_sec": 0.1,
        "without_avg_gateway_total_sec": 0.1,
        "with_avg_gateway_process_sec": 0.1,
        "without_avg_gateway_process_sec": 0.1,
        "with_avg_gateway_provider_wait_sec": 0.1,
        "without_avg_gateway_provider_wait_sec": 0.1,
        "with_avg_gateway_parse_sec": 0.1,
        "without_avg_gateway_parse_sec": 0.1,
        "with_avg_context_hydration_sec": 0.1,
        "wall_attribution_known_share_with": 1.0,
        "wall_attribution_known_share_uncapped_with": 1.0,
        "prompt_purity_threshold": 1.02,
        "prompt_purity_gate_passed": True,
        "median_prompt_purity_index": 1.0,
        "max_prompt_purity_index": 1.0,
        "paired_prompt_purity_ratios": [1.0],
        "with_avg_model_calls": 1.0,
        "without_avg_model_calls": 1.0,
        "model_call_ratio_with_over_without": 1.0,
        "retry_cost_share_wall": 0.0,
        "retry_cost_share_tokens": 0.0,
        "with_avg_phase_wall_r_sec": 0.0,
        "with_avg_r_phase_hyper_sprint_sec": 0.0,
        "nexus_valid_rate": 1.0,
        "model_uses_nexus_rate": 1.0,
        "legacy_gemini_uses_nexus_rate": 0.0,
        "local_reflex_verified_rate": 0.0,
        "nexus_system_execution_valid_rate": 1.0,
        "nexus_context_delivered_rate": 1.0,
        "nexus_usage_valid_rate": 1.0,
        "nexus_system_usage_valid_rate": 1.0,
        "claim_verified_rate": 1.0,
        "route_decision_present_rate": 1.0,
        "token_measured_rate_with": 1.0,
        "token_measured_rate_without": 1.0,
        "provider_token_measured_rate_with": 1.0,
        "provider_token_measured_rate_without": 1.0,
        "artifact_files": [],
        "route_cost_ledger": {"schema": "nexus_route_cost_ledger_v1"},
        "route_cost_trace_report": {"schema": "nexus_route_cost_trace_report_v1"},
        "s2t_shadow_report": {"schema": "nexus_s2t_shadow_report_v1"},
        "s2t_policy_draft": {"schema": "nexus_promoted_s2t_policy_draft_v1", "status": "DRAFT_SHADOW_ONLY"},
        "product_kpis": {"schema": "nexus_product_kpis_v1"},
        "openseeker_kpis": {"schema": "nexus_openseeker_benchmark_kpis_v1"},
        "commercial_model_roi_shadow_hooks": {"signal_count": 0},
    }


def test_build_evidence_bundle_gate_outputs_preserves_public_pass_path():
    output = build_evidence_bundle_gate_outputs(
        _base_context(),
        {"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "cmd"},
    )

    assert output.delivery_gate_passed is True
    assert output.cost_claim_passed is True
    assert output.public_claim_gates["public_claim_gate"]["verdict"] == "PASS"
    assert output.public_gate_checks["run_eligibility_complete"] is True
    assert output.route_policy_evidence_contract["status"] == "PASS"


def test_build_evidence_bundle_gate_outputs_fails_closed_on_route_policy_contract_failure():
    context = _base_context()
    context["rows"][0].pop("route_execution_policy")

    output = build_evidence_bundle_gate_outputs(
        context,
        {"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "cmd"},
    )

    assert output.route_policy_evidence_contract["status"] == "RETURN"
    assert "route_policy_evidence:task-a:1:route_execution_policy_missing" in output.delivery_gate_failures
    assert output.public_claim_gates["public_claim_gate"]["verdict"] == "FAIL"
