import json
from pathlib import Path

from scripts.ops.skills_health import build_skills_health


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_skills_health_ready_with_converged_phase7(tmp_path):
    _write_json(
        tmp_path / "scripts" / "core" / "autonomic_weights.json",
        {"skill_adjustments": {"nexus-debug-expert": 7.2}},
    )
    _write_json(
        tmp_path / ".nexus" / "metrics" / "skills_autotune_report.json",
        {
            "tuned_skill_count": 1,
            "total_rows": 50,
            "suggestions": {
                "nexus-debug-expert": {"delta": 0.4, "proposed": 7.2, "current": 6.8}
            },
        },
    )
    _write_json(
        tmp_path / ".nexus" / "metrics" / "skills_optimization_queue.json",
        {"items": []},
    )
    workspace = tmp_path / "workspace"
    _write_json(workspace / "phase7_prod_final_report_cn.json", {"converged": True})

    payload = build_skills_health(project_root=tmp_path, workspace=workspace)
    assert payload["ready_for_formal_use"] is True
    assert payload["readiness"]["phase7_loop_converged"] is True
    assert payload["summary"]["queue_count"] == 0


def test_build_skills_health_not_ready_when_queue_has_items(tmp_path):
    _write_json(
        tmp_path / "scripts" / "core" / "autonomic_weights.json",
        {"skill_adjustments": {"skill-a": 1.0}},
    )
    _write_json(
        tmp_path / ".nexus" / "metrics" / "skills_autotune_report.json",
        {"tuned_skill_count": 1, "total_rows": 10, "suggestions": {"skill-a": {"delta": -0.5}}},
    )
    _write_json(
        tmp_path / ".nexus" / "metrics" / "skills_optimization_queue.json",
        {"items": [{"skill_id": "skill-a"}]},
    )

    payload = build_skills_health(project_root=tmp_path, workspace=None)
    assert payload["ready_for_formal_use"] is False
    assert payload["readiness"]["optimization_queue_empty"] is False
