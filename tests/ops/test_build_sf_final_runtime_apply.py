from __future__ import annotations

from scripts.ops.build_sf_final_runtime_apply import build_sf_final_runtime_apply


def _comparison(capability: str, current: str, candidate: str, token_delta: int, wall_delta: float) -> dict:
    return {
        "capability": capability,
        "current_skill_id": current,
        "candidate_skill_id": candidate,
        "verdict": "REPLACE_PRIMARY_LIVE_APPROVED",
        "candidate": {
            "status": "PASS",
            "delivery_status": "SUCCESS",
            "receipt_chain_pass": True,
            "trust_mismatch": False,
            "skill_mount_contract_status": "PASS",
            "infra_invalid_reason": "",
            "evidence_path": f"evidence/{candidate}.json",
            "receipt_path": f"receipt/{candidate}",
        },
        "delta": {"token_delta": token_delta, "wall_delta": wall_delta},
    }


def _status(skill_id: str, capability: str) -> dict:
    return {
        "name": skill_id,
        "path": f"/repo/.agents/skills/{skill_id}/SKILL.md",
        "root": "test",
        "skill_status": "nexus_curated_candidate",
        "test_level": "test",
        "action": "ablation_only_compare",
        "capability_mount": capability,
    }


def test_sf_final_runtime_apply_selects_best_clean_replacement_and_keeps_rest() -> None:
    result = build_sf_final_runtime_apply(
        current_overlay={
            "status": "PASS",
            "primary_skill_by_capability": {"repair_loop": "old-repair", "codeintel": "old-code"},
        },
        live_report={
            "summary": {"expected_candidate_count": 2, "comparison_count": 2, "pending_candidate_count": 0},
            "comparisons": [
                _comparison("repair_loop", "old-repair", "new-repair-a", -5, -10.0),
                _comparison("repair_loop", "old-repair", "new-repair-b", -10, -1.0),
            ],
        },
        status_reports=[
            {"skills": [_status("new-repair-a", "repair_loop"), _status("new-repair-b", "repair_loop")]},
            {"skills": [_status("old-code", "codeintel")]},
        ],
    )

    assert result["decision"]["status"] == "PASS"
    assert result["decision"]["summary"]["applied_replacement_count"] == 1
    assert result["overlay"]["primary_skill_by_capability"] == {
        "codeintel": "old-code",
        "repair_loop": "new-repair-b",
    }
    assert result["skill_status"]["summary"]["skill_count"] == 2
    applied = result["decision"]["applied_primary"][0]
    assert applied["selection_rule"] == "min_token_delta_then_wall_delta_among_clean_live_approved"


def test_sf_final_runtime_apply_blocks_missing_status() -> None:
    result = build_sf_final_runtime_apply(
        current_overlay={"status": "PASS", "primary_skill_by_capability": {"repair_loop": "old-repair"}},
        live_report={
            "summary": {"expected_candidate_count": 1, "comparison_count": 1, "pending_candidate_count": 0},
            "comparisons": [_comparison("repair_loop", "old-repair", "new-repair", -5, -1.0)],
        },
        status_reports=[{"skills": []}],
    )

    assert result["decision"]["status"] == "RETURN"
    assert result["overlay"]["runtime_update_allowed"] is False
    assert "repair_loop:new-repair:missing_skill_status" in result["decision"]["blockers"]
