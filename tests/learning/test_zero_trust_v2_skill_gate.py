from __future__ import annotations

from pathlib import Path

from nexus.learning.zero_trust_v2_skill_gate import build_skill_command_spec, resolve_skill_path, scan_skill_source


def test_resolve_skill_path_finds_skill_under_configured_root(tmp_path: Path) -> None:
    skill_dir = tmp_path / "safe-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Safe\n", encoding="utf-8")

    assert resolve_skill_path("safe-skill", roots=(tmp_path,)) == skill_dir / "SKILL.md"


def test_scan_skill_source_blocks_forbidden_tokens(tmp_path: Path) -> None:
    source = tmp_path / "SKILL.md"
    source.write_text("Run subprocess for convenience", encoding="utf-8")

    result = scan_skill_source("unsafe", skill_path=source)

    assert result["status"] == "BLOCKED_BY_POLICY"
    assert "FORBIDDEN_TOKEN:subprocess" in result["failed_security_contract_rules"]


def test_build_skill_command_spec_blocks_missing_source() -> None:
    result = build_skill_command_spec({"capability_id": "claim_gate", "skill_id": "missing-skill"})

    assert result["command"] == []
    assert result["promotion_credit_allowed"] is False
    assert result["source_review"]["failed_security_contract_rules"] == ["SKILL_SOURCE_NOT_FOUND"]
