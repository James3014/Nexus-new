import json
from unittest.mock import patch

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.core.drone_engine import TacticalDrone


def _write(root, name, payload):
    d = root / ".nexus" / "reports" / "drones"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return p


def _hud(monkeypatch, root):
    monkeypatch.setattr(cli_mod, "repo_root", root)
    return CliRunner().invoke(cli_mod.nexus, ["nexus", "drone-hud"])


def test_hud_no_real_records(tmp_path, monkeypatch):
    _write(tmp_path, "x_local_msa_crystal.json", {"synthetic": True, "verified": True})
    out = _hud(monkeypatch, tmp_path).output
    assert "No real drone records found." in out
    assert "[SYNTHETIC]" in out
    assert "Drone:" not in out


def test_hud_real_invalid_and_unreadable(tmp_path, monkeypatch):
    _write(
        tmp_path,
        "a_crystal.json",
        {"drone_id": "a", "status": "SUCCESS", "synthetic": False, "belief_score": 0.9},
    )
    _write(tmp_path, "b_crystal.json", {"verified": True})
    _write(tmp_path, "c_crystal.json", "{not json")
    res = _hud(monkeypatch, tmp_path)
    assert res.exit_code == 0
    assert "Drone: a | Status: SUCCESS" in res.output
    assert "Active/Completed Drones: 1" in res.output
    assert "[INVALID] b_crystal.json" in res.output
    assert "[UNREADABLE] c_crystal.json" in res.output


def test_drone_writes_crystal_on_failure_when_llm_unreachable(tmp_path):
    drone = TacticalDrone(drone_id="dfail", project_root=tmp_path, max_rounds=3)
    with patch("nexus.core.drone_engine.requests.post", side_effect=ConnectionError("down")):
        result = drone.sense_think_act("do something")
    assert result["outcome"] != "SUCCESS"
    data = json.loads(
        (tmp_path / ".nexus/reports/drones/dfail_crystal.json").read_text(encoding="utf-8")
    )
    assert data["drone_id"] == "dfail"
    assert data["status"] == result["outcome"]
    assert data["synthetic"] is False
    assert data["started_at"] and data["finished_at"]


def test_cli_drone_run_fails_closed_when_llm_down(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    with patch("nexus.core.drone_engine.requests.get", side_effect=ConnectionError("down")):
        res = CliRunner().invoke(
            cli_mod.nexus, ["nexus", "drone", "run", "--task", "t", "--drone-id", "dd"]
        )
    assert res.exit_code == 1
    data = json.loads(
        (tmp_path / ".nexus/reports/drones/dd_crystal.json").read_text(encoding="utf-8")
    )
    assert data["status"] == "FAIL"
    assert data["synthetic"] is False
