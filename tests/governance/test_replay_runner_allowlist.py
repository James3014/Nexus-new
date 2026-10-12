"""Replay runners must only execute allowlisted verification commands."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.delivery.replay_runner import ReplayRunner, _parse_command

ROOT = Path(__file__).resolve().parents[2]
OPS_SCRIPT = ROOT / "scripts/ops/replay_runner.py"


def _env():
    # Allowlisted bare names (python3, pytest) must resolve to the interpreter running the tests.
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


@pytest.fixture(autouse=True)
def _interpreter_on_path(monkeypatch):
    monkeypatch.setenv("PATH", _env()["PATH"])


def _run(tmp_path, artifacts):
    return ReplayRunner(tmp_path).run_replay({"test_artifacts": artifacts})


def test_rm_is_rejected_and_not_executed(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    report = _run(tmp_path, [{"command": "rm victim.txt", "exit_code": 0}])
    assert victim.exists()
    assert report["status"] == "REJECTED"
    assert report["passed"] is False
    item = report["replay_results"][0]
    assert item["status"] == "REJECTED"
    assert item["reason"] == "command_not_allowlisted:rm"
    assert item["executed"] is False


def test_touch_is_rejected_and_not_executed(tmp_path):
    report = _run(tmp_path, [{"command": "touch x"}])
    assert not (tmp_path / "x").exists()
    assert report["status"] != "COMPLETED"
    assert report["passed"] is False
    assert report["replay_results"][0]["reason"] == "command_not_allowlisted:touch"


@pytest.mark.parametrize(
    "cmd",
    [
        "definitely_not_a_binary --flag",
        "echo ok",
        "python -c 'print(1)'",
        "python3 script.py",
        "uv sync",
        "uv run rm x",
        "ruff format .",
        "./pytest",
        "/bin/rm x",
        "bash -c true",
    ],
)
def test_arbitrary_binaries_are_not_allowlisted(cmd):
    with pytest.raises(ValueError, match="command_not_allowlisted:"):
        _parse_command(cmd)


@pytest.mark.parametrize(
    "cmd",
    [
        "pytest -q",
        "python -m pytest -q tests/x.py",
        "python3 -m pytest -q",
        "uv run pytest -q tests/x.py",
        "uv run python -m pytest -q",
        "uv run python3 -m pytest",
        "ruff check nexus",
    ],
)
def test_allowlisted_families_parse(cmd):
    assert _parse_command(cmd)


@pytest.mark.parametrize(
    "cmd",
    ["pytest -p evil_plugin", "pytest -pevil", "ruff check --fix .", "pytest ../outside"],
)
def test_dangerous_options_of_allowed_tools_are_rejected(cmd):
    with pytest.raises(ValueError):
        _parse_command(cmd)


def test_metacharacters_still_rejected(tmp_path):
    report = _run(tmp_path, [{"command": "pytest -q; rm -rf x"}])
    assert report["passed"] is False
    assert "unsafe_command" in report["replay_results"][0]["error"]


def _write_tiny_test(tmp_path, body):
    (tmp_path / "test_tiny.py").write_text(f"def test_tiny():\n    {body}\n")


def test_allowlisted_pytest_really_runs_and_passes(tmp_path):
    _write_tiny_test(tmp_path, "assert 1 + 1 == 2")
    report = _run(tmp_path, [{"command": "python3 -m pytest -q test_tiny.py", "exit_code": 0}])
    item = report["replay_results"][0]
    assert item["executed"] is True
    assert item["actual_exit_code"] == 0
    assert report["status"] == "COMPLETED"
    assert report["passed"] is True
    assert report["replay_count"] == 1


def test_allowlisted_pytest_failure_fails(tmp_path):
    _write_tiny_test(tmp_path, "assert 1 == 2")
    report = _run(tmp_path, [{"command": "python3 -m pytest -q test_tiny.py", "exit_code": 0}])
    assert report["replay_results"][0]["executed"] is True
    assert report["replay_results"][0]["actual_exit_code"] != 0
    assert report["status"] == "FAILED"
    assert report["passed"] is False


def test_string_artifact_does_not_crash_and_is_not_a_passed_replay(tmp_path):
    report = _run(tmp_path, ["claims_count=7", {"aggregates": {"success_rate": 1.0}}, 5, None])
    assert report["replay_count"] == 0
    assert report["non_replayable_count"] == 4
    assert report["status"] == "NOT_REPLAYED"
    assert report["status"] != "COMPLETED"
    assert all(
        r["executed"] is False and r["status"] == "NOT_REPLAYABLE" for r in report["replay_results"]
    )


def test_notes_do_not_mask_a_rejected_command(tmp_path):
    report = _run(tmp_path, ["claims_count=7", {"command": "rm -rf x"}])
    assert report["passed"] is False
    assert report["status"] == "REJECTED"


def _ops(tmp_path, artifacts, *extra):
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"evidence_bundle": {"test_artifacts": artifacts}}))
    proc = subprocess.run(
        [sys.executable, str(OPS_SCRIPT), str(evidence), *extra],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
        env=_env(),
    )
    return proc.returncode, json.loads(proc.stdout)


def test_ops_script_does_not_pass_a_bogus_command(tmp_path):
    code, data = _ops(tmp_path, [{"command": "definitely_not_a_binary --x", "exit_code": 0}])
    assert data["status"] == "FAIL"
    assert data["status"] != "PASS"
    assert code != 0
    assert data["replay_results"][0]["reason"] == "command_not_allowlisted:definitely_not_a_binary"


def test_ops_script_notes_only_is_unverified_not_pass(tmp_path):
    code, data = _ops(tmp_path, ["claims_count=7"])
    assert data["status"] == "UNVERIFIED"
    assert code != 0
    code, data = _ops(tmp_path, ["claims_count=7"], "--allow-no-replay")
    assert data["status"] == "UNVERIFIED"
    assert code == 0


def test_ops_script_passes_only_after_real_replay(tmp_path):
    # A real allowlisted command is replayed from the repo root.
    code, data = _ops(tmp_path, [{"command": "python3 -m pytest --version", "exit_code": 0}])
    assert data["status"] == "PASS"
    assert data["replay_count"] == 1
    assert code == 0
