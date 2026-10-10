"""#1686: start-phase runs the red gate itself, auto-repairs RED, and may continue to GREEN."""

from __future__ import annotations

import json
import shlex
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pc = SourceFileLoader(
    "nexus_dsh_phase_chain_helpers_for_red_chain",
    str(Path(__file__).resolve().with_name("test_nexus_dsh_phase_chain.py")),
).load_module()
guard = pc.guard


@pytest.fixture
def tmp_path(dsh_non_temp_path: Path) -> Path:
    # DSH grants its temp areas to every session, so the guard rejects workspaces
    # under pytest's tmp_path (#1607); keep these repositories outside them.
    return dsh_non_temp_path


RED_NODE = "test_red.py::test_value_is_three"
BAD_TEST = "def test_value_is_three():\n    raise RuntimeError('AgyAccountPoolBusyError')\n"
GOOD_TEST = "from mod import value\n\n\ndef test_value_is_three():\n    assert value == 3\n"


def _setup(tmp_path: Path) -> dict:
    ctx = pc._setup(tmp_path)
    red = tmp_path / "red.json"
    red.write_text(
        json.dumps({
            "schema": guard.RED_CONTRACT_SCHEMA,
            "repository": pc.REPO,
            "issue_number": pc.ISSUE,
            "invariant": "value must be three",
            "test_nodes": [RED_NODE],
            "expected_failure": {"kind": "assertion", "message_regex": r"assert 1 == 3"},
            "forbidden_oracle_literals": [],
            "test_path_globs": ["test_red.py"],
        }),
        encoding="utf-8",
    )
    green = json.loads(ctx["green"].read_text(encoding="utf-8"))
    green["target_test_nodes"] = [RED_NODE]
    green["allowed_change_globs"] = ["mod.py", "test_red.py"]
    ctx["green"].write_text(json.dumps(green), encoding="utf-8")
    green_phase = tmp_path / "green-phase.md"
    green_phase.write_text("GREEN_PHASE_BODY allowed: mod.py\n", encoding="utf-8")
    return {**ctx, "red": red, "green_phase": green_phase}


def _red(session: str, text: str, **extra) -> dict:
    return {"session": session, "write": {"test_red.py": text}, **extra}


def _start_red(ctx: dict, plan: list[dict], *extra: str):
    return pc._start(ctx, plan, "--red-contract", str(ctx["red"]), *extra, phase="red")


def _green_args(ctx: dict) -> list[str]:
    return [
        "--continue-to-green",
        "--green-contract",
        str(ctx["green"]),
        "--green-phase-contract",
        str(ctx["green_phase"]),
    ]


