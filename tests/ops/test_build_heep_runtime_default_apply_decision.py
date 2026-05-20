from __future__ import annotations

from scripts.ops.build_heep_runtime_default_apply_decision import build_heep_runtime_default_apply_decision


def test_heep_runtime_default_apply_decision_writes_assembly_overlay() -> None:
    result = build_heep_runtime_default_apply_decision(
        current_overlay={
            "primary_skill_by_capability": {"codeintel": "solo-codeintel", "repair_loop": "tdd"},
            "candidate_primary_skill_by_capability": {"codeintel": "solo-codeintel", "repair_loop": "tdd"},
        },
        reviewed_gate={
            "status": "PASS",
            "cases": [
                {
                    "capability": "codeintel",
                    "selected_mode": "Mode B (Guard)",
                    "status": "PASS",
                    "skill_checks": [
                        {"skill_id": "code-scout", "status": "PASS"},
                        {"skill_id": "code-audit", "status": "PASS"},
                    ],
                }
            ],
        },
    )

    decision = result["decision"]
    overlay = result["overlay"]
    assert decision["status"] == "PASS"
    assert decision["summary"]["runtime_update_allowed"] is True
    assert overlay["primary_skill_by_capability"]["codeintel"] == "code-scout"
    assert overlay["primary_skill_by_capability"]["repair_loop"] == "tdd"
    assert overlay["skill_assembly_by_capability"]["codeintel"] == [
        {"role": "skill_1", "skill_id": "code-scout"},
        {"role": "skill_2", "skill_id": "code-audit"},
    ]
    assert overlay["public_benchmark_allowed"] is False


def test_heep_runtime_default_apply_decision_blocks_failed_review_gate() -> None:
    result = build_heep_runtime_default_apply_decision(
        current_overlay={"primary_skill_by_capability": {"codeintel": "solo-codeintel"}},
        reviewed_gate={"status": "RETURN", "cases": []},
    )

    assert result["decision"]["status"] == "RETURN"
    assert result["decision"]["summary"]["runtime_update_allowed"] is False
    assert "reviewed_apply_gate_not_pass" in result["decision"]["blockers"]
