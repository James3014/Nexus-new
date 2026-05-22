from __future__ import annotations

from pathlib import Path

from scripts.ops.build_zero_trust_v2_physical_skill_evidence import build_zero_trust_v2_physical_skill_evidence


def _row(arm_type: str) -> dict:
    return {
        "row_id": f"row-{arm_type}",
        "capability_id": "codeintel",
        "skill_id": "code-skill",
        "source_skill_id": "code-skill",
        "arm_type": arm_type,
        "security_contract_version": "v2",
        "promotion_credit_source": "v2_only",
    }


def test_physical_skill_evidence_is_materialization_only_by_default(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("# Safe\n", encoding="utf-8")
    result = build_zero_trust_v2_physical_skill_evidence(
        replay_matrix={"rows": [_row("capability_only_v2"), _row("candidate_skill_v2"), _row("wrong_or_quarantined_skill_v2")]},
        command_specs={
            "specs": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "source_review": {"skill_path": str(skill)},
                    "command": ["python3", "-c", "print('ok')"],
                }
            ]
        },
        signing_secret="secret",
    )

    assert result["summary"]["command_ready_count"] == 1
    assert result["summary"]["materialization_only"] is True
    assert result["summary"]["promotion_credit_allowed"] is False
    assert result["summary"]["ready_for_manual_apply_count"] == 0
    assert result["summary"]["runtime_mutation_allowed"] is False
