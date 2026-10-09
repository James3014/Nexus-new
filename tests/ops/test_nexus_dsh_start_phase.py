from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

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
        'objective': 'FIX_1646',
        'maxGoalRounds': int(os.environ.get('FAKE_DSH_MAX_ROUNDS', '1'))}}}))
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
    for key in (
        "FAKE_DSH_GOAL",
        "FAKE_DSH_MAX_ROUNDS",
        "FAKE_DSH_EDIT",
        "FAKE_DSH_EXIT",
        "FAKE_DSH_SESSION",
    ):
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


def test_red_phase_rejects_goal_not_capped_to_one_round(tmp_path: Path) -> None:
    ctx = _setup(tmp_path)
    proc = _start(ctx, "red", env={"FAKE_DSH_GOAL": "1", "FAKE_DSH_MAX_ROUNDS": "256"})
    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["binding_error"].startswith("DSH_GOAL_ROUND_CAP_MISMATCH")
    with pytest.raises(guard.DshWorkflowError):
        guard.load_binding(ctx["state"], "session-phase-1")


def test_red_create_goal_header_caps_goal_rounds_to_one() -> None:
    task = guard.build_phase_task(
        phase="red",
        goal_objective="FIX_1666",
        parent_has_goal=False,
        prior_receipts=[],
        contract_text="C",
    )
    assert "call it once with the goal objective above and max_goal_rounds=1" in task
    green = guard.build_phase_task(
        phase="green",
        goal_objective="FIX_1666",
        parent_has_goal=True,
        prior_receipts=[],
        contract_text="C",
    )
    assert "max_goal_rounds" not in green


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


_REF_PREFIX = "dsh_action_contract:v1:catalog_count=1:catalog_sha256=abc:"
OP_A = "agyop_0a7c3f03cdca4177bf8f4343e8f2aadd"
OP_B = "agyop_545bea0c8f1d4b2e9a6d7c3e1f0b9a84"
OP_T = "agyop_20ba1f7e6d5c4b3a2918f7e6d5c4b3a2"
OP_E0 = "agyop_840753ab12cd34ef56ab78cd90ef12ab"
OP_E1 = "agyop_11aa22bb33cc44dd55ee66ff77008899"
OP_E2 = "agyop_99887766554433221100ffeeddccbbaa"
OP_U = "agyop_aabbccddeeff00112233445566778899"
OP_C = "agyop_cafebabecafebabecafebabecafebabe"
OP_X = "agyop_deadbeefdeadbeefdeadbeefdeadbeef"


def _ref(chars: int) -> str:
    return f"{_REF_PREFIX}prompt_chars={chars}:context_window=262144"


def _sref(session: str, purpose: str = "agent") -> str:
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()
    return f"dsh_session:v1:session_sha256={digest}:purpose={purpose}"


def _marker(session: str, op: str, purpose: str = "agent") -> str:
    payload = {
        "schema": "nexus.dsh_agy_operation_marker.v1",
        "dsh_session_id": session,
        "operation_id": op,
        "purpose": purpose,
    }
    return "NEXUS_DSH_AGY_OPERATION " + json.dumps(payload)


FAKE_STATUS_DISPATCH = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
fixtures = json.loads(Path(os.environ['FAKE_STATUS_FIXTURES']).read_text())
op = sys.argv[sys.argv.index('--status') + 1]
entry = fixtures.get(op)
if entry is None or 'exit' in entry:
    sys.exit(3)
