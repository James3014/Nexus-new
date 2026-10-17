"""No-progress watchdog and tool-output cap for DSH phase runs (Nexus-new#2537)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
ADAPTER_DIR = ROOT / "scripts" / "ops" / "dsh-agy-adapter"
guard = SourceFileLoader("nexus_dsh_workflow_no_progress_test", str(SCRIPT)).load_module()

REPO = "James3014/Nexus-new"
STEP_END = json.dumps({"type": "status", "phase": "step_end", "turn": 2, "step": 1})
COMPACTION = "NEXUS_DSH_AGY_OPERATION " + json.dumps({
    "schema": "nexus.dsh_agy_operation_marker.v1",
    "dsh_session_id": "s",
    "operation_id": "agyop_" + "a" * 32,
    "purpose": "compaction",
})
AGENT_OP = COMPACTION.replace("compaction", "agent")


class Snap:
    """Scriptable worktree snapshot: bump() simulates an edit."""

    def __init__(self) -> None:
        self.value = 0

    def __call__(self):
        return {"worktree_diff_sha256": str(self.value)}

    def bump(self) -> None:
        self.value += 1


def _feed(dog, lines):
    for line in lines:
        reasons = dog.feed_line(line)
        if reasons:
            return reasons
    return []


def test_steps_without_diff_change_trigger_no_progress() -> None:
    dog = guard.NoProgressWatchdog(Snap(), max_steps=40, max_compactions=3)
    assert _feed(dog, [STEP_END] * 39) == []
    assert _feed(dog, [STEP_END]) == ["NO_PROGRESS_STEPS"]


def test_diff_change_resets_step_counter() -> None:
    snap = Snap()
    dog = guard.NoProgressWatchdog(snap, max_steps=40, max_compactions=3)
    for _ in range(5):
        assert _feed(dog, [STEP_END] * 30) == []
        snap.bump()
    # the first event after a change is the one that observes it and resets the counter
    assert _feed(dog, [STEP_END] * 40) == []
    assert _feed(dog, [STEP_END]) == ["NO_PROGRESS_STEPS"]


def test_compaction_threshold_triggers_and_ignores_other_purposes() -> None:
    dog = guard.NoProgressWatchdog(Snap(), max_steps=1000, max_compactions=3)
    assert _feed(dog, [AGENT_OP, COMPACTION, COMPACTION]) == []
    assert _feed(dog, [COMPACTION]) == ["NO_PROGRESS_COMPACTIONS"]


def test_compaction_counter_resets_on_diff_change() -> None:
    snap = Snap()
    dog = guard.NoProgressWatchdog(snap, max_steps=1000, max_compactions=3)
    assert _feed(dog, [COMPACTION, COMPACTION]) == []
    snap.bump()
    assert _feed(dog, [COMPACTION] * 3) == []
    assert _feed(dog, [COMPACTION]) == ["NO_PROGRESS_COMPACTIONS"]


def test_unreadable_snapshot_counts_as_progress_and_zero_disables() -> None:
    dog = guard.NoProgressWatchdog(lambda: None, max_steps=2, max_compactions=1)
    assert _feed(dog, [STEP_END] * 10 + [COMPACTION] * 5) == []
    off = guard.NoProgressWatchdog(Snap(), max_steps=0, max_compactions=0)
    assert _feed(off, [STEP_END] * 100 + [COMPACTION] * 10) == []


def test_garbage_lines_are_ignored() -> None:
    dog = guard.NoProgressWatchdog(Snap(), max_steps=1, max_compactions=1)
    assert (
        _feed(dog, ["", "not json", "{broken", '{"type":"status"}', "NEXUS_DSH_AGY_OPERATION {"])
        == []
    )


FAKE_DSH = """#!/usr/bin/env python3
import json, os, signal, sys, time
from pathlib import Path
if os.environ.get('FAKE_DSH_EXIT0_ON_TERM'):
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
print(json.dumps({'type': 'session', 'sessionId': 'sess-np', 'cwd': os.getcwd()}), flush=True)
edit = os.environ.get('FAKE_DSH_EDIT_AT')
for i in range(int(os.environ['FAKE_DSH_STEPS'])):
    if edit and i == int(edit):
        Path(os.environ['FAKE_DSH_EDIT_FILE']).write_text('changed = %d\\n' % i)
    print(json.dumps({'type': 'status', 'phase': 'step_end', 'turn': 2, 'step': i}), flush=True)
    time.sleep(float(os.environ.get('FAKE_DSH_STEP_SLEEP', '0')))