def test_red_repair_reaches_red_ready_on_second_attempt(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [
        _red("s-red", BAD_TEST, goal=True),
        _red("s-red-repair-1", GOOD_TEST),
        _red("s-unused", BAD_TEST),
    ]
    proc = _start_red(ctx, plan, "--auto-repair-red", "3")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "RED_READY"
    assert out["final_decision"] == "RED_READY"
    assert out["red_auto_repair_limit"] == 3
    assert out["red_repairs_used"] == 1
    assert out["base_revision"] == ctx["base"]
    assert [p["phase"] for p in out["phases"]] == ["red", "red"]
    assert [p["session_id"] for p in out["phases"]] == ["s-red", "s-red-repair-1"]
    assert out["phases"][1]["parent_session_id"] == "s-red"
    gates = [p["gate"] for p in out["phases"]]
    assert [g["kind"] for g in gates] == ["red", "red"]
    assert [g["decision"] for g in gates] == ["REVISE_RED", "RED_READY"]
    assert gates[0]["reason_codes"] == ["UNINTENDED_FAILURE"]
    # The final RED receipt is durable, hash-intact and usable as --red-receipt.
    assert out["red_receipt_path"] == gates[1]["receipt_path"]
    assert out["red_receipt_hash"] == gates[1]["receipt_hash"]
    ready = guard._load_red_receipt(Path(out["red_receipt_path"]), pc.REPO, pc.ISSUE)
    assert ready["receipt_hash"] == out["red_receipt_hash"]
    assert ready["base_revision"] == ctx["base"]
    assert ready["contract_hash"] == out["red_contract_hash"]
    guard.verify_gate_sidecar(ctx["state"], ready, gate="red")
    assert len(pc._calls(ctx)) == 2


def test_red_repair_contract_and_header_carry_gate_evidence(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [_red("s-red", BAD_TEST, goal=True), _red("s-red-repair-1", GOOD_TEST)]
    proc = _start_red(ctx, plan, "--auto-repair-red", "1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    first = out["phases"][0]["gate"]
    contract = Path(out["phases"][1]["contract_path"]).read_text(encoding="utf-8")
    assert contract.startswith("CONTRACT_BODY allowed: mod.py\n")
    assert "RED GATE FEEDBACK (auto-repair 1/1" in contract
    assert f"{first['receipt_path']} receipt_hash={first['receipt_hash']}" in contract
    assert "UNINTENDED_FAILURE" in contract
    assert RED_NODE in contract and "AgyAccountPoolBusyError" in contract
    assert "Changed paths: test_red.py" in contract
    assert "Invariant: value must be three" in contract
    assert "Expected failure: assertion matching `assert 1 == 3`" in contract
    assert (
        "Edit only tests; make the target fail at an assertion that encodes the intended"
        " behavior." in contract
    )
    python = str(ctx["repo"].resolve() / ".venv" / "bin" / "python")
    red_gate = shlex.join([
        python,
        str(pc.SCRIPT.resolve()),
        "red-gate",
        "--repo-root",
        str(ctx["repo"].resolve()),
        "--base-revision",
        ctx["base"],
        "--contract",
        str(ctx["red"].resolve()),
        "--python",
        python,
    ])
    assert out["red_gate_command"] == red_gate
    calls = pc._calls(ctx)
    for task in (calls[0][-1], calls[1][-1]):
        header = task.split("PHASE CONTRACT", 1)[0]
        assert (
            "Before claiming RED_READY, run this exact command and read its decision: "
            f"`{red_gate}`" in header
        )
        assert "Before claiming GREEN_READY" not in header
    repair_task = calls[1][-1]
    assert "Phase: red" in repair_task
    assert "create_goal for this phase: NOT allowed" in repair_task
    assert f"- {first['receipt_path']} receipt_hash={first['receipt_hash']}" in repair_task
    assert repair_task.rstrip().endswith(contract.rstrip())


def test_red_auto_repair_limit_is_respected(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [_red("s-red", BAD_TEST, goal=True)] + [_red(f"s-{i}", BAD_TEST) for i in range(4)]
    proc = _start_red(ctx, plan, "--auto-repair-red", "1", *_green_args(ctx))
    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "RED_AUTO_REPAIR_EXHAUSTED"
    assert out["final_decision"] == "REVISE_RED"
    assert out["red_repairs_used"] == 1
    assert out["red_receipt_path"] is None
    assert [p["phase"] for p in out["phases"]] == ["red", "red"]
    assert len(pc._calls(ctx)) == 2


def test_default_red_budget_is_zero_but_gate_still_runs(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [_red("s-red", BAD_TEST, goal=True), _red("s-x", GOOD_TEST)]
    proc = _start_red(ctx, plan)
    assert proc.returncode == guard.EXIT_BLOCKED
    out = pc._chain(ctx, proc)
    assert out["red_auto_repair_limit"] == 0
    assert out["stop_reason"] == "RED_AUTO_REPAIR_EXHAUSTED"
    assert [p["gate"]["decision"] for p in out["phases"]] == ["REVISE_RED"]
    assert len(pc._calls(ctx)) == 1


def test_nonzero_red_repair_turn_stops_chain(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [
        _red("s-red", BAD_TEST, goal=True),
        _red("s-red-repair-1", GOOD_TEST, exit=5),
        _red("s-x", GOOD_TEST),
    ]
    proc = _start_red(ctx, plan, "--auto-repair-red", "3", *_green_args(ctx))
    assert proc.returncode == 5, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "DSH_TURN_FAILED"
    assert [p["phase"] for p in out["phases"]] == ["red", "red"]
    assert out["phases"][1]["gate"] is None
    assert out["phases"][1]["turn_state"] == guard.TURN_FAILED_DIRTY
    assert len(pc._calls(ctx)) == 2


def test_nonzero_initial_red_turn_stops_without_gate(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [_red("s-red", BAD_TEST, goal=True, exit=3), _red("s-x", GOOD_TEST)]
    proc = _start_red(ctx, plan, "--auto-repair-red", "3")
    assert proc.returncode == 3
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "DSH_TURN_FAILED"
    assert out["final_decision"] is None
    assert out["phases"][0]["gate"] is None
    assert len(pc._calls(ctx)) == 1


def test_red_gate_environment_failure_does_not_spend_budget(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    (ctx["repo"] / ".venv" / "bin" / "python").unlink()
    plan = [_red("s-red", GOOD_TEST, goal=True), _red("s-x", GOOD_TEST)]
    proc = _start_red(ctx, plan, "--auto-repair-red", "3")
    assert proc.returncode == guard.EXIT_BLOCKED
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "RED_GATE_ENVIRONMENT_FAILURE"
    assert out["phases"][0]["gate"]["reason_codes"] == ["ENVIRONMENT_FAILURE"]
    assert out["red_repairs_used"] == 0
    assert len(pc._calls(ctx)) == 1


def test_continue_to_green_runs_green_chain_with_exact_red_continuity(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [
        _red("s-red", BAD_TEST, goal=True),
        _red("s-red-repair-1", GOOD_TEST),
        {"session": "s-green", "write": pc._value(2)},
        {"session": "s-repair-1", "write": pc._value(3)},
        {"session": "s-unused", "write": pc._value(9)},
    ]
    proc = _start_red(ctx, plan, "--auto-repair-red", "2", "--auto-repair", "1", *_green_args(ctx))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "GREEN_READY"
    assert out["final_decision"] == "GREEN_READY"
    assert [p["phase"] for p in out["phases"]] == ["red", "red", "green", "repair"]
    kinds = [(p["gate"]["kind"], p["gate"]["decision"]) for p in out["phases"]]
    assert kinds == [
        ("red", "REVISE_RED"),
        ("red", "RED_READY"),
        ("green", "REVISE_GREEN"),
        ("green", "GREEN_READY"),
    ]
    assert out["red_repairs_used"] == 1 and out["repairs_used"] == 1
    red_ready = out["phases"][1]["gate"]
    assert out["red_receipt_path"] == red_ready["receipt_path"]
    assert out["red_receipt_hash"] == red_ready["receipt_hash"]
    # GREEN is lineage-bound to the RED_READY session, its contract and its receipt.
    green = out["phases"][2]
    assert green["parent_session_id"] == "s-red-repair-1"
    assert green["contract_path"] == str(ctx["green_phase"].resolve())
    assert out["phases"][3]["parent_session_id"] == "s-green"
    red_line = f"- {red_ready['receipt_path']} receipt_hash={red_ready['receipt_hash']}"
    calls = pc._calls(ctx)
    assert len(calls) == 4
    green_task = calls[2][-1]
    assert "Phase: green" in green_task
    assert red_line in green_task
    assert green_task.rstrip().endswith("GREEN_PHASE_BODY allowed: mod.py")
    assert f"`{out['green_gate_command']}`" in green_task
    assert "Before claiming RED_READY" not in green_task
    assert red_line in calls[3][-1]
    red_receipt = json.loads(Path(red_ready["receipt_path"]).read_text(encoding="utf-8"))
    for entry in out["phases"][2:]:
        receipt = json.loads(Path(entry["gate"]["receipt_path"]).read_text(encoding="utf-8"))
        assert receipt["base_revision"] == red_receipt["base_revision"] == ctx["base"]
        assert receipt["contract_hash"] == out["green_contract_hash"]


def test_continue_to_green_not_started_without_red_ready(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    plan = [_red("s-red", BAD_TEST, goal=True), {"session": "s-green", "write": pc._value(3)}]
    proc = _start_red(ctx, plan, *_green_args(ctx))
    assert proc.returncode == guard.EXIT_BLOCKED
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "RED_AUTO_REPAIR_EXHAUSTED"
    assert [p["phase"] for p in out["phases"]] == ["red"]
    assert len(pc._calls(ctx)) == 1


def test_red_contract_drift_during_turn_fails_closed(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    drifted = json.loads(ctx["red"].read_text(encoding="utf-8"))
    drifted["invariant"] = "weakened"
    step = _red("s-red", GOOD_TEST, goal=True)
    step["write"][str(ctx["red"])] = json.dumps(drifted)
    proc = _start_red(
        ctx, [step, _red("s-x", GOOD_TEST)], "--auto-repair-red", "3", *_green_args(ctx)
    )
    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    out = pc._chain(ctx, proc)
    assert out["stop_reason"] == "RED_CONTRACT_DRIFT"
    assert out["red_receipt_path"] is None
    assert out["red_repairs_used"] == 0
    assert len(pc._calls(ctx)) == 1


def test_tampered_red_receipt_blocks_continue_to_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _setup(tmp_path)
    original = guard.persist_red_gate_with_sidecar

    def tamper(root, receipt, *, repo, base):
        path = original(root, receipt, repo=repo, base=base)
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        payload["base_revision"] = "0" * 40
        Path(path).write_text(json.dumps(payload), encoding="utf-8")
        return path

    monkeypatch.setattr(guard, "persist_red_gate_with_sidecar", tamper)
    plan = [_red("s-red", GOOD_TEST, goal=True), {"session": "s-green", "write": pc._value(3)}]
    ctx["plan"].write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setenv("FAKE_DSH_CALLS", str(ctx["calls"]))
    monkeypatch.setenv("FAKE_DSH_PLAN", str(ctx["plan"]))
    code = guard.main([
        "start-phase",
        "--repository",
        pc.REPO,
        "--issue",
        str(pc.ISSUE),
        "--phase",
        "red",
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
        "--red-contract",
        str(ctx["red"]),
        *_green_args(ctx),
    ])
    out = json.loads(capsys.readouterr().out)
    assert code == guard.EXIT_BLOCKED
    assert out["stop_reason"] == "RED_RECEIPT_INVALID"
    assert out["red_receipt_path"] is None
    assert [p["phase"] for p in out["phases"]] == ["red"]
    assert len(pc._calls(ctx)) == 1


@pytest.mark.parametrize(
    ("phase", "extra"),
    [
        ("red", ["--auto-repair-red", "4"]),
        ("red", ["--auto-repair-red", "-1"]),
        ("green", []),
        ("red", ["--continue-to-green"]),
        ("red", ["--continue-to-green", "--green-contract", "GREEN"]),
        ("red", ["--green-phase-contract", "GREEN_PHASE"]),
        ("red", ["--red-receipt", "RED_RECEIPT"]),
    ],
)
def test_invalid_red_chain_arguments_block_before_spawn(
    tmp_path: Path, phase: str, extra: list[str]
) -> None:
    ctx = _setup(tmp_path)
    subst = {
        "GREEN": str(ctx["green"]),
        "GREEN_PHASE": str(ctx["green_phase"]),
        "RED_RECEIPT": str(ctx["red"]),
    }
    argv = ["--red-contract", str(ctx["red"]), *(subst.get(a, a) for a in extra)]
    proc = pc._start(ctx, [_red("s", GOOD_TEST, goal=True)], *argv, phase=phase)
    assert proc.returncode == guard.EXIT_BLOCKED
    assert json.loads(proc.stdout)["reason_code"] == "START_PHASE_ARGUMENT_INVALID"
    assert pc._calls(ctx) == []


def test_red_budget_and_continue_require_red_contract(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    for extra in (["--auto-repair-red", "1"], _green_args(ctx)):
        proc = pc._start(ctx, [_red("s", GOOD_TEST, goal=True)], *extra, phase="red")
        assert json.loads(proc.stdout)["reason_code"] == "START_PHASE_ARGUMENT_INVALID"
    assert pc._calls(ctx) == []


def test_red_contract_bound_to_other_issue_blocks_before_spawn(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    other = json.loads(ctx["red"].read_text(encoding="utf-8"))
    other["issue_number"] = pc.ISSUE + 1
    ctx["red"].write_text(json.dumps(other), encoding="utf-8")
    proc = _start_red(ctx, [_red("s", GOOD_TEST, goal=True)])
    assert proc.returncode == guard.EXIT_BLOCKED
    assert json.loads(proc.stdout)["reason_code"] == "RED_CONTRACT_INVALID"
    assert pc._calls(ctx) == []
