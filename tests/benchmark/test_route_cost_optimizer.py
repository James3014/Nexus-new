from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.route_cost_optimizer import build_longtail_cost_recommendations, build_optimizer_plan


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_optimizer_promotes_verified_wall_improvement(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "schema_version": "baseline",
        "rows": [
            {
                "task_id": "evidence-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 100,
                "with_tokens": 50000,
                "without_semantic": "VERIFIED",
                "without_status": "SUCCESS",
            }
        ],
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "evidence-001",
                "task_type": "public_feature",
                "difficulty": "hard",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 40,
                "total_tokens": 49000,
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "nexus_winner_source": "model_patch",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "evidence-001", "semantic_status": "VERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"promote_cost_tune": 1}
    assert out["promoted_policy"]["candidate_cap_overrides"] == {}
    assert out["promoted_policy"]["feature_rules"][0]["match"] == {"task_type": "public_feature", "difficulty": "hard"}
    assert out["promoted_policy"]["feature_rules"][0]["controls"] == {"candidate_cap": 1}
    assert out["next_required_action"] == "promote_cost_policy_then_rerun_12_task_fail_fast_loop"
    assert out["cost_truth_table"][0]["candidate_effective_wall_sec"] == 40
    assert out["promoted_policy"]["promotion_gate"]["runner_overhead_polluted"] is False


def test_longtail_recommendations_preserve_ddtree_floor_and_governance_gates() -> None:
    ledger = {
        "schema": "nexus_route_cost_ledger_v1",
        "arms": {
            "with_nexus": {
                "top_phase_wall_offenders": [
                    {
                        "task_id": "route-oracle-ddtree-001",
                        "task_capability": "ddtree",
                        "task_type": "public_test_repair",
                        "dominant_phase": "R",
                    }
                ]
            }
        },
    }

    out = build_longtail_cost_recommendations(ledger)

    rec = out["recommendations"][0]
    assert rec["controls"] == {"context_mode": "compact", "max_rounds": 1, "candidate_cap": 3}
    assert "ddtree" in rec["safety_floor"]
    assert {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"} <= set(rec["safety_floor"])
    assert out["promotion_gate"]["requires_same_model_rerun"] is True


def test_optimizer_holds_runner_overhead_polluted_rows(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "schema_version": "baseline",
        "rows": [
            {
                "task_id": "context-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 100,
                "with_tokens": 50000,
                "without_semantic": "UNVERIFIED",
                "without_status": "FAILED",
            }
        ],
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "context-001",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 181.5,
                "cli_elapsed_sec": 3.5,
                "runner_overhead_sec": 178.0,
                "runner_overhead_polluted": True,
                "total_tokens": 49000,
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "nexus_winner_source": "model_patch",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "context-001", "semantic_status": "UNVERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"hold_runner_overhead_polluted": 1}
    assert out["promoted_policy"]["candidate_cap_overrides"] == {}
    assert out["promoted_policy"]["hold_tasks"] == []
    assert out["promoted_policy"]["legacy_task_policy_source_ids"]["hold_task_ids"] == ["context-001"]
    assert out["next_required_action"] == "rerun_polluted_cost_rows_inprocess_before_promotion"
    assert out["cost_truth_table"][0]["candidate_effective_wall_sec"] == 3.5
    assert out["cost_truth_table"][0]["candidate_runner_overhead_polluted"] is True
    assert out["promoted_policy"]["promotion_gate"]["runner_overhead_polluted"] is True


def test_optimizer_promotes_clean_retry_attempt_despite_outer_wall_pollution(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "rows": [
            {
                "task_id": "context-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 100,
                "with_tokens": 50000,
                "without_semantic": "UNVERIFIED",
                "without_status": "FAILED",
            }
        ],
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "context-001",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 254,
                "runner_overhead_polluted": True,
                "model_attempt_wall_sec": 35,
                "model_attempt_runner_overhead_polluted": False,
                "total_tokens": 42681,
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "stats",
                "nexus_winner_source": "nexus_llm_baseline",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "context-001", "semantic_status": "UNVERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"promote_cost_tune": 1}
    assert out["decisions"][0]["wall_delta_pct"] == -65.0
    assert out["decisions"][0]["clean_model_cost_evidence"] is True


def test_optimizer_holds_unreliable_local_fallback(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "rows": [
            {
                "task_id": "repair-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 50,
                "with_tokens": 50000,
                "without_semantic": "UNVERIFIED",
                "without_status": "FAILED",
            }
        ]
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "repair-001",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 40,
                "total_tokens": 384,
                "model_calls": 1,
                "token_capture_status": "estimated",
                "nexus_winner_source": "local",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "repair-001", "semantic_status": "UNVERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"hold_not_model_uplift": 1}
    assert out["promoted_policy"]["hold_tasks"] == []
    assert out["promoted_policy"]["legacy_task_policy_source_ids"]["hold_task_ids"] == ["repair-001"]
    assert out["next_required_action"] == "rerun_hold_tasks_with_measured_model_tokens_or_keep_out_of_model_uplift_claim"


def test_optimizer_holds_measured_local_success_as_not_model_uplift(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "rows": [
            {
                "task_id": "repair-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 40,
                "with_tokens": 45000,
                "without_semantic": "UNVERIFIED",
                "without_status": "FAILED",
            }
        ]
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "repair-001",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 35,
                "total_tokens": 44000,
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "nexus_winner_source": "local_hidden_shadow",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "repair-001", "semantic_status": "UNVERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"hold_not_model_uplift": 1}
    assert out["promoted_policy"]["hold_tasks"] == []
    assert out["promoted_policy"]["legacy_task_policy_source_ids"]["hold_task_ids"] == ["repair-001"]
    assert out["decisions"][0]["cost_evidence_class"] == "rescue_only_local_success"


def test_optimizer_rejects_explicit_non_clean_model_cost_evidence(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "rows": [
            {
                "task_id": "context-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 100,
                "with_tokens": 50000,
                "without_semantic": "UNVERIFIED",
                "without_status": "FAILED",
            }
        ]
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "context-001",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 40,
                "total_tokens": 30000,
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "nexus_winner_source": "model_patch",
                "clean_model_cost_evidence": False,
                "cost_evidence_class": "rescue_only_local_success",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "context-001", "semantic_status": "UNVERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"hold_needs_trace_diagnosis": 1}
    assert out["decisions"][0]["measured_token_only"] is True
    assert out["decisions"][0]["clean_model_cost_evidence"] is False
    assert out["decisions"][0]["cost_evidence_class"] == "rescue_only_local_success"


def test_optimizer_requires_trace_diagnosis_for_verified_cost_regression(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "rows": [
            {
                "task_id": "context-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 50,
                "with_tokens": 45000,
                "without_semantic": "UNVERIFIED",
                "without_status": "FAILED",
            }
        ]
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "context-001",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 80,
                "total_tokens": 50000,
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "nexus_winner_source": "model_patch",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "context-001", "semantic_status": "UNVERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"hold_needs_trace_diagnosis": 1}
    assert out["next_required_action"] == "diagnose_hold_tasks_before_promoting_cost_policy"


def test_optimizer_holds_measured_status_without_provider_token_source(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "rows": [
            {
                "task_id": "context-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 100,
                "with_tokens": 50000,
                "without_semantic": "UNVERIFIED",
                "without_status": "FAILED",
            }
        ]
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "context-001",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 40,
                "total_tokens": 30000,
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "missing",
                "nexus_winner_source": "model_patch",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "context-001", "semantic_status": "UNVERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"hold_not_model_uplift": 1}
    assert out["decisions"][0]["measured_token_only"] is False
    assert out["decisions"][0]["candidate_token_source"] == "missing"


def test_optimizer_routes_bare_verified_rows_to_lite_when_cost_not_improved(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    baseline = {
        "rows": [
            {
                "task_id": "trust-001",
                "with_semantic": "VERIFIED",
                "with_status": "SUCCESS",
                "with_wall": 50,
                "with_tokens": 45000,
                "without_semantic": "VERIFIED",
                "without_status": "SUCCESS",
            }
        ]
    }
    _write_jsonl(
        candidate / "with_nexus_1.jsonl",
        [
            {
                "task_id": "trust-001",
                "task_type": "public_bugfix",
                "difficulty": "easy",
                "semantic_status": "VERIFIED",
                "status": "SUCCESS",
                "run_eligible": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 75,
                "total_tokens": 46000,
                "model_calls": 1,
                "token_measured": True,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "nexus_winner_source": "model_patch",
            }
        ],
    )
    _write_jsonl(candidate / "without_nexus_1.jsonl", [{"task_id": "trust-001", "semantic_status": "VERIFIED", "run_eligible": True}])

    out = build_optimizer_plan(baseline_aggregate=baseline, candidate_dir=candidate)

    assert out["decision_counts"] == {"route_lite_required": 1}
    assert out["promoted_policy"]["lite_route_tasks"] == []
    assert out["promoted_policy"]["legacy_task_policy_source_ids"]["lite_required_task_ids"] == ["trust-001"]
    assert out["promoted_policy"]["feature_rules"][0]["controls"] == {"candidate_cap": 1, "lite_route": True}
