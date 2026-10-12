import json
from unittest.mock import patch

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.core.drone_engine import TacticalDrone
from nexus.orchestrator.event_logger import EventLogger
from nexus.orchestrator.metrics import MetricsAggregator
from scripts.engine.commands.multi_agent_actions import render_multi_agent_metrics


def _metrics(tmp_path, events):
    logger = EventLogger(str(tmp_path / "events.jsonl"))
    for event_type, task_id in events:
        logger.log_event(event_type, {"task_id": task_id})
    return MetricsAggregator(logger).compute_metrics()


def test_close_after_gate_failures_is_not_success(tmp_path):
    m = _metrics(
        tmp_path,
        [
            ("TASK_CREATE", "t1"),
            ("TASK_START", "t1"),
            ("GATE_FAILURE", "t1"),
            ("GATE_FAILURE", "t1"),
            ("TASK_CLOSE", "t1"),
        ],
    )
    assert m["total_tasks"] == 1
    assert m["success_rate"] == 0.0
    assert m["gate_failure_rate"] == 1.0
    assert m["gate_failure_events"] == 2
    assert all(m[k] <= 1.0 for k in ("success_rate", "conflict_rate", "gate_failure_rate"))
    lines = render_multi_agent_metrics(m)
    assert "Success Rate: 0.0%" in lines
    assert "Gate Failure Rate: 100.0%" in lines


def test_verified_close_counts_as_success(tmp_path):
    m = _metrics(
        tmp_path,
        [
            ("TASK_START", "ok"),
            ("GATE_FAILURE", "ok"),
            ("GATE_PASS", "ok"),
            ("TASK_CLOSE", "ok"),
            ("TASK_START", "bad"),
            ("GATE_FAILURE", "bad"),
            ("TASK_CLOSE", "bad"),
        ],
    )
    assert m["total_tasks"] == 2
    assert m["success_rate"] == 0.5
    assert m["gate_failure_rate"] == 1.0
    assert m["gate_failure_events"] == 2


def test_pass_without_close_is_not_success(tmp_path):
    m = _metrics(tmp_path, [("TASK_START", "t"), ("GATE_PASS", "t")])
    assert m["success_rate"] == 0.0
    assert m["gate_failure_rate"] == 0.0


def test_empty_metrics_are_not_applicable(tmp_path):
    m = _metrics(tmp_path, [])
    assert m["total_tasks"] == 0
    assert m["success_rate"] is None
    assert m["gate_failure_rate"] is None
    assert m["conflict_rate"] is None
    lines = render_multi_agent_metrics(m)
    assert "Success Rate: N/A" in lines
    assert "Gate Failure Rate: N/A" in lines
    assert "Conflict Rate: N/A" in lines


def test_fail_drone_crystal_has_no_confident_belief_score(tmp_path):
    drone = TacticalDrone(drone_id="dfail", project_root=tmp_path, max_rounds=2)
    result = drone.abort_unavailable("LLM endpoint unavailable")
    assert result["belief_final"] is None
    data = json.loads(
        (tmp_path / ".nexus/reports/drones/dfail_crystal.json").read_text(encoding="utf-8")
    )
    assert data["status"] == "FAIL"
    assert data["belief_score"] is None
    assert "FAIL" in data["belief_score_reason"]


def test_failed_run_via_unreachable_llm_has_no_belief_score(tmp_path):
    drone = TacticalDrone(drone_id="dfail2", project_root=tmp_path, max_rounds=3)
    with patch("nexus.core.drone_engine.requests.post", side_effect=ConnectionError("down")):
        result = drone.sense_think_act("do something")
    assert result["outcome"] != "SUCCESS"
    data = json.loads(
        (tmp_path / ".nexus/reports/drones/dfail2_crystal.json").read_text(encoding="utf-8")
    )
    assert data["belief_score"] is None


def test_success_crystal_keeps_real_belief_score(tmp_path):
    drone = TacticalDrone(drone_id="dok", project_root=tmp_path)
    drone.belief_score = 0.8
    drone.status = "SUCCESS"
    drone.save_evolution_crystal(drone.crystal_path())
    data = json.loads(drone.crystal_path().read_text(encoding="utf-8"))
    assert data["belief_score"] == 0.8


def test_hud_renders_null_belief_score(tmp_path, monkeypatch):
    drone = TacticalDrone(drone_id="dnull", project_root=tmp_path)
    drone.abort_unavailable("down")
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    res = CliRunner().invoke(cli_mod.nexus, ["nexus", "drone-hud"])
    assert res.exit_code == 0
    assert "Drone: dnull | Status: FAIL | Belief: N/A" in res.output