Path(os.environ['FAKE_DSH_PID_FILE']).write_text(str(os.getpid()))
time.sleep(float(os.environ.get('FAKE_DSH_LINGER', '0')))
"""


def _setup(base: Path) -> dict:
    repo = base / "repo"
    repo.mkdir()
    for cmd in (
        ["init", "-q"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    (repo / "mod.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    payload = {
        "schema": guard.DOCTOR_SCHEMA,
        "claim_ceiling": guard.DOCTOR_CLAIM_CEILING,
        "resume_disposition": "SAFE",
        "next_gate": {"code": "CONTINUE_BOUNDED_ISSUE_WORK"},
        "source": {"status": "OBSERVED", "head": "a" * 40, "github_main": "b" * 40},
        "task": {
            "status": "OBSERVED",
            "state": "open",
            "issue_number": 1646,
            "updated_at": "2026-10-08T00:00:00Z",
            "url": "https://example.invalid/1646",
        },
    }
    doctor = base / "doctor"
    doctor.write_text(
        f"#!/usr/bin/env python3\nimport json\nprint(json.dumps({payload!r}))\n", encoding="utf-8"
    )
    doctor.chmod(0o755)
    dsh = base / "dsh"
    dsh.write_text(FAKE_DSH, encoding="utf-8")
    dsh.chmod(0o755)
    contract = base / "contract.md"
    contract.write_text("CONTRACT_BODY allowed: mod.py\n", encoding="utf-8")
    (base / "dsh-home").mkdir()
    return {
        "repo": repo,
        "doctor": doctor,
        "dsh": dsh,
        "contract": contract,
        "state": base / "state",
        "home": base / "dsh-home",
        "pid_file": base / "pid.txt",
    }


def _start(ctx: dict, env: dict[str, str], *extra: str) -> subprocess.CompletedProcess[str]:
    full = os.environ.copy()
    full["FAKE_DSH_PID_FILE"] = str(ctx["pid_file"])
    full.update(env)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "start-phase",
            "--repository",
            REPO,
            "--issue",
            "1646",
            "--phase",
            "repair",
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
        env=full,
        timeout=60,
    )


@pytest.fixture
def ctx(dsh_non_temp_path: Path) -> dict:
    return _setup(dsh_non_temp_path)


def test_start_phase_stops_scripted_no_progress_stream(ctx: dict) -> None:
    proc = _start(ctx, {"FAKE_DSH_STEPS": "6", "FAKE_DSH_LINGER": "30"}, "--no-progress-steps", "5")
    assert proc.returncode == guard.EXIT_NO_PROGRESS, proc.stderr
    out = json.loads(proc.stdout)
    assert out["decision"] == "NO_PROGRESS"
    assert out["reason_codes"] == ["NO_PROGRESS_STEPS"]
    assert out["no_progress"]["max_steps"] == 5
    # The fake DSH lingers 30 s after its last step; the watchdog must have killed it.
    assert out["phase_wall_ms"] < 20_000
    assert not ctx["pid_file"].exists() or not _alive(int(ctx["pid_file"].read_text()))


def test_start_phase_does_not_stop_stream_with_diff_changes(ctx: dict) -> None:
    proc = _start(
        ctx,
        {
            "FAKE_DSH_STEPS": "10",
            "FAKE_DSH_STEP_SLEEP": "0.15",
            "FAKE_DSH_EDIT_AT": "3",
            "FAKE_DSH_EDIT_FILE": str(ctx["repo"] / "mod.py"),
        },
        "--no-progress-steps",
        "8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert "decision" not in out or out["decision"] != "NO_PROGRESS"
    assert out["turn_state"] == guard.TURN_OK


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None and not os.environ.get("CI"), reason="node not installed")
def test_adapter_caps_each_tool_result_with_truncation_note(tmp_path: Path) -> None:
    assert NODE is not None, "node is required in CI"
    runtime = tmp_path / "runtime"
    adapter = runtime / "node_modules" / "@nexus" / "dsh-llm-agy-pilot"
    dependency = runtime / "node_modules" / "@deepseek-ai" / "dsh-llm"
    adapter.parent.mkdir(parents=True)
    dependency.mkdir(parents=True)
    shutil.copytree(ADAPTER_DIR, adapter)
    (dependency / "package.json").write_text(
        json.dumps({"name": "@deepseek-ai/dsh-llm", "type": "module", "exports": "./index.js"}),
        encoding="utf-8",
    )
    (dependency / "index.js").write_text(
        "export class LlmAdapter {}\n"
        "export class LlmError extends Error { constructor(m, c, o={}) { super(m, o); this.code=c } }\n",
        encoding="utf-8",
    )
    script = tmp_path / "probe.mjs"
    script.write_text(
        f"import {{ capToolResultMessages, TOOL_RESULT_CAP_CHARS }} from {json.dumps(str(adapter / 'index.js'))}\n"
        "const big = 'x'.repeat(50000), small = 'ok'\n"
        "const msgs = Object.freeze([\n"
        " {role:'user', content:[{type:'text', text: big}]},\n"
        " {role:'tool', callId:'c1', isError:false, content:[{type:'text', text: big}]},\n"
        " {role:'tool', callId:'c2', isError:false, content:[{type:'text', text: small}]},\n"
        "])\n"
        "const out = capToolResultMessages(msgs)\n"
        "console.log(JSON.stringify({cap: TOOL_RESULT_CAP_CHARS, user: out[0].content[0].text.length,"
        " big: out[1].content[0].text, small: out[2].content[0].text, callId: out[1].callId}))\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, check=True, cwd=str(tmp_path)
    )
    got = json.loads(proc.stdout)
    assert got["cap"] == 8192
    assert got["user"] == 50000  # only tool results are capped
    assert got["small"] == "ok"
    assert got["callId"] == "c1"
    assert got["big"].startswith("x" * 8192)
    assert "TRUNCATED" in got["big"] and "50000" in got["big"]
    assert len(got["big"]) < 8192 + 300


def _dsh_exits_zero_on_sigterm_env(ctx: dict) -> dict[str, str]:
    # The installed DSH handles SIGTERM with interrupt(0): the child exits 0 after a stop.
    return {
        "FAKE_DSH_STEPS": "8",
        "FAKE_DSH_STEP_SLEEP": "0.05",
        "FAKE_DSH_LINGER": "30",
        "FAKE_DSH_EXIT0_ON_TERM": "1",
        "FAKE_DSH_EDIT_AT": "0",
        "FAKE_DSH_EDIT_FILE": str(ctx["repo"] / "mod.py"),
    }


def test_sigterm_exit_zero_with_dirty_worktree_is_quarantined(ctx: dict) -> None:
    env = _dsh_exits_zero_on_sigterm_env(ctx)
    env["FAKE_DSH_STEPS"] = "30"
    # Edit at step 0 is progress; later steps then stall until the threshold.
    proc = _start(ctx, env, "--no-progress-steps", "5")
    assert proc.returncode == guard.EXIT_NO_PROGRESS, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["decision"] == "NO_PROGRESS"
    assert out["dsh_exit_code"] == 0
    assert out["turn_state"] == guard.TURN_FAILED_DIRTY
    state = guard.load_turn_state(ctx["state"], out["session_id"])
    assert state is not None
    assert Path(state["quarantine_receipt"]).is_file()
    patches = list((ctx["state"] / "quarantine" / out["session_id"]).glob("*.patch"))
    assert patches and b"changed" in patches[0].read_bytes()
