import json
from pathlib import Path

from nexus.core.router import SkillsRouter


def _write_inventory(project_root: Path, skill_id: str) -> None:
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "skills": {
            skill_id: {
                "phases": ["D"],
                "langs": ["*"],
                "triggers": ["debug"],
                "description": "test skill",
            }
        }
    }
    (scripts_dir / "skills_inventory.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_router_prefers_builtin_skill_artifact(tmp_path: Path) -> None:
    skill_id = "demo.skill"
    _write_inventory(tmp_path, skill_id)

    builtin_skill = tmp_path / "scripts" / "skills_builtin" / skill_id / "SKILL.md"
    builtin_skill.parent.mkdir(parents=True, exist_ok=True)
    builtin_skill.write_text("# builtin\n", encoding="utf-8")

    external_skill = tmp_path / "scripts" / skill_id / "SKILL.md"
    external_skill.parent.mkdir(parents=True, exist_ok=True)
    external_skill.write_text("# external\n", encoding="utf-8")

    router = SkillsRouter(project_root=str(tmp_path))
    result = router.route(
        "D",
        {
            "task_id": "debug investigate issue",
            "files": ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            "steps_history": [1, 2, 3, 4],
        },
    )

    assert result["skill_id"] == skill_id
    assert result["skill_source"] == "builtin"
    assert result["artifact_found"] is True
    assert result["skill_path"] == str(builtin_skill)


def test_router_falls_back_to_external_when_builtin_missing(tmp_path: Path) -> None:
    skill_id = "demo.skill"
    _write_inventory(tmp_path, skill_id)

    external_skill = tmp_path / "scripts" / skill_id / "SKILL.md"
    external_skill.parent.mkdir(parents=True, exist_ok=True)
    external_skill.write_text("# external\n", encoding="utf-8")

    router = SkillsRouter(project_root=str(tmp_path))
    result = router.route(
        "D",
        {
            "task_id": "debug investigate issue",
            "files": ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            "steps_history": [1, 2, 3, 4],
        },
    )

    assert result["skill_id"] == skill_id
    assert result["skill_source"] == "external"
    assert result["artifact_found"] is True
    assert result["skill_path"] == str(external_skill)


def test_router_rejects_missing_skill_artifact(tmp_path: Path) -> None:
    skill_id = "demo.skill"
    _write_inventory(tmp_path, skill_id)

    router = SkillsRouter(project_root=str(tmp_path))
    result = router.route(
        "D",
        {
            "task_id": "debug investigate issue",
            "files": ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            "steps_history": [1, 2, 3, 4],
        },
    )

    assert result == {}
