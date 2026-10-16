from scripts.ops.build_sf_final_live_compare_report import build_sf_final_live_compare_report


def _result(*, arm_id: str, skill_id: str, tokens: int, wall: float, status: str = "SUCCESS") -> dict:
    return {
        "row_id": f"repair::{arm_id}::{skill_id}",
        "status": "PASS",
        "capability": "repair_loop",
        "arm_id": arm_id,
        "skill_id": skill_id,
        "candidate_skill_id": "" if arm_id == "current_primary_skill" else skill_id,
        "task_ref": {"task_id": "sf-final-all-live-compare-repair_loop-001"},
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


def _return_result(*, arm_id: str, skill_id: str, reason: str) -> dict:
    row = _result(arm_id=arm_id, skill_id=skill_id, tokens=100, wall=10.0)
    row["status"] = "RETURN"
    row["reason"] = reason
    return row


def test_build_sf_final_live_compare_report_approves_each_clean_candidate():
    matrix = {
        "rows": [
            {"capability": "repair_loop", "arm_id": "candidate_skill", "candidate_skill_id": "candidate-a"},
            {"capability": "repair_loop", "arm_id": "candidate_skill", "candidate_skill_id": "candidate-b"},
        ]
    }
    report = build_sf_final_live_compare_report(
        live_summary={
            "results": [
                _result(arm_id="current_primary_skill", skill_id="current", tokens=100, wall=10.0),
                _result(arm_id="candidate_skill", skill_id="candidate-a", tokens=90, wall=9.0),
                _result(arm_id="candidate_skill", skill_id="candidate-b", tokens=80, wall=8.0),
            ]
        },
        matrix=matrix,
    )

    assert report["status"] == "PASS"
    assert report["summary"]["expected_candidate_count"] == 2
    assert report["summary"]["pending_candidate_count"] == 0
    assert report["summary"]["replace_live_approved_count"] == 2


def test_build_sf_final_live_compare_report_lists_pending_candidates():
    matrix = {
        "rows": [
            {"capability": "repair_loop", "arm_id": "candidate_skill", "candidate_skill_id": "candidate-a"},
            {"capability": "repair_loop", "arm_id": "candidate_skill", "candidate_skill_id": "candidate-b"},
        ]
    }
    report = build_sf_final_live_compare_report(
        live_summary={
            "results": [
                _result(arm_id="current_primary_skill", skill_id="current", tokens=100, wall=10.0),
                _result(arm_id="candidate_skill", skill_id="candidate-a", tokens=90, wall=9.0),
            ]
        },
        matrix=matrix,
    )

    assert report["summary"]["pending_candidate_count"] == 1
    assert report["pending_candidates"] == [
        {"capability": "repair_loop", "candidate_skill_id": "candidate-b", "reason": "not_yet_live_executed"}
    ]


def test_build_sf_final_live_compare_report_blocks_on_returned_baseline():
    matrix = {
        "rows": [
            {"capability": "repair_loop", "arm_id": "candidate_skill", "candidate_skill_id": "candidate-a"},
        ]
    }
    report = build_sf_final_live_compare_report(
        live_summary={
            "results": [
                _return_result(
                    arm_id="current_primary_skill",
                    skill_id="current",
                    reason="model_required_local_delivery_blocked",
                ),
                _result(arm_id="candidate_skill", skill_id="candidate-a", tokens=90, wall=9.0),
            ]
        },
        matrix=matrix,
    )

    assert report["status"] == "RETURN"
    assert report["blockers"] == [
        "repair_loop:current_primary_skill:current:model_required_local_delivery_blocked"
    ]
