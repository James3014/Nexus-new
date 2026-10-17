"""#1678: start-phase runs the green gate itself and auto-repairs within a bounded budget."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_phase_chain_test", str(SCRIPT)).load_module()


@pytest.fixture
def tmp_path(dsh_non_temp_path: Path) -> Path:
    # DSH grants its temp areas to every session, so the guard rejects workspaces
    # under pytest's tmp_path (#1607); keep these repositories outside them.
    return dsh_non_temp_path


REPO = "James3014/Nexus-new"
ISSUE = 1678
NODE = "test_mod.py::test_value"

# Each invocation consumes the next step of FAKE_DSH_PLAN: optional file writes, a
# session id and an exit code. Every argv is appended to FAKE_DSH_CALLS.
FAKE_DSH = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
calls = Path(os.environ['FAKE_DSH_CALLS'])
seen = json.loads(calls.read_text()) if calls.exists() else []
seen.append(sys.argv[1:])
calls.write_text(json.dumps(seen))
step = json.loads(Path(os.environ['FAKE_DSH_PLAN']).read_text())[len(seen) - 1]
print(json.dumps({'type': 'session', 'sessionId': step['session'], 'cwd': os.getcwd()}))
if step.get('goal'):
    print(json.dumps({'type': 'goal/change', 'data': {'kind': 'goal/change',
        'operation': 'create', 'goal': {'id': 'goal-c', 'revision': 1,
        'objective': 'FIX_1678', 'maxGoalRounds': 1}}}))
for rel, text in step.get('write', {}).items():
    Path(rel).write_text(text)
sys.exit(step.get('exit', 0))
"""


