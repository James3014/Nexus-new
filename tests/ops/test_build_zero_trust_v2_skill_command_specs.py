from __future__ import annotations

from scripts.ops.build_zero_trust_v2_skill_command_specs import build_zero_trust_v2_skill_command_specs


def test_zero_trust_v2_skill_command_specs_filters_priority_and_blocks_missing_source() -> None:
    result = build_zero_trust_v2_skill_command_specs(
        backlog={
            "items": [
                {"capability_id": "claim_gate", "skill_id": "missing-p0", "priority": "P0"},
                {"capability_id": "codeintel", "skill_id": "missing-p1", "priority": "P1"},
            ]
        },
        priority="P0",
    )

    assert result["status"] == "PASS"
    assert result["summary"]["selected_candidate_count"] == 1
    assert result["summary"]["command_ready_count"] == 0
    assert result["summary"]["blocked_count"] == 1
    assert result["specs"][0]["capability_id"] == "claim_gate"
