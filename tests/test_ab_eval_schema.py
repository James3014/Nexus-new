from __future__ import annotations

import json

from scripts.bench.ab_eval import compare_datasets, load_runs


def test_ab_eval_loads_jsonl_and_compares_semantic_solve_rate(tmp_path):
    dataset_a = tmp_path / "a.jsonl"
    dataset_b = tmp_path / "b.jsonl"

    dataset_a.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "t1",
                        "category": "bugfix",
                        "repo_kind": "neutral_fixture",
                        "semantic_status": "UNVERIFIED",
                        "task_duration_sec": 10.0,
                        "wall_duration_sec": 12.0,
                        "total_tokens": 200,
                        "token_capture_status": "measured",
                        "attempt_count": 1,
                    }
                ),
                json.dumps(
                    {
                        "task_id": "t2",
                        "category": "feature",
                        "repo_kind": "nexus_internal",
                        "semantic_status": "VERIFIED",
                        "task_duration_sec": 20.0,
                        "wall_duration_sec": 22.0,
                        "total_tokens": 400,
                        "token_capture_status": "measured",
                        "attempt_count": 2,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    dataset_b.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "t1",
                        "category": "bugfix",
                        "repo_kind": "neutral_fixture",
                        "semantic_status": "VERIFIED",
                        "task_duration_sec": 12.0,
                        "wall_duration_sec": 14.0,
                        "total_tokens": 300,
                        "token_capture_status": "measured",
                        "model_total_tokens": 300,
                        "model_token_capture_status": "measured",
                        "rescue_cost_status": "local_only",
                        "attempt_count": 2,
                        "nexus_tier": "full",
                        "gemini_uses_nexus": True,
                        "nexus_usage_valid": True,
                        "nexus_rescued": True,
                        "gemini_patch_status": "failed",
                        "pillar_lancedb_active": True,
                        "pillar_memory_active": True,
                        "pillar_mempalace_active": True,
                        "pillar_belief_active": True,
                        "pillar_artifact_active": True,
                        "phase_p": "route_built",
                        "phase_x": "retrieval_checked",
                        "phase_d": "guard_decision",
                        "phase_r": "hyper_executed",
                        "phase_a": "artifact_verified",
                        "phase_c": "closure_written",
                        "capability_claim_verified": True,
                        "capability_hyper_used": True,
                        "capability_self_heal_used": True,
                        "capability_swarm_used": True,
                        "capability_drone_used": False,
                        "capability_nightshift_recommended": True,
                        "capability_nightshift_invoked": True,
                        "capability_nightshift_recovered": False,
                        "autoreason_enabled": True,
                        "ddtree_enabled": True,
                        "ddtree_eligible": True,
                        "ultra_review_recommended": True,
                        "ultra_review_invoked": True,
                        "ultra_review_gate_passed": True,
                        "capability_plan_trace_present": True,
                        "capability_plan_node_count": 12,
                        "capability_plan_score": 24,
                        "artifact_verification_only": True,
                        "rlm_trace_present": True,
                        "rlm_trace_quality_score": 80,
                    }
                ),
                json.dumps(
                    {
                        "task_id": "t2",
                        "category": "feature",
                        "repo_kind": "nexus_internal",
                        "semantic_status": "VERIFIED",
                        "task_duration_sec": 22.0,
                        "wall_duration_sec": 24.0,
                        "total_tokens": 500,
                        "token_capture_status": "measured",
                        "attempt_count": 3,
                        "mutation_required": True,
                        "artifact_changed": True,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = compare_datasets("without", load_runs(dataset_a), "with", load_runs(dataset_b))
    assert report["a"]["summary"]["solve_rate"] == 0.5
    assert report["a"]["summary"]["solve_count"] == 1
    assert report["a"]["summary"]["solve_rate_ci95"] == [0.0945, 0.9055]
    assert report["a"]["summary"]["semantic_verified_rate"] == 0.5
    assert report["a"]["summary"]["avg_wall_duration_sec"] == 17.0
    assert report["b"]["summary"]["solve_rate"] == 1.0
    assert report["b"]["summary"]["semantic_verified_rate"] == 1.0
    assert report["b"]["summary"]["avg_wall_duration_sec"] == 19.0
    assert report["b"]["summary"]["median_duration_sec"] == 17.0
    assert report["delta"]["solve_rate_delta"] == 0.5
    assert report["delta"]["semantic_verified_rate_delta"] == 0.5
    assert report["delta"]["nexus_lift"] == 1.0
    assert report["delta"]["semantic_nexus_lift"] == 1.0
    assert report["delta"]["avg_wall_duration_sec_delta"] == 2.0
    assert report["a"]["summary"]["token_observable_rate"] == 1.0
    assert report["b"]["summary"]["token_observable_rate"] == 1.0
    assert report["a"]["summary"]["token_measured_rate"] == 1.0
    assert report["b"]["summary"]["token_measured_rate"] == 1.0
    assert report["a"]["summary"]["token_estimated_rate"] == 0.0
    assert report["b"]["summary"]["token_local_only_rate"] == 0.0
    assert report["a"]["summary"]["cost_comparable_rate"] == 1.0
    assert report["b"]["summary"]["cost_comparable_rate"] == 1.0
    assert report["b"]["summary"]["avg_model_total_tokens"] == 150.0
    assert report["b"]["summary"]["model_token_measured_rate"] == 0.5
    assert report["b"]["summary"]["local_rescue_rate"] == 0.5
    assert report["a"]["summary"]["avg_total_tokens_measured_only"] == 300.0
    assert report["b"]["summary"]["nexus_usage_valid_rate"] == 0.5
    assert report["b"]["summary"]["nexus_full_tier_rate"] == 0.5
    assert report["b"]["summary"]["model_uses_nexus_rate"] == 0.5
    assert report["b"]["summary"]["gemini_uses_nexus_rate"] == 0.5
    assert report["b"]["summary"]["nexus_rescue_rate"] == 0.5
    assert report["b"]["summary"]["gemini_patch_pass_rate"] == 0.0
    assert report["b"]["summary"]["phase_completion_rate"] == 0.5
    assert report["b"]["summary"]["claim_verified_rate"] == 0.5
    assert report["b"]["summary"]["hyper_used_rate"] == 0.5
    assert report["b"]["summary"]["self_heal_used_rate"] == 0.5
    assert report["b"]["summary"]["swarm_used_rate"] == 0.5
    assert report["b"]["summary"]["drone_used_rate"] == 0.0
    assert report["b"]["summary"]["nightshift_recommended_rate"] == 0.5
    assert report["b"]["summary"]["nightshift_invoked_rate"] == 0.5
    assert report["b"]["summary"]["nightshift_recovery_rate"] == 0.0
    assert report["b"]["summary"]["autoreason_enabled_rate"] == 0.5
    assert report["b"]["summary"]["ddtree_enabled_rate"] == 0.5
    assert report["b"]["summary"]["ddtree_eligible_rate"] == 0.5
    assert report["b"]["summary"]["ultra_review_recommended_rate"] == 0.5
    assert report["b"]["summary"]["ultra_review_invoked_rate"] == 0.5
    assert report["b"]["summary"]["ultra_review_gate_passed_rate"] == 0.5
    assert report["b"]["summary"]["capability_plan_trace_present_rate"] == 0.5
    assert report["b"]["summary"]["avg_capability_plan_node_count"] == 6.0
    assert report["b"]["summary"]["avg_capability_plan_score"] == 12.0
    assert report["b"]["summary"]["patch_success_count"] == 1
    assert report["b"]["summary"]["patch_success_rate"] == 0.5
    assert report["b"]["summary"]["verification_only_rate"] == 0.5
    assert report["b"]["summary"]["mutation_required_rate"] == 0.5
    assert report["b"]["summary"]["mutation_success_rate"] == 1.0
    assert report["delta"]["nexus_usage_valid_rate_delta"] == 0.5
    assert report["delta"]["nexus_full_tier_rate_delta"] == 0.5
    assert report["delta"]["patch_success_rate_delta"] == 0.5
    assert report["delta"]["verification_only_rate_delta"] == 0.5
    assert report["delta"]["cost_comparable_rate_delta"] == 0.0
    assert report["delta"]["model_token_measured_rate_delta"] == 0.5
    assert report["delta"]["local_rescue_rate_delta"] == 0.5
    assert report["delta"]["swarm_used_rate_delta"] == 0.5
    assert report["delta"]["drone_used_rate_delta"] == 0.0
    assert report["delta"]["nightshift_recommended_rate_delta"] == 0.5
    assert report["delta"]["nightshift_invoked_rate_delta"] == 0.5
    assert report["delta"]["nightshift_recovery_rate_delta"] == 0.0
    assert report["delta"]["autoreason_enabled_rate_delta"] == 0.5
    assert report["delta"]["ddtree_enabled_rate_delta"] == 0.5
    assert report["delta"]["ddtree_eligible_rate_delta"] == 0.5
    assert report["delta"]["ultra_review_recommended_rate_delta"] == 0.5
    assert report["delta"]["ultra_review_invoked_rate_delta"] == 0.5
    assert report["delta"]["ultra_review_gate_passed_rate_delta"] == 0.5
    assert report["delta"]["capability_plan_trace_present_rate_delta"] == 0.5
    assert report["delta"]["avg_capability_plan_node_count_delta"] == 6.0
    assert report["delta"]["avg_capability_plan_score_delta"] == 12.0
    assert report["delta"]["rlm_trace_present_rate_delta"] == 0.5
    assert report["b"]["summary"]["avg_rlm_trace_quality_score"] == 40.0
    assert report["delta"]["avg_rlm_trace_quality_score_delta"] == 40.0
    coverage = report["capability_coverage"]["b"]
    assert coverage["hyper"]["selected_rate"] == 0.5
    assert coverage["hyper"]["invoked_rate"] == 0.5
    assert coverage["swarm"]["evidence_rate"] == 0.0
    assert coverage["drone"]["selected_rate"] == 0.0
    assert coverage["nightshift"]["selected_rate"] == 0.5
    assert coverage["nightshift"]["gate_rate"] == 0.0
    assert coverage["autoreason"]["evidence_rate"] == 0.0
    assert coverage["ddtree"]["invoked_rate"] == 0.5
    assert coverage["ultra_review"]["gate_rate"] == 0.5
    assert coverage["rlm"]["gate_rate"] == 0.5
    assert coverage["ultra_review"]["public_safe"] is False
    assert report["rule_lifecycle"][0]["rule_id"] == "verified-delivery-governance"
    assert report["rule_lifecycle"][0]["recommended_state"] == "active"
    assert report["rule_lifecycle"][1]["rule_id"] == "rlm-trace"
    assert report["by_category"]["bugfix"]["solve_rate_delta"] == 1.0
    assert report["by_category"]["feature"]["patch_success_rate_delta"] == 1.0
    assert report["by_repo_kind"]["neutral_fixture"]["solve_rate_delta"] == 1.0


def test_ab_eval_capability_coverage_counts_planned_msa_selection(tmp_path):
    dataset_a = tmp_path / "a.jsonl"
    dataset_b = tmp_path / "b.jsonl"
    dataset_a.write_text('{"task_id":"a","semantic_status":"UNVERIFIED"}\n', encoding="utf-8")
    dataset_b.write_text(
        json.dumps(
            {
                "task_id": "a",
                "semantic_status": "VERIFIED",
                "capability_plan_selected": ["swarm", "drone", "nightshift"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = compare_datasets("without", load_runs(dataset_a), "with", load_runs(dataset_b))
    coverage = report["capability_coverage"]["b"]
    assert coverage["swarm"]["selected_rate"] == 1.0
    assert coverage["drone"]["selected_rate"] == 1.0
    assert coverage["nightshift"]["selected_rate"] == 1.0
    assert coverage["swarm"]["public_safe"] is False


def test_ab_eval_prefers_capability_receipts_over_legacy_inference(tmp_path):
    dataset_a = tmp_path / "a.jsonl"
    dataset_b = tmp_path / "b.jsonl"
    dataset_a.write_text('{"task_id":"a","semantic_status":"UNVERIFIED"}\n', encoding="utf-8")
    dataset_b.write_text(
        json.dumps(
            {
                "task_id": "a",
                "semantic_status": "VERIFIED",
                "capability_plan_selected": ["swarm"],
                "capability_swarm_used": True,
                "capability_swarm_evidence_count": 3,
                "capability_claim_verified": True,
                "capability_receipts": [
                    {
                        "name": "swarm",
                        "selected": True,
                        "invoked": False,
                        "evidence_present": False,
                        "gate_passed": False,
                        "outcome_contributed": False,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = compare_datasets("without", load_runs(dataset_a), "with", load_runs(dataset_b))
    coverage = report["capability_coverage"]["b"]
    assert coverage["swarm"]["source"] == "capability_receipts"
    assert coverage["swarm"]["selected_rate"] == 1.0
    assert coverage["swarm"]["invoked_rate"] == 0.0
    assert coverage["swarm"]["evidence_rate"] == 0.0
    assert coverage["swarm"]["gate_rate"] == 0.0
    assert coverage["swarm"]["public_safe"] is False


def test_ab_eval_counts_trust_mismatch_rate(tmp_path):
    dataset_a = tmp_path / "trust_a.json"
    dataset_b = tmp_path / "trust_b.json"
    dataset_a.write_text(
        json.dumps(
            [
                {"semantic_status": "VERIFIED", "report_trust_mismatch": False},
                {"semantic_status": "VERIFIED", "report_trust_mismatch": True},
            ]
        ),
        encoding="utf-8",
    )
    dataset_b.write_text(
        json.dumps(
            [
                {"semantic_status": "VERIFIED", "report_trust_mismatch": False},
                {"semantic_status": "VERIFIED", "report_trust_mismatch": False},
            ]
        ),
        encoding="utf-8",
    )
    report = compare_datasets("a", load_runs(dataset_a), "b", load_runs(dataset_b))
    assert report["a"]["summary"]["trust_mismatch_rate"] == 0.5
    assert report["b"]["summary"]["trust_mismatch_rate"] == 0.0
    assert report["delta"]["trust_mismatch_rate_delta"] == -0.5


def test_ab_eval_treats_null_semantic_status_as_missing_and_falls_back_to_status(tmp_path):
    dataset = tmp_path / "rows.json"
    dataset.write_text(
        json.dumps(
            [
                {"semantic_status": None, "status": "SUCCESS"},
                {"semantic_status": "VERIFIED", "status": "FAILED"},
            ]
        ),
        encoding="utf-8",
    )
    report = compare_datasets("x", load_runs(dataset), "y", load_runs(dataset))
    assert report["a"]["summary"]["solve_rate"] == 1.0
    assert report["a"]["summary"]["semantic_verified_rate"] == 0.5


def test_ab_eval_reports_hard_success_rate(tmp_path):
    dataset_a = tmp_path / "hard_a.json"
    dataset_b = tmp_path / "hard_b.json"
    dataset_a.write_text(
        json.dumps(
            [
                {"difficulty": "hard", "semantic_status": "UNVERIFIED"},
                {"difficulty": "easy", "semantic_status": "VERIFIED"},
            ]
        ),
        encoding="utf-8",
    )
    dataset_b.write_text(
        json.dumps(
            [
                {"difficulty": "hard", "semantic_status": "VERIFIED"},
                {"difficulty": "easy", "semantic_status": "VERIFIED"},
            ]
        ),
        encoding="utf-8",
    )
    report = compare_datasets("gemini_flash", load_runs(dataset_a), "gemini_flash_nexus", load_runs(dataset_b))
    assert report["a"]["summary"]["hard_success_rate"] == 0.0
    assert report["b"]["summary"]["hard_success_rate"] == 1.0
    assert report["delta"]["hard_success_rate_delta"] == 1.0
    assert report["delta"]["nexus_lift"] == 1.0


def test_ab_eval_marks_relative_lift_undefined_when_baseline_zero(tmp_path):
    dataset_a = tmp_path / "zero_a.json"
    dataset_b = tmp_path / "zero_b.json"
    dataset_a.write_text(json.dumps([{"semantic_status": "UNVERIFIED"}]), encoding="utf-8")
    dataset_b.write_text(json.dumps([{"semantic_status": "VERIFIED"}]), encoding="utf-8")
    report = compare_datasets("gemini_flash", load_runs(dataset_a), "gemini_flash_nexus", load_runs(dataset_b))
    assert report["delta"]["solve_rate_delta"] == 1.0
    assert report["delta"]["nexus_lift"] is None


def test_ab_eval_reports_formal_nexus_treatment_validity(tmp_path):
    dataset_a = tmp_path / "formal_a.json"
    dataset_b = tmp_path / "formal_b.json"
    dataset_a.write_text(json.dumps([{"task_id": "base", "semantic_status": "VERIFIED"}]), encoding="utf-8")
    dataset_b.write_text(
        json.dumps(
            [
                {
                    "task_id": "valid",
                    "semantic_status": "VERIFIED",
                    "model_calls": 1,
                    "model_uses_nexus": True,
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "nexus_usage_valid": True,
                    "pillar_lancedb_active": True,
                    "pillar_memory_active": True,
                    "pillar_mempalace_active": True,
                    "pillar_belief_active": True,
                    "pillar_artifact_active": True,
                    "phase_p": "route_built",
                    "phase_x": "retrieval_checked",
                    "phase_d": "guard_decision",
                    "phase_r": "hyper_executed",
                    "phase_a": "artifact_verified",
                    "phase_c": "closure_written",
                    "capability_claim_verified": True,
                },
                {
                    "task_id": "invalid",
                    "semantic_status": "VERIFIED",
                    "model_calls": 0,
                    "model_uses_nexus": False,
                    "gemini_uses_nexus": False,
                    "nexus_context_delivered": False,
                    "nexus_usage_valid": False,
                    "pillar_lancedb_active": True,
                    "phase_p": "route_built",
                    "capability_claim_verified": False,
                },
            ]
        ),
        encoding="utf-8",
    )

    report = compare_datasets("gemini_flash", load_runs(dataset_a), "gemini_flash_nexus", load_runs(dataset_b))
    formal = report["formal_treatment"]
    assert formal["valid_count"] == 1
    assert formal["valid_rate"] == 0.5
    assert formal["invalid_count"] == 1
    assert formal["invalid_task_ids"] == ["invalid"]
    assert "model_calls_zero" in formal["invalid_rows"][0]["issues"]
    assert "model_uses_nexus_false" in formal["invalid_rows"][0]["issues"]
    assert "gemini_uses_nexus_false" not in formal["invalid_rows"][0]["issues"]
    assert "nexus_context_not_delivered" in formal["invalid_rows"][0]["issues"]
    assert "nexus_usage_invalid" in formal["invalid_rows"][0]["issues"]
    assert "claim_not_verified" in formal["invalid_rows"][0]["issues"]
