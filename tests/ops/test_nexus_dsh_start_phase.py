from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_start_phase_test", str(SCRIPT)).load_module()
REPO = "James3014/Nexus-new"

FAKE_DSH = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ['FAKE_DSH_MARKER']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
sid = os.environ.get('FAKE_DSH_SESSION', 'session-phase-1')
if sid != 'NONE':
    print(json.dumps({'type': 'session', 'sessionId': sid, 'cwd': os.getcwd()}))
if os.environ.get('FAKE_DSH_GOAL'):
    print(json.dumps({'type': 'goal/change', 'data': {'kind': 'goal/change',
        'operation': 'create', 'goal': {'id': 'goal-p', 'revision': 1,
        'objective': 'FIX_1646'}}}))
edit = os.environ.get('FAKE_DSH_EDIT')
if edit:
    Path(edit).write_text('changed = 1\\n')
sys.exit(int(os.environ.get('FAKE_DSH_EXIT', '0')))
"""


def _doctor_payload(state: str) -> dict:
    return {
        "schema": guard.DOCTOR_SCHEMA,
        "claim_ceiling": guard.DOCTOR_CLAIM_CEILING,
        "resume_disposition": "SAFE",
        "next_gate": {"code": "CONTINUE_BOUNDED_ISSUE_WORK"},
        "source": {"status": "OBSERVED", "head": "a" * 40, "github_main": "b" * 40},
        "task": {
            "status": "OBSERVED",
            "state": state,
            "issue_number": 1646,
            "updated_at": "2026-10-08T00:00:00Z",
            "url": "https://example.invalid/1646",
        },
    }


def _setup(tmp_path: Path, *, issue_state: str = "open") -> dict:
    repo = tmp_path / "repo"
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
    doctor = tmp_path / "doctor"
    doctor.write_text(
        f"#!/usr/bin/env python3\nimport json\nprint(json.dumps({_doctor_payload(issue_state)!r}))\n",
        encoding="utf-8",
    )
    doctor.chmod(0o755)
    dsh = tmp_path / "dsh"
    dsh.write_text(FAKE_DSH, encoding="utf-8")
    dsh.chmod(0o755)
    contract = tmp_path / "contract.md"
    contract.write_text("CONTRACT_BODY allowed: mod.py\n", encoding="utf-8")
    (tmp_path / "dsh-home").mkdir()
    return {
        "repo": repo,
        "doctor": doctor,
        "dsh": dsh,
        "contract": contract,
        "state": tmp_path / "state",
        "marker": tmp_path / "marker.json",
        "home": tmp_path / "dsh-home",
    }


def _start(ctx: dict, phase: str, *extra: str, env: dict[str, str] | None = None):
    full = os.environ.copy()
    full["FAKE_DSH_MARKER"] = str(ctx["marker"])
    for key in ("FAKE_DSH_GOAL", "FAKE_DSH_EDIT", "FAKE_DSH_EXIT", "FAKE_DSH_SESSION"):
        full.pop(key, None)
    full.update(env or {})
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
        env=full,
    )


def test_red_phase_creates_binding_with_goal(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    proc = _start(ctx, "red", env={"FAKE_DSH_GOAL": "1"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["schema"] == "nexus.dsh_phase_run.v1"
    assert out["session_id"] == "session-phase-1"
    assert out["turn_state"] == "TURN_OK"
    assert Path(out["log_path"]).parent.name == "1646"
    assert Path(out["log_path"]).name.endswith("-red.log")
    binding = guard.load_binding(ctx["state"], "session-phase-1")
    assert binding["goal_id"] == "goal-p"
    assert binding["phase"] == "red"
    assert binding["binding_hash"] == out["binding_hash"]
    argv = json.loads(ctx["marker"].read_text())
    assert argv[:3] == ["--profile", "headless", "--json"]
    assert "--session-id" not in argv


def test_green_phase_without_goal_binds_with_lineage_and_header(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    receipt = tmp_path / "red.json"
    receipt.write_text(json.dumps({"receipt_hash": "sha256:abc123"}), encoding="utf-8")
    proc = _start(
        ctx,
        "green",
        "--parent-session-id",
        "session-parent",
        "--prior-receipt",
        str(receipt),
        "--goal-objective",
        "FIX_1646",
        "--patch",
        "p1",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["parent_session_id"] == "session-parent"
    binding = guard.load_binding(ctx["state"], out["session_id"])
    assert binding["goal_id"] is None
    assert binding["phase"] == "green"
    assert binding["parent_session_id"] == "session-parent"
    argv = json.loads(ctx["marker"].read_text())
    assert argv[:5] == ["--profile", "headless", "--patch", "p1", "--json"]
    task = argv[-1]
    assert "Phase: green" in task
    assert "Goal objective: FIX_1646" in task
    assert "Do not call create_goal unless phase=red and no goal exists." in task
    assert "NOT allowed" in task
    assert "Every bash action must include a short description." in task
    assert "never re-run insertion scripts; no helper/scratch files" in task
    assert "receipt_hash=sha256:abc123" in task
    assert task.rstrip().endswith("CONTRACT_BODY allowed: mod.py")


def test_legacy_binding_hash_unchanged_without_lineage(tmp_path: Path) -> None:
    log = tmp_path / "l.jsonl"
    log.write_text(
        json.dumps({"type": "session", "sessionId": "s1"})
        + "\n"
        + json.dumps({
            "type": "goal/change",
            "data": {
                "kind": "goal/change",
                "operation": "create",
                "goal": {"id": "g", "revision": 1, "objective": "O"},
            },
        })
        + "\n",
        encoding="utf-8",
    )
    binding = guard.build_binding_from_log(
        log_path=log, repository=REPO, issue_number=1, repo_root=tmp_path, dsh_home=tmp_path
    )
    assert "phase" not in binding and "parent_session_id" not in binding
    guard.validate_binding(binding)


def test_closed_issue_blocks_before_spawn(tmp_path: Path) -> None:
    ctx = _setup(tmp_path, issue_state="closed")
    proc = _start(ctx, "red", env={"FAKE_DSH_GOAL": "1"})
    assert proc.returncode == guard.EXIT_BLOCKED
    out = json.loads(proc.stdout)
    assert out["decision"] == "BLOCK_RESUME"
    assert out["reason_code"] == "TRACKED_ISSUE_TERMINAL"
    assert not ctx["marker"].exists()


def test_dirty_sibling_session_blocks_new_phase(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    failed = _start(
        ctx,
        "red",
        env={
            "FAKE_DSH_GOAL": "1",
            "FAKE_DSH_EDIT": str(ctx["repo"] / "mod.py"),
            "FAKE_DSH_EXIT": "3",
        },
    )
    assert failed.returncode == 3
    assert json.loads(failed.stdout)["turn_state"] == guard.TURN_FAILED_DIRTY
    ctx["marker"].unlink()
    proc = _start(ctx, "green", env={"FAKE_DSH_SESSION": "session-phase-2"})
    assert proc.returncode == guard.EXIT_BLOCKED
    out = json.loads(proc.stdout)
    assert out["reason_code"] == "PREVIOUS_TURN_FAILED_DIRTY"
    assert out["provider_invocation_allowed"] is False
    assert out["blocking_session_id"] == "session-phase-1"
    assert not ctx["marker"].exists()


def test_failing_dsh_with_edits_is_failed_dirty_and_quarantined(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    proc = _start(
        ctx,
        "repair",
        env={"FAKE_DSH_EDIT": str(ctx["repo"] / "mod.py"), "FAKE_DSH_EXIT": "5"},
    )
    assert proc.returncode == 5
    out = json.loads(proc.stdout)
    assert out["turn_state"] == guard.TURN_FAILED_DIRTY
    state = guard.load_turn_state(ctx["state"], out["session_id"])
    assert state is not None and Path(state["quarantine_receipt"]).is_file()
    assert (ctx["repo"] / "mod.py").read_text() == "changed = 1\n"


def test_unobserved_session_fails_closed(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    proc = _start(ctx, "green", env={"FAKE_DSH_SESSION": "NONE"})
    assert proc.returncode == guard.EXIT_BLOCKED
    out = json.loads(proc.stdout)
    assert out["session_id"].startswith("start-phase-unobserved-")
    assert out["turn_state"] == guard.TURN_FAILED_DIRTY
    assert out["binding_hash"] is None
    assert _start(ctx, "green").returncode == guard.EXIT_BLOCKED