print(json.dumps(entry['status']))
"""


def _canonical_env(tmp_path: Path, monkeypatch, ops: dict[str, dict]) -> None:
    fixtures = {}
    for op_id, spec in ops.items():
        if spec.get("unavailable"):
            fixtures[op_id] = {"exit": 3}
            continue
        fixtures[op_id] = {
            "status": {
                "operation_id": spec.get("status_id", op_id),
                "status": "COMPLETED",
                "evidence_refs": spec.get("refs", []),
            }
        }
    fx = tmp_path / "fixtures.json"
    fx.write_text(json.dumps(fixtures), encoding="utf-8")
    dispatch = tmp_path / "fake-status-dispatch"
    dispatch.write_text(FAKE_STATUS_DISPATCH, encoding="utf-8")
    dispatch.chmod(0o755)
    monkeypatch.setenv("NEXUS_AGY_DISPATCH", str(dispatch))
    monkeypatch.setenv("FAKE_STATUS_FIXTURES", str(fx))


def _phase_log(tmp_path: Path, lines: list[str]) -> Path:
    log = tmp_path / "phase.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


def test_reader_accepts_only_marked_session_bound_canonical_prompt_chars(
    tmp_path: Path, monkeypatch
) -> None:
    _canonical_env(
        tmp_path,
        monkeypatch,
        {
            OP_A: {"refs": [_ref(58819), _sref("S-main")]},
            OP_B: {"refs": [_ref(111), _sref("S-other")]},
        },
    )
    log = _phase_log(
        tmp_path,
        [
            _marker("S-main", OP_A),
            "gateway_prompt_chars=416 unrelated Gateway metric 688",
            _marker("S-other", OP_B),
        ],
    )
    out = guard.read_canonical_agy_operations(log, "S-main")
    assert out["coverage"] == "OBSERVED_NON_EXHAUSTIVE"
    assert out["exhaustive"] is False
    assert out["operations"] == [
        {
            "operation_id": OP_A,
            "purpose": "agent",
            "status": "COMPLETED",
            "prompt_chars": 58819,
            "prompt_chars_unit": "characters",
            "evidence": "CANONICAL",
            "reason": None,
        }
    ]


def test_reader_keeps_auxiliary_purpose_distinct(tmp_path: Path, monkeypatch) -> None:
    _canonical_env(
        tmp_path, monkeypatch, {OP_T: {"refs": [_ref(1971), _sref("S-main", "session-title")]}}
    )
    log = _phase_log(tmp_path, [_marker("S-main", OP_T, "session-title")])
    op = guard.read_canonical_agy_operations(log, "S-main")["operations"][0]
    assert op["purpose"] == "session-title"
    assert op["prompt_chars"] == 1971
    assert "tokens" not in op


def test_reader_without_any_marker_is_non_exhaustive(tmp_path: Path, monkeypatch) -> None:
    _canonical_env(tmp_path, monkeypatch, {})
    log = _phase_log(tmp_path, ["gateway_prompt_chars=416"])
    assert guard.read_canonical_agy_operations(log, "S-main") == {
        "schema": guard.AGY_OPERATION_SUMMARY_SCHEMA,
        "session_id": "S-main",
        "coverage": "NON_EXHAUSTIVE_NO_MARKER",
        "exhaustive": False,
        "operations": [],
    }


def test_reader_substituted_operation_id_is_unknown(tmp_path: Path, monkeypatch) -> None:
    _canonical_env(
        tmp_path, monkeypatch, {OP_X: {"refs": [_ref(9), _sref("S-main")], "status_id": OP_A}}
    )
    log = _phase_log(tmp_path, [_marker("S-main", OP_X)])
    op = guard.read_canonical_agy_operations(log, "S-main")["operations"][0]
    assert op["evidence"] == "UNKNOWN"
    assert op["prompt_chars"] is None
    assert op["reason"] == "RECORD_OPERATION_MISMATCH"


def test_reader_forged_session_marker_is_unknown(tmp_path: Path, monkeypatch) -> None:
    # The canonical record belongs to S-other; a marker claiming S-main must not be accepted.
    _canonical_env(tmp_path, monkeypatch, {OP_X: {"refs": [_ref(58819), _sref("S-other")]}})
    log = _phase_log(tmp_path, [_marker("S-main", OP_X)])
    op = guard.read_canonical_agy_operations(log, "S-main")["operations"][0]
    assert op["evidence"] == "UNKNOWN"
    assert op["prompt_chars"] is None
    assert op["reason"] == "SESSION_EVIDENCE_MISMATCH"


def test_reader_missing_or_conflicting_evidence_is_unknown(tmp_path: Path, monkeypatch) -> None:
    _canonical_env(
        tmp_path,
        monkeypatch,
        {
            OP_E0: {"refs": [_sref("S-main")]},
            OP_E1: {"refs": [_ref(5), _ref(6), _sref("S-main")]},
            OP_E2: {"refs": [_ref(4)]},
        },
    )
    log = _phase_log(
        tmp_path, [_marker("S-main", OP_E0), _marker("S-main", OP_E1), _marker("S-main", OP_E2)]
    )
    ops = {
        op["operation_id"]: op
        for op in guard.read_canonical_agy_operations(log, "S-main")["operations"]
    }
    assert ops[OP_E0]["reason"] == "EVIDENCE_MISSING"
    assert ops[OP_E1]["reason"] == "EVIDENCE_CONFLICT"
    assert ops[OP_E2]["reason"] == "SESSION_EVIDENCE_MISSING"
    assert all(ops[op]["prompt_chars"] is None for op in (OP_E0, OP_E1, OP_E2))


def test_reader_unavailable_status_is_unknown(tmp_path: Path, monkeypatch) -> None:
    _canonical_env(tmp_path, monkeypatch, {OP_U: {"unavailable": True}})
    log = _phase_log(tmp_path, [_marker("S-main", OP_U)])
    op = guard.read_canonical_agy_operations(log, "S-main")["operations"][0]
    assert op["evidence"] == "UNKNOWN"
    assert op["reason"] == "STATUS_UNAVAILABLE"


def test_reader_malformed_or_conflicting_markers_are_unknown(tmp_path: Path, monkeypatch) -> None:
    _canonical_env(tmp_path, monkeypatch, {OP_C: {"refs": [_ref(7), _sref("S-main")]}})
    log = _phase_log(
        tmp_path,
        [
            "NEXUS_DSH_AGY_OPERATION {not json",
            _marker("S-main", OP_C, "agent"),
            _marker("S-main", OP_C, "compaction"),
        ],
    )
    out = guard.read_canonical_agy_operations(log, "S-main")
    malformed = [op for op in out["operations"] if op["operation_id"] is None]
    assert malformed and malformed[0]["reason"] == "MARKER_MALFORMED"
    conflict = [op for op in out["operations"] if op["operation_id"] == OP_C]
    assert conflict[0]["evidence"] == "UNKNOWN"
    assert conflict[0]["reason"] == "MARKER_CONFLICT"
    assert conflict[0]["prompt_chars"] is None


def test_reader_unrelated_session_markers_only_stay_non_exhaustive(
    tmp_path: Path, monkeypatch
) -> None:
    _canonical_env(tmp_path, monkeypatch, {OP_B: {"refs": [_ref(111), _sref("S-other")]}})
    log = _phase_log(tmp_path, [_marker("S-other", OP_B)])
    out = guard.read_canonical_agy_operations(log, "S-main")
    assert out["coverage"] == "NON_EXHAUSTIVE_NO_MARKER"
    assert out["exhaustive"] is False
    assert out["operations"] == []


def test_reader_duplicate_identical_action_refs_are_unknown(tmp_path: Path, monkeypatch) -> None:
    _canonical_env(
        tmp_path, monkeypatch, {OP_A: {"refs": [_ref(58819), _ref(58819), _sref("S-main")]}}
    )
    log = _phase_log(tmp_path, [_marker("S-main", OP_A)])
    op = guard.read_canonical_agy_operations(log, "S-main")["operations"][0]
    assert op["evidence"] == "UNKNOWN"
    assert op["prompt_chars"] is None
    assert op["reason"] == "EVIDENCE_DUPLICATE"


def test_reader_unreadable_log_is_unknown(tmp_path: Path, monkeypatch) -> None:
    _canonical_env(tmp_path, monkeypatch, {})
    out = guard.read_canonical_agy_operations(tmp_path / "missing.log", "S-main")
    assert out["coverage"] == "UNKNOWN_LOG_UNREADABLE"
    assert out["exhaustive"] is False
    assert out["operations"] == []
