from scripts.ops.build_sf_final_live_compare_report import build_sf_final_live_compare_report


def _result(*, arm_id: str, skill_id: str, tokens: int, wall: float, status: str = "SUCCESS") -> dict:
    return {
        "row_id": f"repair::{arm_id}",
        "status": "PASS",
        "capability": "repair_loop",
        "arm_id": arm_id,
        "skill_id": skill_id,
        "task_ref": {"task_id": "sf-final-live-compare-repair_loop-001"},
        "benchmark_row": {
            "status": status,
            "total_tokens": tokens,
            "phase_wall_total_sec": wall,
            "skill_mount_contract_status": "PASS",
            "report_trust_mismatch": False,
        },
        "ablation_gate_row": {
            "selected": True,
            "injected": True,
            "used": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "evidence_path": "evidence.json",
            "receipt_path": "receipt",
        },
    }


def test_build_sf_final_live_compare_report_approves_candidate_when_cleaner():
    report = build_sf_final_live_compare_report(
        live_summary={
            "results": [
                _result(arm_id="current_primary_skill", skill_id="current", tokens=100, wall=10.0),
                _result(arm_id="candidate_skill", skill_id="candidate", tokens=90, wall=9.0),
            ]
        }
    )

    assert report["status"] == "PASS"
    assert report["summary"]["replace_live_approved_count"] == 1
    assert report["comparisons"][0]["verdict"] == "REPLACE_PRIMARY_LIVE_APPROVED"
    assert report["comparisons"][0]["delta"]["token_delta"] == -10


def test_build_sf_final_live_compare_report_holds_without_receipt_chain():
    candidate = _result(arm_id="candidate_skill", skill_id="candidate", tokens=90, wall=9.0)
    candidate["ablation_gate_row"]["outcome_contributed"] = False
    report = build_sf_final_live_compare_report(
        live_summary={
            "results": [
                _result(arm_id="current_primary_skill", skill_id="current", tokens=100, wall=10.0),
                candidate,
            ]
        }
    )

    assert report["summary"]["hold_count"] == 1
    assert report["comparisons"][0]["verdict"] == "HOLD_MISSING_LIVE_EVIDENCE"
    assert "candidate_receipt_chain_incomplete" in report["comparisons"][0]["reason_codes"]
