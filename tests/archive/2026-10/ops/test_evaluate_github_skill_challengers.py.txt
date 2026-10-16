from __future__ import annotations

from pathlib import Path

from scripts.ops.evaluate_github_skill_challengers import build_report


def _write_skill(root: Path, skill_id: str, description: str) -> None:
    skill_dir = root / ".agents" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: {description}\n---\n\n# {skill_id}\n",
        encoding="utf-8",
    )


def _write_repo_skill(source_root: Path, repo: str, rel: str, description: str) -> None:
    path = source_root / repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: upstream-skill\ndescription: {description}\n---\n\n# Upstream\n",
        encoding="utf-8",
    )


def _source_root(tmp_path: Path) -> Path:
    source = tmp_path / "sources"
    _write_repo_skill(source, "andrej-karpathy-skills", "skills/karpathy-guidelines/SKILL.md", "Coding guidelines.")
    _write_repo_skill(source, "Skills-Security-Check", "SKILL.md", "Skill security scanner.")
    _write_repo_skill(source, "auto-skill", "SKILL.md", "Unsafe global rule mutating auto skill.")
    _write_repo_skill(source, "idea-reality-mcp", "skills/idea-check/SKILL.md", "Idea reality check.")
    return source


def test_github_challengers_are_candidate_only_and_rewrite_unsafe_auto_skill(tmp_path: Path) -> None:
    _write_skill(tmp_path, "current-learning", "Generic learning notes.")
    report = build_report(
        repo_root=tmp_path,
        source_root=_source_root(tmp_path),
        overlay={"primary_skill_by_capability": {"metabolism_resume": "current-learning"}},
        apply=True,
    )

    assert report["runtime_update_allowed"] is False
    assert report["public_benchmark_allowed"] is False
    auto = next(item for item in report["repo_reports"] if item["repo"] == "auto-skill")
    assert auto["original_rejected"] is True
    assert auto["generated_safe_candidate"] == "github-auto-skill-safe-learning"
    materialized = tmp_path / ".agents/skills/github-challengers/github-auto-skill-safe-learning/SKILL.md"
    assert materialized.exists()
    text = materialized.read_text(encoding="utf-8")
    assert '"runtime_eligible":false' in text
    assert "must not inherit its forced self-install or global-rule mutation behavior" in text


def test_replacement_requires_challenger_to_win_actual_fixture_ranking(tmp_path: Path) -> None:
    _write_skill(tmp_path, "weak-codeintel", "Generic helper.")
    report = build_report(
        repo_root=tmp_path,
        source_root=_source_root(tmp_path),
        overlay={"primary_skill_by_capability": {"codeintel": "weak-codeintel"}},
        apply=False,
    )

    comparison = next(item for item in report["comparisons"] if item["capability"] == "codeintel")
    assert comparison["challenger_skill"] == "github-karpathy-guidelines"
    assert comparison["decision"] == "REPLACE_CURRENT"
    assert report["replacement_candidates"] == {"codeintel": "github-karpathy-guidelines"}
