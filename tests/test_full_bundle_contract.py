import pytest
import json
from scripts.bench.evidence_bundle_gates import build_evidence_bundle_gate_outputs
from scripts.bench.public_lane_contract import build_public_promotion_readiness_contract

def test_full_bundle_contract_integration_flow():
    """
    TDD Phase 4 (RED): Verify the integration flow of full bundle contract gates.
    Ensure route policy evidence, telemetry classification, and promotion readiness contracts
    correctly aggregate on the evidence bundle and pass strict fail-closed constraints.
    """
    # 1. Setup a highly realistic mock context containing v3.0 telemetry classification and route evidence
    mock_rows = [
        {
            "task_id": "repair_ast_1",
            "trial_index": 1,
            "mode": "with_nexus",
            "run_eligible": True,
            "hidden_verifier_passed": True,
            "capability_activation_contract": "cost_capped",
            "expected_capabilities": ["ast_scanning"],
            "expected_capability_receipt_coverage": {
                "expected": ["ast_scanning"],
                "missing": [],
                "all_public_safe": True
            },
            "expected_capability_invocation_coverage": {
                "expected": ["ast_scanning"],
                "missing": [],
                "all_invoked_with_evidence": True
            },
            "capability_receipts": [
                {
                    "name": "ast_scanning",
                    "selected": True,
                    "invoked": True,
                    "evidence_refs": ["ev_ref_1"],
                    "distinct_roles": ["actor_1", "actor_2"],
                    "replay_refs": ["rep_ref_1"],
                    "source_refs": ["src_ref_1"],
                    "semantic_evidence_complete": True,
                    "telemetries": {
                        "wall_time_ms": 4000,
                        "token_usage": 1500,
                        "provider_costs": 0.03,
                        "overhead_ms": 100,
                        "network_timeout_observed_ms": 2500,
                        "cost_accounting_exclusion_candidate": True,
                        "telemetry_provenance": "gateway_timeout"
                    }
                }
            ],
            "route_execution_policy": {
                "reason_codes": ["cost_capped_capability_allows_verified_pre_model_rescue", "expected_capability_protection"],
                "pre_model_deterministic_rescue_allowed": False,
                "candidate_pool_size": 1
            },
            "semantic_status": "VERIFIED",
            "local_reflex_risk_level": "low",
            "local_reflex_bare_sufficiency": "high",
            "nexus_winner_source": "local_deterministic_pre_model_rescue"
        },
        {
            "task_id": "repair_ast_1",
            "trial_index": 1,
            "mode": "without_nexus",
            "run_eligible": True,
            "hidden_verifier_passed": True,
            "semantic_status": "VERIFIED"
        }
    ]
    
    # Bundle level mock metrics
    mock_context = {
        "rows": mock_rows,
        "with_rows": [mock_rows[0]],
        "without_rows": [mock_rows[1]],
        "with_models": ["gpt-4o"],
        "without_models": ["gpt-4o"],
        "same_task_trials": True,
        "hidden_verifier_mode": True,
        "eligibility_complete": True,
        "eligible_with": [mock_rows[0]],
        "eligible_without": [mock_rows[1]],
        "with_trust_mismatch_rate": 0.0,
        "without_trust_mismatch_rate": 0.0,
        "with_semantic_verified_rate": 1.0,
        "without_semantic_verified_rate": 1.0,
        "nexus_valid_rate": 1.0,
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
        "prompt_purity_gate_passed": True,
        "verified_equal_without_lift": False,
        "wall_cost_ratio_with_over_without": 1.1,  # ordinary wall regression
        "token_cost_ratio_with_over_without": 0.8,
        "model_call_ratio_with_over_without": 0.8,
        "retry_cost_share_wall": 0.0,
        "retry_cost_share_tokens": 0.0,
        "wall_ledger_invalid": False,
        "warning_ledger_invalid": False,
        "wall_ledger_summary_with": {
            "conserved_rate": 1.0,
            "telemetry_invalid_rows": 0
        },
        "wall_ledger_summary_without": {
            "conserved_rate": 1.0,
            "telemetry_invalid_rows": 0
        },
        "valid_comparison_ready": True,
        "session_worker_contamination_rate": 0.0,
        "outbound_prompt_ledger_invalid": False,
        "outbound_prompt_ledger_summary": {"status": "PASS", "forbidden_literal_count": 0},
        "session_worker_contamination": {"clean": True, "contaminated_row_count": 0},
        "route_cost_ledger": {"schema": "nexus_route_cost_ledger_v1"},
        "route_cost_trace_report": {"schema": "nexus_route_cost_trace_report_v1"},
        "s2t_shadow_report": {"schema": "nexus_s2t_shadow_report_v1"},
        "s2t_policy_draft": {"schema": "nexus_s2t_policy_draft_v1", "status": "PASS"},
        "valid_comparison_readiness_gate": {
            "required_min_eligible_without": 0,
            "eligible_without_count": 0
        },
        "infra_quarantine_report": {
            "infra_valid_pair_count": 1,
            "infra_invalid_pair_count": 0,
            "infra_valid_pair_rate": 1.0
        },
        "product_kpis": {"schema": "nexus_product_kpis_v1"},
        "openseeker_kpis": {"schema": "nexus_openseeker_kpis_v1"},
        "commercial_model_roi_shadow_hooks": {"signal_count": 5},
        "artifact_files": ["file1"],
        "min_required_pairs_for_efficiency_claim": 1,
        "route_cost_regression_wall_ratio_threshold": 1.05,
        "route_cost_regression_token_ratio_threshold": 1.05,
        "with_avg_wall_sec": 4.0,
        "without_avg_wall_sec": 3.7,
        "median_paired_wall_cost_ratio": 1.1,
        "paired_wall_ratios": [1.1],
        "efficiency_pair_count": 1,
        "cost_efficiency_sample_sufficient": True,
        "warning_ledger_required": False,
        "warning_ledger_summary": {"warning_clean": True, "unresolved_warning_count": 0},
        "with_avg_tokens": 1500,
        "without_avg_tokens": 1800,
        "median_prompt_purity_index": 1.0,
        "max_prompt_purity_index": 1.0,
        "paired_prompt_purity_ratios": [1.0],
        "with_avg_model_calls": 1,
        "without_avg_model_calls": 2,
        "with_avg_prompt_system_instruction_chars": 100,
        "with_avg_prompt_task_constraint_chars": 100,
        "with_avg_prompt_source_payload_chars": 100,
        "with_avg_prompt_test_payload_chars": 100,
        "with_avg_prompt_candidate_payload_chars": 100,
        "with_avg_prompt_nexus_control_chars": 100,
        "with_avg_prompt_governance_contract_chars": 100,
        "with_avg_gateway_total_sec": 4.0,
        "without_avg_gateway_total_sec": 3.7,
        "with_avg_gateway_process_sec": 0.5,
        "without_avg_gateway_process_sec": 0.5,
        "with_avg_gateway_provider_wait_sec": 3.5,
        "without_avg_gateway_provider_wait_sec": 3.2,
        "with_avg_gateway_parse_sec": 0.05,
        "without_avg_gateway_parse_sec": 0.05,
        "with_avg_context_hydration_sec": 0.1,
        "wall_attribution_known_share_with": 0.9,
        "wall_attribution_known_share_uncapped_with": 0.9,
        "prompt_purity_threshold": 0.1,
        "with_avg_phase_wall_r_sec": 1.0,
        "with_avg_r_phase_hyper_sprint_sec": 0.5,
        "model_uses_nexus_rate": 1.0,
        "legacy_gemini_uses_nexus_rate": 1.0,
        "local_reflex_verified_rate": 1.0,
        "nexus_valid_rate": 1.0,
        "claim_verified_below_threshold": False,
        "token_measured_rate_with": 1.0,
        "token_measured_rate_without": 1.0,
        "provider_token_measured_rate_with": 1.0,
        "provider_token_measured_rate_without": 1.0,
        "paired_token_ratios": [0.8],
        "median_paired_token_cost_ratio": 0.8,
        "verified_lift_rate": 1.0,
        "verified_lift_per_1k_with_tokens": 0.5,
        "marginal_token_utility": 1.0,
        "token_roi_status": "HIGH",
    }
    
    mock_config = {
        "tasks_file": "tasks.json",
        "tasks_manifest_hash": "sha_123",
        "runner_command": "pytest",
        "trust_workspace_policy": "trusted"
    }
    
    # 2. Build the bundle outputs
    outputs = build_evidence_bundle_gate_outputs(mock_context, mock_config)
    
    # Under Telemetry Classification & Provenance, since there is cost_accounting_exclusion_candidate=True
    # with gateway_timeout, derive_cost_efficiency_decision should classify this as NEUTRAL/IMPROVED rather than REGRESSED
    assert outputs.cost_efficiency_status in {"IMPROVED", "NEUTRAL"}
    
    # 3. Verify the final Public Promotion Readiness Contract succeeds
    bundle_payload = {
        "public_verified_delivery_claim_gate": outputs.public_claim_gates["public_verified_delivery_claim_gate"],
        "public_cost_claim_gate": outputs.public_claim_gates["public_cost_claim_gate"],
        "public_cost_efficiency_claim_gate": outputs.public_claim_gates["public_cost_efficiency_claim_gate"],
        "public_claim_gate": outputs.public_claim_gates["public_claim_gate"],
        "taskset_contract": {"fixed_public_taskset_ready": True},
        "session_worker_contamination": {"clean": True, "contamination_rate": 0.0},
        "outbound_prompt_ledger_gate": {"status": "PASS"},
        "x3_promotion_gate": {"status": "PASS"},
        "valid_comparison_readiness_gate": {"status": "PASS"},
        "route_policy_evidence_contract": outputs.route_policy_evidence_contract,
        "expected_capability_evidence_contract": outputs.expected_capability_evidence_contract,
        "external_provider_claim_boundary_contract": {"public_claim_allowed": True},
    }
    
    promotion_readiness = build_public_promotion_readiness_contract(bundle_payload)
    
    # Under revised fail-closed TDD, ensure promotion is fully allowed
    assert promotion_readiness["promotion_allowed"] is True
    assert promotion_readiness["status"] == "PASS"
