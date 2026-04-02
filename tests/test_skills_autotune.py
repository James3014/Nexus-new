from pathlib import Path
import json

from scripts.ops.skills_autotune import run_autotune


def test_autotune_emits_skill_creator_queue_for_degraded_skill(tmp_path: Path):
    project_root = tmp_path
    (project_root / "scripts" / "core").mkdir(parents=True, exist_ok=True)
    (project_root / ".nexus" / "runs" / "r1").mkdir(parents=True, exist_ok=True)

    weights_path = project_root / "scripts" / "core" / "autonomic_weights.json"
    weights_path.write_text(
        json.dumps(
            {
                "base_weights": {},
                "skill_adjustments": {"demo-skill": 2.0},
                "last_updated": "x",
                "total_sessions_analyzed": 1,
            }
        ),
        encoding="utf-8",
    )

    decision_log = project_root / ".nexus" / "runs" / "r1" / "router_decisions.jsonl"
    decision_log.write_text(
        "\n".join(
            [
                json.dumps({"phase": "D", "decision_id": "dec-1", "selected_skill": "demo-skill", "score": 1.0}),
                json.dumps({"phase": "D", "decision_id": "dec-2", "selected_skill": "demo-skill", "score": 1.2}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    outcome_log = project_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
    outcome_log.parent.mkdir(parents=True, exist_ok=True)
    outcome_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "decision_id": "dec-1",
                        "skill_id": "demo-skill",
                        "pass": False,
                        "phantom_blocked": True,
                        "retry_count": 3,
                        "repair_success": False,
                        "proof_present": False,
                        "regression_pass_rate": 0.0,
                        "pattern_reuse": 0.0,
                        "next_run_hit": 0.0,
                    }
                ),
                json.dumps(
                    {
                        "decision_id": "dec-2",
                        "skill_id": "demo-skill",
                        "pass": False,
                        "phantom_blocked": True,
                        "retry_count": 2,
                        "repair_success": False,
                        "proof_present": False,
                        "regression_pass_rate": 0.0,
                        "pattern_reuse": 0.0,
                        "next_run_hit": 0.0,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rc = run_autotune(
        project_root=project_root,
        apply=False,
        min_samples=1,
        baseline=0.9,
        learning_rate=0.6,
        degrade_threshold=0.2,
        max_step=0.35,
        degrade_consecutive_rounds=1,
    )
    assert rc == 0

    queue_path = project_root / ".nexus" / "metrics" / "skills_optimization_queue.json"
    assert queue_path.exists()
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue["handler_skill"] == "skill-creator-advanced"
    assert len(queue["items"]) == 1
    assert queue["items"][0]["skill_id"] == "demo-skill"
