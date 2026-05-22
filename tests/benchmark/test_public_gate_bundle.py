from scripts.bench.public_gate_bundle import build_public_gate_checks, derive_cost_efficiency_decision


def test_cost_efficiency_decision_passes_when_costs_improve():
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=0.5,
        token_cost_ratio_with_over_without=0.25,
        model_call_ratio_with_over_without=1.0,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
    )

    assert decision.status == "IMPROVED"
    assert decision.failures == []


def test_cost_efficiency_decision_returns_when_wall_ledger_invalid():
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=0.5,
        token_cost_ratio_with_over_without=0.25,
        model_call_ratio_with_over_without=1.0,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=True,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
    )

    assert decision.status == "RETURN"
    assert decision.failures == ["wall_ledger_telemetry_invalid"]


def test_cost_efficiency_decision_is_inconclusive_without_valid_comparison():
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=0.5,
        token_cost_ratio_with_over_without=0.25,
        model_call_ratio_with_over_without=1.0,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=False,
    )

    assert decision.status == "INCONCLUSIVE_PROVIDER_VARIANCE"
    assert decision.failures == ["valid_comparison_not_ready"]


def test_public_gate_checks_expose_claim_boundary_inputs():
    checks = build_public_gate_checks(_public_gate_context())

    assert checks["same_model"] is True
    assert checks["same_task_trials"] is True
    assert checks["eligible_with_nexus"] == 1
    assert checks["eligible_without_nexus"] == 1
    assert checks["trust_mismatch_free"] is True
    assert checks["valid_comparison_ready"] is True
    assert checks["provider_token_measured_rate_with"] == 1.0
    assert checks["wall_ledger_with_conserved_rate"] == 1.0
    assert checks["route_cost_ledger_schema"] == "nexus_route_cost_ledger_v1"
    assert checks["s2t_policy_draft_status"] == "DRAFT_SHADOW_ONLY"


def _public_gate_context() -> dict:
    return {
        "with_models": {"gemini-3-flash-preview"},
        "without_models": {"gemini-3-flash-preview"},
        "same_task_trials": True,
        "hidden_verifier_mode": True,
        "eligibility_complete": True,
        "eligible_with": [{"task_id": "task/1"}],
        "eligible_without": [{"task_id": "task/1"}],
        "with_trust_mismatch_rate": 0.0,
        "without_trust_mismatch_rate": 0.0,
        "with_semantic_verified_rate": 1.0,
        "without_semantic_verified_rate": 1.0,
        "verified_equal_without_lift": True,
        "with_avg_wall_sec": 1.0,
        "without_avg_wall_sec": 2.0,
        "wall_cost_ratio_with_over_without": 0.5,
        "median_paired_wall_cost_ratio": 0.5,
        "paired_wall_ratios": [0.5],
        "efficiency_pair_count": 1,
        "cost_efficiency_sample_sufficient": False,
        "valid_comparison_ready": True,
        "valid_comparison_readiness_gate": {"required_min_eligible_without": 1, "eligible_without_count": 1},
        "infra_quarantine_report": {
            "infra_valid_pair_count": 1,
            "infra_invalid_pair_count": 0,
            "infra_valid_pair_rate": 1.0,
        },
        "session_worker_contamination_rate": 0.0,
        "session_worker_contamination": {"contaminated_row_count": 0, "clean": True},
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
        "outbound_prompt_ledger_summary": {
            "status": "PASS",
            "record_count": 1,
            "sha256": "abc",
            "forbidden_literal_count": 0,
        },
        "min_required_pairs_for_efficiency_claim": 3,
        "route_cost_regression_wall_ratio_threshold": 1.8,
        "with_avg_tokens": 100.0,
        "without_avg_tokens": 200.0,
        "token_cost_ratio_with_over_without": 0.5,
        "median_paired_token_cost_ratio": 0.5,
        "paired_token_ratios": [0.5],
        "route_cost_regression_token_ratio_threshold": 1.5,
        "verified_lift_rate": 0.0,
        "verified_lift_per_1k_with_tokens": 0.0,
        "marginal_token_utility": 0.0,
        "token_roi_status": "EFFICIENT",
        "with_avg_prompt_system_instruction_chars": 10.0,
        "with_avg_prompt_task_constraint_chars": 20.0,
        "with_avg_prompt_source_payload_chars": 30.0,
        "with_avg_prompt_test_payload_chars": 40.0,
        "with_avg_prompt_candidate_payload_chars": 50.0,
        "with_avg_prompt_nexus_control_chars": 60.0,
        "with_avg_prompt_governance_contract_chars": 70.0,
        "with_avg_gateway_total_sec": 0.1,
        "without_avg_gateway_total_sec": 0.2,
        "with_avg_gateway_process_sec": 0.1,
        "without_avg_gateway_process_sec": 0.2,
        "with_avg_gateway_provider_wait_sec": 0.1,
        "without_avg_gateway_provider_wait_sec": 0.2,
        "with_avg_gateway_parse_sec": 0.1,
        "without_avg_gateway_parse_sec": 0.2,
        "with_avg_context_hydration_sec": 0.0,
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
        "config": {"runner_command": "runner", "tasks_manifest_hash": "abc"},
        "artifact_files": [{"path": "artifact.json"}],
        "route_cost_ledger": {"schema": "nexus_route_cost_ledger_v1"},
        "route_cost_trace_report": {"schema": "nexus_route_cost_trace_report_v1"},
        "s2t_shadow_report": {"schema": "nexus_s2t_shadow_report_v1"},
        "s2t_policy_draft": {"schema": "nexus_promoted_s2t_policy_draft_v1", "status": "DRAFT_SHADOW_ONLY"},
        "product_kpis": {"schema": "nexus_product_kpis_v1"},
        "openseeker_kpis": {"schema": "nexus_openseeker_benchmark_kpis_v1"},
        "commercial_model_roi_shadow_hooks": {"signal_count": 0},
    }
