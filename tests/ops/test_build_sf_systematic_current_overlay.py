from __future__ import annotations

from scripts.ops.build_sf_systematic_current_overlay import build_current_overlay


def _row(capability: str, current: str, challenger: str, verdict: str) -> dict:
    return {
        "capability": capability,
        "current_best": {
            "effective": True,
            "evidence_path": f"evidence/{capability}/current.json",
            "provider_token_measured": True,
            "receipt_path": f"receipt/{capability}/current",
            "skill_id": current,
            "skill_mount_contract_status": "PASS",
            "status": "PASS",
            "trust_mismatch": False,
        },
        "challenger": {
            "effective": True,
            "evidence_path": f"evidence/{capability}/challenger.json",
            "provider_token_measured": True,
            "receipt_path": f"receipt/{capability}/challenger",
            "skill_id": challenger,
            "skill_mount_contract_status": "PASS",
            "status": "PASS",
            "trust_mismatch": False,
        },
        "token_delta_challenger_minus_current": -1,
        "verdict": verdict,
        "wall_delta_challenger_minus_current": -1.0,
    }


def test_build_current_overlay_combines_replacements_and_held_current() -> None:
    overlay = build_current_overlay(
        {
            "schema": "test.rollup",
            "summary": {"capability_count": 2},
            "rows": [
                _row("repair_loop", "old-repair", "new-repair", "replace_candidate"),
                _row("forecast_pregate", "current-forecast", "new-forecast", "keep_current_best_cost_or_wall"),
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
    assert "plan_quality_gate" in overlay["capability_aliases"]["forecast_pregate"]
