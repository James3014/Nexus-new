import json
from pathlib import Path

from scripts.ops.skills_optimization_runner import run_once


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_skills_optimization_runner_processes_queue_and_rebounds_weight(tmp_path: Path):
    skill_path = tmp_path / "scripts" / "skills_builtin" / "demo-skill" / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text("# Demo Skill\n", encoding="utf-8")

    _write_json(
        tmp_path / "scripts" / "core" / "autonomic_weights.json",
        {"skill_adjustments": {"demo-skill": 1.0}},
    )
    _write_json(
        tmp_path / ".nexus" / "metrics" / "skills_optimization_queue.json",
        {
            "items": [
                {
                    "skill_id": "demo-skill",
                    "skill_path_builtin": str(skill_path),
                }
            ]
        },
    )

    rc = run_once(tmp_path, max_items=3, rebound=0.1)
    assert rc == 0

    queue = json.loads(
        (tmp_path / ".nexus" / "metrics" / "skills_optimization_queue.json").read_text(encoding="utf-8")
    )
    assert queue["items"] == []

    weights = json.loads((tmp_path / "scripts" / "core" / "autonomic_weights.json").read_text(encoding="utf-8"))
    assert float(weights["skill_adjustments"]["demo-skill"]) > 1.0

    content = skill_path.read_text(encoding="utf-8")
    assert "## Trigger Precision" in content
    assert "## Output Contract" in content
