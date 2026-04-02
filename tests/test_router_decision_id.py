from pathlib import Path
import json

from nexus.core.router import SkillsRouter


def test_router_emits_decision_id_in_candidates_and_log(tmp_path: Path):
    inventory_path = tmp_path / "scripts" / "skills_inventory.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(
        json.dumps(
            {
                "skills": {
                    "demo-skill": {
                        "description": "demo",
                        "phases": ["R"],
                        "triggers": ["demo"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    skill_file = tmp_path / "scripts" / "skills_builtin" / "demo-skill" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text("# Demo\n", encoding="utf-8")

    router = SkillsRouter(project_root=str(tmp_path), run_dir=str(tmp_path / ".nexus" / "runs" / "t1"))
    candidates = router.route_candidates("R", {"task_id": "demo task"})
    assert candidates
    assert str(candidates[0].get("decision_id", "")).startswith("dec_r_")

    log_path = tmp_path / ".nexus" / "runs" / "t1" / "router_decisions.jsonl"
    assert log_path.exists()
    line = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()][-1]
    row = json.loads(line)
    assert str(row.get("decision_id", "")).startswith("dec_r_")
