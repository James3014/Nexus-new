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
                        "attempt_count": 2,
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
                        "artifact_verification_only": True,
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
    assert report["a"]["summary"]["avg_total_tokens_measured_only"] == 300.0
    assert report["b"]["summary"]["nexus_usage_valid_rate"] == 0.5
    assert report["b"]["summary"]["gemini_uses_nexus_rate"] == 0.5
    assert report["b"]["summary"]["nexus_rescue_rate"] == 0.5
    assert report["b"]["summary"]["gemini_patch_pass_rate"] == 0.0
    assert report["b"]["summary"]["phase_completion_rate"] == 0.5
    assert report["b"]["summary"]["claim_verified_rate"] == 0.5
    assert report["b"]["summary"]["patch_success_count"] == 1
    assert report["b"]["summary"]["patch_success_rate"] == 0.5
    assert report["b"]["summary"]["verification_only_rate"] == 0.5
    assert report["b"]["summary"]["mutation_required_rate"] == 0.5
    assert report["b"]["summary"]["mutation_success_rate"] == 1.0
    assert report["delta"]["nexus_usage_valid_rate_delta"] == 0.5
    assert report["delta"]["patch_success_rate_delta"] == 0.5
    assert report["delta"]["verification_only_rate_delta"] == 0.5
    assert report["by_category"]["bugfix"]["solve_rate_delta"] == 1.0
    assert report["by_category"]["feature"]["patch_success_rate_delta"] == 1.0
    assert report["by_repo_kind"]["neutral_fixture"]["solve_rate_delta"] == 1.0


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
    assert "gemini_uses_nexus_false" in formal["invalid_rows"][0]["issues"]
    assert "nexus_context_not_delivered" in formal["invalid_rows"][0]["issues"]
    assert "nexus_usage_invalid" in formal["invalid_rows"][0]["issues"]
    assert "claim_not_verified" in formal["invalid_rows"][0]["issues"]