def _doctor_payload() -> dict:
    return {
        "schema": guard.DOCTOR_SCHEMA,
        "claim_ceiling": guard.DOCTOR_CLAIM_CEILING,
        "resume_disposition": "SAFE",
        "next_gate": {"code": "CONTINUE_BOUNDED_ISSUE_WORK"},
        "source": {"status": "OBSERVED", "head": "a" * 40, "github_main": "b" * 40},
        "task": {
            "status": "OBSERVED",
            "state": "open",
            "issue_number": ISSUE,
            "updated_at": "2026-10-10T00:00:00Z",
            "url": "https://example.invalid/1678",
        },
    }


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _setup(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (repo / "mod.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "test_mod.py").write_text(
        "from mod import value\n\n\ndef test_value():\n    assert value == 3\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    venv_bin = repo / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    # A wrapper, not a symlink: a symlinked venv interpreter loses its site-packages.
    (venv_bin / "python").write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8"
    )
    (venv_bin / "python").chmod(0o755)
    doctor = tmp_path / "doctor"
    doctor.write_text(
        f"#!/usr/bin/env python3\nimport json\nprint(json.dumps({_doctor_payload()!r}))\n",
        encoding="utf-8",
    )
    doctor.chmod(0o755)
    dsh = tmp_path / "dsh"
    dsh.write_text(FAKE_DSH, encoding="utf-8")
    dsh.chmod(0o755)
    contract = tmp_path / "contract.md"
    contract.write_text("CONTRACT_BODY allowed: mod.py\n", encoding="utf-8")
    green = tmp_path / "green.json"
    green.write_text(
        json.dumps({
            "schema": guard.GREEN_CONTRACT_SCHEMA,
            "repository": REPO,
            "issue_number": ISSUE,
            "target_test_nodes": [NODE],
            "regression_pytest_targets": [],
            "allowed_change_globs": ["mod.py"],
            "lint": {"ruff_check_paths_from_changes": False, "ruff_format_preview": False},
        }),
        encoding="utf-8",
    )
    (tmp_path / "dsh-home").mkdir()
    return {
        "tmp": tmp_path,
        "repo": repo,
        "base": _git(repo, "rev-parse", "HEAD"),
        "doctor": doctor,
        "dsh": dsh,
        "contract": contract,
        "green": green,
        "state": tmp_path / "state",
        "calls": tmp_path / "calls.json",
        "plan": tmp_path / "plan.json",
        "home": tmp_path / "dsh-home",
    }


def _value(n: int) -> dict:
    return {"mod.py": f"value = {n}\n"}


def _start(ctx: dict, plan: list[dict], *extra: str, phase: str = "green"):
    ctx["plan"].write_text(json.dumps(plan), encoding="utf-8")
    env = os.environ.copy()
    env["FAKE_DSH_CALLS"] = str(ctx["calls"])
    env["FAKE_DSH_PLAN"] = str(ctx["plan"])
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "start-phase",
            "--repository",
            REPO,
            "--issue",
            str(ISSUE),
            "--phase",
            phase,
            "--repo-root",
            str(ctx["repo"]),
            "--dsh-home",
            str(ctx["home"]),
            "--phase-contract",
            str(ctx["contract"]),
            "--state-root",
            str(ctx["state"]),
            "--doctor-bin",
            str(ctx["doctor"]),
            "--dsh-bin",
            str(ctx["dsh"]),
            *extra,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def _calls(ctx: dict) -> list[list[str]]:
    return json.loads(ctx["calls"].read_text()) if ctx["calls"].exists() else []


def _chain(ctx: dict, proc) -> dict:
    out = json.loads(proc.stdout)
    assert out["schema"] == "nexus.dsh_phase_chain.v1", proc.stdout + proc.stderr
    durable = json.loads(Path(out["summary_path"]).read_text(encoding="utf-8"))
    assert {k: v for k, v in out.items() if k != "summary_path"} == durable
    return out


def test_auto_repair_reaches_green_ready_on_second_repair(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [
        {"session": "s-green", "write": _value(2)},
        {"session": "s-repair-1", "write": _value(4)},
        {"session": "s-repair-2", "write": _value(3)},
        {"session": "s-unused", "write": _value(9)},
    ]
    proc = _start(ctx, plan, "--green-contract", str(ctx["green"]), "--auto-repair", "3")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = _chain(ctx, proc)
    assert out["final_decision"] == "GREEN_READY"
    assert out["stop_reason"] == "GREEN_READY"
    assert out["auto_repair_limit"] == 3
    assert out["repairs_used"] == 2
    assert [p["phase"] for p in out["phases"]] == ["green", "repair", "repair"]
    assert [p["session_id"] for p in out["phases"]] == ["s-green", "s-repair-1", "s-repair-2"]
    decisions = [p["gate"]["decision"] for p in out["phases"]]
    assert decisions == ["REVISE_GREEN", "REVISE_GREEN", "GREEN_READY"]
    for entry in out["phases"]:
        receipt = json.loads(Path(entry["gate"]["receipt_path"]).read_text(encoding="utf-8"))
        assert receipt["receipt_hash"] == entry["gate"]["receipt_hash"]
        assert receipt["base_revision"] == ctx["base"]
        assert entry["dsh_exit_code"] == 0
        assert entry["turn_state"] == guard.TURN_OK
    # Repair phases are lineage-bound to the previous session.
    assert out["phases"][1]["parent_session_id"] == "s-green"
    assert out["phases"][2]["parent_session_id"] == "s-repair-1"
    # The GREEN_READY receipt carries #1700 recovery sidecar evidence.
    ready = json.loads(Path(out["phases"][2]["gate"]["receipt_path"]).read_text())
    guard.verify_gate_sidecar(ctx["state"], ready, gate="green")
    assert len(_calls(ctx)) == 3


def test_auto_repair_limit_is_respected(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [{"session": f"s-{i}", "write": _value(10 + i)} for i in range(5)]
    proc = _start(ctx, plan, "--green-contract", str(ctx["green"]), "--auto-repair", "1")
    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    out = _chain(ctx, proc)
    assert out["final_decision"] == "REVISE_GREEN"
    assert out["stop_reason"] == "AUTO_REPAIR_EXHAUSTED"
    assert out["repairs_used"] == 1
    assert [p["phase"] for p in out["phases"]] == ["green", "repair"]
    assert len(_calls(ctx)) == 2


def test_default_auto_repair_is_zero_but_gate_still_runs(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [{"session": "s-green", "write": _value(2)}, {"session": "s-x", "write": _value(3)}]
    proc = _start(ctx, plan, "--green-contract", str(ctx["green"]))
    assert proc.returncode == guard.EXIT_BLOCKED
    out = _chain(ctx, proc)
    assert out["auto_repair_limit"] == 0
    assert out["stop_reason"] == "AUTO_REPAIR_EXHAUSTED"
    assert [p["gate"]["decision"] for p in out["phases"]] == ["REVISE_GREEN"]
    assert len(_calls(ctx)) == 1


def test_auto_repair_above_three_blocks_before_spawn(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    proc = _start(
        ctx, [{"session": "s"}], "--green-contract", str(ctx["green"]), "--auto-repair", "4"
    )
    assert proc.returncode == guard.EXIT_BLOCKED
    assert json.loads(proc.stdout)["reason_code"] == "START_PHASE_ARGUMENT_INVALID"
    assert _calls(ctx) == []


def test_auto_repair_without_green_contract_blocks_before_spawn(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    proc = _start(ctx, [{"session": "s"}], "--auto-repair", "1")
    assert proc.returncode == guard.EXIT_BLOCKED
    assert json.loads(proc.stdout)["reason_code"] == "START_PHASE_ARGUMENT_INVALID"
    assert _calls(ctx) == []


def test_nonzero_dsh_exit_stops_chain_without_gate_or_repair(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [{"session": "s-green", "write": _value(2), "exit": 3}, {"session": "s-x"}]
    proc = _start(ctx, plan, "--green-contract", str(ctx["green"]), "--auto-repair", "3")
    assert proc.returncode == 3, proc.stdout + proc.stderr
    out = _chain(ctx, proc)
    assert out["stop_reason"] == "DSH_TURN_FAILED"
    assert out["final_decision"] is None
    assert out["repairs_used"] == 0
    assert len(out["phases"]) == 1
    assert out["phases"][0]["gate"] is None
    assert out["phases"][0]["turn_state"] == guard.TURN_FAILED_DIRTY
    assert len(_calls(ctx)) == 1
    state = guard.load_turn_state(ctx["state"], "s-green")
    assert state is not None and Path(state["quarantine_receipt"]).is_file()


def test_nonzero_repair_turn_stops_chain(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [
        {"session": "s-green", "write": _value(2)},
        {"session": "s-repair-1", "write": _value(4), "exit": 7},
        {"session": "s-x", "write": _value(3)},
    ]
    proc = _start(ctx, plan, "--green-contract", str(ctx["green"]), "--auto-repair", "3")
    assert proc.returncode == 7
    out = _chain(ctx, proc)
    assert out["stop_reason"] == "DSH_TURN_FAILED"
    assert [p["phase"] for p in out["phases"]] == ["green", "repair"]
    assert out["phases"][1]["gate"] is None
    assert len(_calls(ctx)) == 2


def test_header_contains_safe_edit_rules_and_exact_gate_command(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    proc = _start(
        ctx, [{"session": "s-green", "write": _value(3)}], "--green-contract", str(ctx["green"])
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = _chain(ctx, proc)
    python = str(ctx["repo"].resolve() / ".venv" / "bin" / "python")
    expected = shlex.join([
        python,
        str(SCRIPT.resolve()),
        "green-gate",
        "--repo-root",
        str(ctx["repo"].resolve()),
        "--base-revision",
        ctx["base"],
        "--contract",
        str(ctx["green"].resolve()),
        "--python",
        python,
    ])
    assert out["green_gate_command"] == expected
    task = _calls(ctx)[0][-1]
    header = task.split("PHASE CONTRACT", 1)[0]
    assert (
        "Before claiming GREEN_READY, run this exact command and read its decision: "
        f"`{expected}`" in header
    )
    assert (
        "Never edit files with sed -i, perl -pi, or scripts that insert or append text; "
        "use the edit/write tools or a single anchored replacement that fails if the anchor "
        "is not found exactly once; after every edit run `git diff --stat`." in header
    )
    assert "Use only the repository interpreter `.venv/bin/python`." in header


def test_header_rules_present_for_all_phases_without_green_contract() -> None:
    for phase in guard.PHASES:
        task = guard.build_phase_task(
            phase=phase,
            goal_objective="O",
            parent_has_goal=False,
            prior_receipts=[],
            contract_text="C",
        )
        assert "Never edit files with sed -i, perl -pi" in task
        assert "Use only the repository interpreter `.venv/bin/python`." in task
        assert "Before claiming GREEN_READY" not in task


def test_generated_repair_contract_carries_gate_feedback(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [
        {"session": "s-green", "write": _value(2)},
        {"session": "s-repair-1", "write": _value(3)},
    ]
    proc = _start(ctx, plan, "--green-contract", str(ctx["green"]), "--auto-repair", "1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = _chain(ctx, proc)
    first_gate = out["phases"][0]["gate"]
    repair = out["phases"][1]
    contract = Path(repair["contract_path"]).read_text(encoding="utf-8")
    assert contract.startswith("CONTRACT_BODY allowed: mod.py\n")
    assert "TARGET_TESTS_NOT_PASSING" in contract
    assert first_gate["receipt_hash"] in contract
    assert NODE in contract and "assert 2 == 3" in contract
    task = _calls(ctx)[1][-1]
    assert "Phase: repair" in task
    assert f"{first_gate['receipt_path']} receipt_hash={first_gate['receipt_hash']}" in task
    assert task.rstrip().endswith(contract.rstrip())


def test_repair_contract_includes_lint_output_and_regression_messages() -> None:
    receipt = {
        "decision": "REVISE_GREEN",
        "receipt_hash": "sha256:" + "1" * 64,
        "reason_codes": ["LINT_FAILURE", "REGRESSION_TESTS_FAILING"],
        "node_results": [{"nodeid": NODE, "outcome": "passed", "message": ""}],
        "regression_failures": [
            {"classname": "t", "name": "test_r", "outcome": "failed", "message": "boom"}
        ],
        "lint_output": {"ruff_check": "F401 unused import", "ruff_format": None},
        "diff_check": {"exit_code": 0, "failures": []},
    }
    text = guard.build_repair_contract(
        "ORIGINAL", receipt, receipt_path="/r.json", attempt=1, limit=2
    )
    assert text.startswith("ORIGINAL")
    for needle in ("LINT_FAILURE", "REGRESSION_TESTS_FAILING", "F401 unused import", "boom"):
        assert needle in text
    assert "receipt_hash=sha256:" + "1" * 64 in text


def test_red_receipt_binds_gate_base_and_invalid_receipt_blocks(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    body = {
        "schema": guard.RED_RECEIPT_SCHEMA,
        "decision": "RED_READY",
        "repository": REPO,
        "issue_number": ISSUE,
        "base_revision": ctx["base"],
    }
    red = tmp_path / "red.json"
    red.write_text(json.dumps(guard._red_receipt(body)), encoding="utf-8")
    proc = _start(
        ctx,
        [{"session": "s-green", "write": _value(3)}],
        "--green-contract",
        str(ctx["green"]),
        "--red-receipt",
        str(red),
    )
    out = _chain(ctx, proc)
    assert out["red_receipt_hash"] == guard._red_receipt(body)["receipt_hash"]
    assert out["base_revision"] == ctx["base"]
    # The supplied receipt reaches the gate; one without RED node evidence cannot bind the
    # oracle, so the chain fails closed instead of reporting GREEN_READY (#1678/#1665).
    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    assert out["stop_reason"] == "RED_RECEIPT_INVALID"
    assert out["phases"][0]["gate"]["red_oracle"]["status"] == "INVALID"
    assert out["repairs_used"] == 0

    tampered = tmp_path / "red-bad.json"
    tampered.write_text(
        json.dumps({**guard._red_receipt(body), "decision": "REVISE_RED"}), encoding="utf-8"
    )
    ctx["calls"].unlink()
    proc = _start(
        ctx,
        [{"session": "s-2"}],
        "--green-contract",
        str(ctx["green"]),
        "--red-receipt",
        str(tampered),
    )
    assert proc.returncode == guard.EXIT_BLOCKED
    assert json.loads(proc.stdout)["reason_code"] == "RED_RECEIPT_INVALID"
    assert _calls(ctx) == []


def test_gate_environment_failure_stops_without_spending_repair_budget(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    (ctx["repo"] / ".venv" / "bin" / "python").unlink()
    plan = [{"session": "s-green", "write": _value(3)}, {"session": "s-x"}]
    proc = _start(ctx, plan, "--green-contract", str(ctx["green"]), "--auto-repair", "3")
    assert proc.returncode == guard.EXIT_BLOCKED
    out = _chain(ctx, proc)
    assert out["stop_reason"] == "GREEN_GATE_ENVIRONMENT_FAILURE"
    assert out["phases"][0]["gate"]["reason_codes"] == ["ENVIRONMENT_FAILURE"]
    assert out["repairs_used"] == 0
    assert len(_calls(ctx)) == 1


def test_red_phase_with_green_contract_gets_header_but_no_gate(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [{"session": "s-red", "goal": True}, {"session": "s-x"}]
    proc = _start(ctx, plan, "--green-contract", str(ctx["green"]), phase="red")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = _chain(ctx, proc)
    assert out["stop_reason"] == "NO_GATE_FOR_RED_PHASE"
    assert out["phases"][0]["gate"] is None
    assert out["final_decision"] is None
    assert out["green_gate_command"] in _calls(ctx)[0][-1]
    assert len(_calls(ctx)) == 1
    redo = _start(
        ctx, plan, "--green-contract", str(ctx["green"]), "--auto-repair", "1", phase="red"
    )
    assert json.loads(redo.stdout)["reason_code"] == "START_PHASE_ARGUMENT_INVALID"
