from __future__ import annotations

from scripts.ops.build_sf_systematic_current_overlay import build_current_overlay


def _row(
    capability: str,
    current: str,
    challenger: str,
    verdict: str,
    *,
    token_delta: int = -1,
    wall_delta: float = -1.0,
) -> dict:
    return {
        "capability": capability,
        "current_best": {
            "benchmark_status": "SUCCESS",
            "effective": True,
            "evidence_path": f"evidence/{capability}/current.json",
            "model_calls": 2,
            "provider_token_measured": True,
            "receipt_path": f"receipt/{capability}/current",
            "semantic_status": "VERIFIED",
            "skill_id": current,
            "skill_mount_contract_status": "PASS",
            "status": "PASS",
            "trust_mismatch": False,
        },
        "challenger": {
            "benchmark_status": "SUCCESS",
            "effective": True,
            "evidence_path": f"evidence/{capability}/challenger.json",
            "model_calls": 2,
            "provider_token_measured": True,
            "receipt_path": f"receipt/{capability}/challenger",
            "semantic_status": "VERIFIED",
            "skill_id": challenger,
            "skill_mount_contract_status": "PASS",
            "status": "PASS",
            "trust_mismatch": False,
        },
        "token_delta_challenger_minus_current": token_delta,
        "verdict": verdict,
        "wall_delta_challenger_minus_current": wall_delta,
    }


def test_build_current_overlay_combines_replacements_and_held_current() -> None:
    overlay = build_current_overlay(
        {
            "schema": "test.rollup",
            "summary": {"capability_count": 2},
            "rows": [
                _row("repair_loop", "old-repair", "new-repair", "replace_candidate"),
                _row(
                    "forecast_pregate",
                    "current-forecast",
                    "new-forecast",
                    "keep_current_best_cost_or_wall",
                    wall_delta=1.0,
                ),
            ],
        }
    )

    assert overlay["status"] == "PASS"
    assert overlay["runtime_update_allowed"] is True
    assert overlay["public_benchmark_allowed"] is False
    assert overlay["primary_skill_by_capability"] == {
        "forecast_pregate": "current-forecast",
        "repair_loop": "new-repair",
    }
    assert overlay["candidate_primary_skill_by_capability"] == overlay["primary_skill_by_capability"]
    assert overlay["summary"]["replace_candidate_count"] == 1
    assert overlay["summary"]["keep_current_best_count"] == 1
    assert overlay["summary"]["replacement_hold_count"] == 0
    assert "plan_quality_gate" in overlay["capability_aliases"]["forecast_pregate"]


def test_build_current_overlay_blocks_raw_replace_when_cost_truth_is_missing() -> None:
    row = _row("repair_loop", "old-repair", "new-repair", "replace_candidate")
    row["challenger"]["provider_token_measured"] = False

    overlay = build_current_overlay(
        {
            "schema": "test.rollup",
            "summary": {"capability_count": 1},
            "rows": [row],
        }
    )

    assert overlay["status"] == "BLOCKED"
    assert overlay["runtime_update_allowed"] is False
    assert overlay["primary_skill_by_capability"] == {"repair_loop": "old-repair"}
    assert overlay["selected_primary"][0]["decision"] == "hold"
    assert overlay["selected_primary"][0]["replacement_decision"] == "HOLD"
    assert "blocked_by_missing_cost_truth:challenger" in overlay["selected_primary"][0]["replacement_blockers"]
    assert "repair_loop:replacement_gate:blocked_by_missing_cost_truth:challenger" in overlay["blockers"]
