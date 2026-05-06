from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.flash_baseline_summary import build_summary


def _write_jsonl(path: Path, rows: list[dict]):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_flash_baseline_summary_reports_rates_route_quality_and_public_safe(tmp_path: Path):
    without = [
        {
            "mode": "without_nexus",
            "task_id": "t1",
            "trial_index": 1,
            "status": "FAIL",
            "semantic_status": "FAILED",
            "run_eligible": True,
            "model_name": "gemini-3-flash-preview",
        }
    ]
    with_rows = [
        {
            "mode": "with_nexus",
            "task_id": "t1",
            "trial_index": 1,
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "run_eligible": True,
            "model_name": "gemini-3-flash-preview",
            "runtime_pruned_capabilities": {"autoreason": "candidate_factory_skipped"},
            "runtime_pruned_capability_count": 1,
            "capability_receipts": [
                {
                    "name": "judge_panel",
                    "selected": True,
                    "invoked": True,
                    "evidence_present": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                    "public_claim_safe": True,
                }
            ],
        }
    ]
    _write_jsonl(tmp_path / "without_nexus_1.jsonl", without)
    _write_jsonl(tmp_path / "with_nexus_1.jsonl", with_rows)

    summary = build_summary(output_dir=tmp_path, scope="1x1")

    assert summary["status"] == "PASS"
    assert summary["promotion_status"] == "PASS"
    assert summary["solve_rate"]["with_nexus"] == 1.0
    assert summary["semantic_verified_rate"]["delta"] == 1.0
    assert summary["public_safe"]["public_safe"] == ["judge_panel"]
    assert summary["route_quality"]["selected_to_invoked_rate"] == 1.0
    assert summary["runtime_pruning"]["with_nexus"] == 1.0
    assert summary["runtime_pruning"]["avg_with_nexus"] == 1.0
    assert summary["runtime_pruning"]["warnings"] == ["runtime_pruning_above_warning_threshold"]
    assert summary["runtime_pruning"]["target_failures"] == ["runtime_pruning_above_target_threshold"]
    assert summary["infra_invalid"]["with_nexus"] == 0


def test_flash_baseline_summary_marks_infra_invalid_rows(tmp_path: Path):
    _write_jsonl(
        tmp_path / "without_nexus_1.jsonl",
        [
            {
                "mode": "without_nexus",
                "task_id": "t1",
                "trial_index": 1,
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "run_eligible": False,
                "infra_invalid_reason": "quota_exhausted",
            }
        ],
    )
    _write_jsonl(
        tmp_path / "with_nexus_1.jsonl",
        [
            {
                "mode": "with_nexus",
                "task_id": "t1",
                "trial_index": 1,
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "run_eligible": True,
                "capability_receipts": [],
            }
        ],
    )

    summary = build_summary(output_dir=tmp_path, scope="1x1")

    assert summary["status"] == "INFRA_INVALID"
    assert summary["promotion_status"] == "INFRA_INVALID"
    assert summary["infra_invalid"]["without_nexus"] == 1
    assert summary["infra_invalid"]["reasons"] == ["quota_exhausted"]


def test_flash_baseline_summary_marks_no_uplift(tmp_path: Path):
    row = {
        "task_id": "t1",
        "trial_index": 1,
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "run_eligible": True,
        "model_name": "gemini-3-flash-preview",
        "token_measured": True,
        "token_capture_status": "measured",
        "capability_receipts": [
            {
                "name": "judge_panel",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
            }
        ],
    }
    _write_jsonl(tmp_path / "without_nexus_1.jsonl", [{**row, "mode": "without_nexus"}])
    _write_jsonl(tmp_path / "with_nexus_1.jsonl", [{**row, "mode": "with_nexus"}])

    summary = build_summary(output_dir=tmp_path, scope="1x1")

    assert summary["status"] == "NO_UPLIFT"
    assert summary["semantic_verified_rate"]["delta"] == 0.0


def test_flash_baseline_summary_marks_regression(tmp_path: Path):
    without = {
        "task_id": "t1",
        "trial_index": 1,
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "run_eligible": True,
        "model_name": "gemini-3-flash-preview",
        "token_measured": True,
        "token_capture_status": "measured",
    }
    with_row = {
        **without,
        "mode": "with_nexus",
        "status": "FAILED",
        "semantic_status": "FAILED",
        "capability_receipts": [],
    }
    _write_jsonl(tmp_path / "without_nexus_1.jsonl", [{**without, "mode": "without_nexus"}])
    _write_jsonl(tmp_path / "with_nexus_1.jsonl", [with_row])

    summary = build_summary(output_dir=tmp_path, scope="1x1")

    assert summary["status"] == "REGRESSION"
    assert summary["semantic_verified_rate"]["delta"] == -1.0
