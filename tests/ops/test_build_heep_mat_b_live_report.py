from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_heep_mat_b_live_report import build_heep_mat_b_live_report, main


def _result(
    *,
    arm: str,
    tokens: int,
    wall: float,
    mounts: int = 1,
    status: str = "PASS",
    replay_evidence: bool = False,
) -> dict:
    replay_fields = {}
    if replay_evidence:
        replay_fields = {
            "semantic_completed": status == "PASS",
            "runtime_classification": "verified_pass" if status == "PASS" else "return",
            "data_contract_violation": False,
            "cost_rubric_status": "PASS",
            "delivery_rubric_status": "PASS" if status == "PASS" else "RETURN",
            "evidence_rubric_status": "PASS",
        }
    return {
        "row_id": f"row::{arm}",
        "capability": "artifact_gate",
        "arm_id": arm,
        "status": status,
        "task_ref": {"task_id": "heep-mat-b-artifact_gate-001"},
        "benchmark_row": {
            "status": "SUCCESS" if status == "PASS" else "RETURN",
            "total_tokens": tokens,
            "phase_wall_total_sec": wall,
            "report_trust_mismatch": False,
            "runner_overhead_polluted": False,
            "model_attempt_runner_overhead_polluted": False,
            "skill_mount_count": mounts,
            "skill_mount_contract_status": "PASS",
            **replay_fields,
        },
        "ablation_gate_row": {
            "selected": True,
            "injected": True,
            "used": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
        },
    }


def test_heep_mat_b_report_keeps_single_when_efficiency_regresses() -> None:
    report = build_heep_mat_b_live_report(
        live_summary={
            "results": [
                _result(arm="mode_a_current_primary", tokens=100, wall=10.0),
                _result(arm="heep_multi_skill", tokens=120, wall=12.5, mounts=3),
            ]
        }
    )

    assert report["status"] == "PASS"
    assert report["summary"]["keep_single_count"] == 1
    comparison = report["comparisons"][0]
    assert comparison["verdict"] == "KEEP_SINGLE_PRIMARY"
    assert comparison["delta"]["token_delta"] == 20
    assert comparison["delta"]["wall_delta"] == 2.5
    assert comparison["delta"]["evidence_seal_count_delta"] == 2


def test_heep_mat_b_report_holds_when_final_reopen_evidence_missing() -> None:
    report = build_heep_mat_b_live_report(
        live_summary={
            "results": [
                _result(arm="mode_a_current_primary", tokens=100, wall=10.0),
                _result(arm="heep_multi_skill", tokens=90, wall=8.5, mounts=3),
            ]
        }
    )

    assert report["comparisons"][0]["verdict"] == "HOLD_MISSING_MAT_B_EVIDENCE"
    assert report["comparisons"][0]["reason_codes"] == ["missing_reopen_rate"]


def test_heep_mat_b_report_uses_deterministic_reopen_replay_proxy() -> None:
    report = build_heep_mat_b_live_report(
        live_summary={
            "results": [
                _result(arm="mode_a_current_primary", tokens=100, wall=10.0, replay_evidence=True),
                _result(arm="heep_multi_skill", tokens=90, wall=8.5, mounts=3, replay_evidence=True),
            ]
        }
    )

    comparison = report["comparisons"][0]
    assert comparison["verdict"] == "APPROVE_HEEP_MODE_CANDIDATE"
    assert comparison["baseline"]["reopen_rate"] == 0.0
    assert comparison["challenger"]["reopen_rate_source"] == "deterministic_receipt_replay_proxy"


def test_heep_mat_b_cli_writes_report(tmp_path: Path, capsys) -> None:
    live = tmp_path / "live_summary.json"
    output = tmp_path / "report.json"
    live.write_text(
        json.dumps(
            {
                "results": [
                    _result(arm="mode_a_current_primary", tokens=100, wall=10.0),
                    _result(arm="heep_multi_skill", tokens=120, wall=12.5, mounts=3),
                ]
            }
        ),
        encoding="utf-8",
    )

    rc = main(["--live-summary", str(live), "--output", str(output)])
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert captured["status"] == "PASS"
    assert captured["keep_single_count"] == 1
    assert output.exists()
