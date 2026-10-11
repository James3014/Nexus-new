"""Real-component tests for `nexus skills list/sync` (the unit tests use fakes)."""

from pathlib import Path

from scripts.engine.commands import registry_actions


def _write_skill(root: Path, name: str) -> None:
    skill_dir = root / ".agents" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: demo skill for tests\n---\nbody\n",
        encoding="utf-8",
    )


def test_skills_sync_then_list_with_real_registry(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _write_skill(home, "alpha")
    repo = tmp_path / "repo"
    repo.mkdir()

    first = registry_actions.sync_external_skills(repo)
    second = registry_actions.sync_external_skills(repo)
    rows = registry_actions.get_skills_list(repo)

    assert (first.added, first.updated) == (1, 0)
    assert (second.added, second.updated) == (0, 1)
    assert [(r.skill_id, r.name, r.origin_type) for r in rows] == [
        ("external::alpha", "alpha", "external-skill-md")
    ]


def test_skills_list_empty_registry(tmp_path):
    assert registry_actions.get_skills_list(tmp_path) == []
