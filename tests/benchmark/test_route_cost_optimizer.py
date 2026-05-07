from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.route_cost_optimizer import build_optimizer_plan


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
    assert out["promoted_policy"]["candidate_cap_overrides"] == {"evidence-001": 1}
    assert out["next_required_action"] == "promote_cost_policy_then_rerun_12_task_fail_fast_loop"


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
    assert out["promoted_policy"]["hold_tasks"] == ["repair-001"]
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
    assert out["promoted_policy"]["hold_tasks"] == ["repair-001"]


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
    assert out["promoted_policy"]["lite_route_tasks"] == ["trust-001"]
