from __future__ import annotations

from pathlib import Path

from scripts.ops.optimize_sf_primary_skill_descriptions import build_report


def _write_skill(root: Path, skill_id: str, description: str) -> Path:
    skill_dir = root / ".agents" / "skills" / skill_id
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        f"---\nname: {skill_id}\ndescription: {description}\n---\n\n# {skill_id}\n",
        encoding="utf-8",
    )
    return path


def test_optimizer_applies_only_hinted_primary_skills(tmp_path: Path) -> None:
    _write_skill(tmp_path, "diagnose", "Debug things.")
    untouched = _write_skill(tmp_path, "unhinted-skill", "General helper.")
    overlay = {
        "primary_skill_by_capability": {
            "memory": "diagnose",
            "xray": "diagnose",
            "external_productivity": "unhinted-skill",
        }
    }

    report = build_report(repo_root=tmp_path, overlay=overlay, max_apply=10, apply=True)

    assert report["summary"]["primary_skill_count"] == 2
    assert report["summary"]["evaluated_candidate_count"] == 1
    assert report["summary"]["skipped_no_domain_hint_count"] == 1
    assert report["summary"]["improved_candidate_count"] == 1
    assert report["summary"]["applied_count"] == 1
    assert report["applied_skills"] == ["diagnose"]
    assert "runtime evidence checks" in (tmp_path / ".agents/skills/diagnose/SKILL.md").read_text(encoding="utf-8")
    assert untouched.read_text(encoding="utf-8").splitlines()[2] == "description: General helper."
