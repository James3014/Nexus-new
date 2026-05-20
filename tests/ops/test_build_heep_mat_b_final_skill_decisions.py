from __future__ import annotations

from scripts.ops import build_heep_mat_b_final_skill_decisions as final_decisions


def test_final_decision_selects_multi_skill_for_non_cost_win(monkeypatch) -> None:
    monkeypatch.setattr(final_decisions, "_skill_paths", lambda: {"base": "base/SKILL.md", "extra": "extra/SKILL.md"})
    queue = {
        "rows": [
            {
                "capability": "xray",
                "baseline_arm": {"skill_ids": ["base"]},
                "challenger_arm": {"skill_ids": ["base", "extra"]},
            }
        ]
    }
    resolution = {
        "rows": [
            {
                "capability": "xray",
                "mode_decision": "MULTI_SKILL_NON_COST_WIN",
                "remaining_gate": ["provider-clean replay"],
            }
        ]
    }

    out = final_decisions.build_final_skill_decisions(
        live_compare_queue=queue,
        blocked_mode_resolution=resolution,
    )

    assert out["status"] == "PASS"
    assert out["summary"]["multi_skill_decision_count"] == 1
    assert out["decisions"][0]["decision"] == "USE_MULTI_SKILL"
    assert out["decisions"][0]["selected_skill_ids"] == ["base", "extra"]
    assert out["decisions"][0]["runtime_update_allowed"] is False


def test_final_decision_uses_single_primary_when_receipt_chain_missing(monkeypatch) -> None:
    monkeypatch.setattr(final_decisions, "_skill_paths", lambda: {"base": "base/SKILL.md", "extra": "extra/SKILL.md"})
    queue = {
        "rows": [
            {
                "capability": "drone",
                "baseline_arm": {"skill_ids": ["base"]},
                "challenger_arm": {"skill_ids": ["base", "extra"]},
            }
        ]
    }
    resolution = {
        "rows": [
            {
                "capability": "drone",
                "mode_decision": "UNDECIDED_RECEIPT_CHAIN_MISSING",
                "remaining_gate": ["executor receipt replay"],
            }
        ]
    }

    out = final_decisions.build_final_skill_decisions(
        live_compare_queue=queue,
        blocked_mode_resolution=resolution,
    )

    assert out["status"] == "PASS"
    assert out["summary"]["single_primary_fallback_count"] == 1
    assert out["decisions"][0]["decision"] == "USE_SINGLE_PRIMARY_FALLBACK"
    assert out["decisions"][0]["selected_skill_ids"] == ["base"]
