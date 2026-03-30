import json
from pathlib import Path


def test_builtin_skill_stubs_exist_for_critical_inventory_entries():
    project_root = Path(__file__).resolve().parents[1]
    inventory = json.loads((project_root / "scripts" / "skills_inventory.json").read_text(encoding="utf-8"))
    skills = inventory.get("skills", {})

    critical = [
        "codebase_investigator",
        "self-healer",
        "git-manager",
        "aibdd.spec.user-story.gen",
        "aibdd.auto.python.e2e.red/green",
        "common.gen.pseudo-code",
        "superpowers",
        "felo-cli",
        "skill-creator-advanced",
    ]
    for skill_id in critical:
        assert skill_id in skills, f"missing inventory entry: {skill_id}"
        skill_path = project_root / "scripts" / "skills_builtin" / skill_id / "SKILL.md"
        assert skill_path.exists(), f"missing builtin stub: {skill_path}"
