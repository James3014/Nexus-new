from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_test", str(SCRIPT)).load_module()


def _write_log(path: Path, *, cwd: Path) -> tuple[str, str]:
    session_id = "session-test-1600"
    goal_id = "goal-test-1600"
    events = [
        {"type": "session", "sessionId": session_id, "cwd": str(cwd)},
        {
            "type": "tool_call",
            "callId": "call-create",
            "tool": "create_goal",
            "input": {"objective": "FIX_ISSUE_1600"},
        },
        {
            "type": "tool_result",
            "callId": "call-create",
            "status": "completed",
            "result": json.dumps({
                "goal": {
                    "id": goal_id,
                    "revision": 1,
                    "objective": "FIX_ISSUE_1600",
                    "phase": "active",
                    "roundsStarted": 0,
                    "maxGoalRounds": 256,
                },
                "activation": "armed",
            }),
        },
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in events),
        encoding="utf-8",
    )
    return session_id, goal_id


def _write_goal_projection(
    dsh_home: Path,
    *,
    session_id: str,
    goal_id: str,
    objective: str = "FIX_ISSUE_1600",
    revision: int = 3,
    phase: str = "active",
) -> Path:
    path = dsh_home / "storages" / "session_projcache" / "sessions" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "version": 1,
            "record": {
                "rows": {
                    "goal": {
                        "ver": 6,
                        "seq": 10,
                        "val": {
                            "current": {
                                "goal": {
                                    "id": goal_id,
                                    "revision": revision,
                                    "objective": objective,
                                    "phase": phase,
                                    "maxGoalRounds": 256,
                                },
                                "roundsStarted": 0,
                                "createdAt": 1,
                                "updatedAt": 2,
                            },
                            "seenGoalIds": [goal_id],
                            "failure": None,
                        },
                    }
                }
            },
        }),
        encoding="utf-8",
    )
    return path


def _binding(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    repo.mkdir()
    dsh_home = tmp_path / "dsh-home"
    dsh_home.mkdir()
    log = tmp_path / "turn.jsonl"
    session_id, goal_id = _write_log(log, cwd=repo)
    _write_goal_projection(
        dsh_home,
        session_id=session_id,
        goal_id=goal_id,
    )
    binding = guard.build_binding_from_log(
        log_path=log,
        repository="James3014/Nexus-new",
        issue_number=1600,
        repo_root=repo,
        dsh_home=dsh_home,
        created_at="2026-10-08T00:00:00Z",
    )
    assert binding["session_id"] == session_id
    assert binding["goal_id"] == goal_id
    return binding


def _doctor(*, state: str, disposition: str, gate: str) -> dict:
    return {
        "schema": guard.DOCTOR_SCHEMA,
        "claim_ceiling": guard.DOCTOR_CLAIM_CEILING,
        "resume_disposition": disposition,
        "next_gate": {"code": gate},
        "source": {
            "status": "OBSERVED",
            "repository": "James3014/Nexus-new",
            "head": "a" * 40,
            "github_main": "b" * 40,
        },
        "task": {
            "status": "OBSERVED",
            "state": state,
            "issue_number": 1600,
            "updated_at": "2026-10-08T00:00:00Z",
            "url": "https://github.com/James3014/Nexus-new/issues/1600",
        },
    }


def _write_doctor(path: Path, payload: dict) -> None:
    path.write_text(
        f"#!/usr/bin/env python3\nimport json\nprint(json.dumps({payload!r}))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_dsh(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['FAKE_DSH_MARKER']).write_text("
        "json.dumps({'cwd': os.getcwd(), 'dsh_home': os.environ.get('DSH_HOME'), "
        "'preflight_receipt': os.environ.get('NEXUS_DSH_PREFLIGHT_RECEIPT'), "
        "'argv': sys.argv[1:]}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_bind_log_persists_integrity_bound_session_and_goal(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    state_root = tmp_path / "state"

    path = guard.store_binding(state_root, binding)
    loaded = guard.load_binding(state_root, binding["session_id"])

    assert loaded == binding
    assert path.is_file()
    assert binding["authority"] == "TRACKING_METADATA_ONLY"
    assert binding["binding_hash"].startswith("sha256:")


def test_same_session_cannot_be_rebound_to_different_issue(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    state_root = tmp_path / "state"
    guard.store_binding(state_root, binding)

    conflicting = dict(binding)
    conflicting["issue_number"] = 1601
    body = dict(conflicting)
    body.pop("binding_hash")
    conflicting["binding_hash"] = guard._binding_hash(body)

    with pytest.raises(guard.DshWorkflowError, match="different tracked work"):
        guard.store_binding(state_root, conflicting)


def test_closed_issue_blocks_resume_without_minting_completion_authority(
    tmp_path: Path,
) -> None:
    binding = _binding(tmp_path)

    receipt = guard.evaluate_doctor(
        binding,
        _doctor(state="closed", disposition="SAFE", gate="NO_PENDING_GATE"),
        generated_at="2026-10-08T00:01:00Z",
    )

    assert receipt["decision"] == "BLOCK_RESUME"
    assert receipt["reason_code"] == "TRACKED_ISSUE_TERMINAL"
    assert receipt["provider_invocation_allowed"] is False
    assert receipt["task_state"] == "closed"
    assert receipt["claim_ceiling"] == "PRE_RESUME_GUARD_NO_COMPLETION_AUTHORITY"


def test_reopened_issue_is_rechecked_and_can_resume(tmp_path: Path) -> None:
    binding = _binding(tmp_path)

    closed = guard.evaluate_doctor(
        binding,
        _doctor(state="closed", disposition="SAFE", gate="NO_PENDING_GATE"),
        generated_at="2026-10-08T00:01:00Z",
    )
    reopened = guard.evaluate_doctor(
        binding,
        _doctor(
            state="open",
            disposition="SAFE",
            gate="CONTINUE_BOUNDED_ISSUE_WORK",
        ),
        generated_at="2026-10-08T00:02:00Z",
    )

    assert closed["decision"] == "BLOCK_RESUME"
    assert reopened["decision"] == "ALLOW_RESUME"
    assert reopened["provider_invocation_allowed"] is True
    assert reopened["task_state"] == "open"


def test_unknown_issue_state_fails_closed(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    doctor = _doctor(
        state="open",
        disposition="SAFE",
        gate="CONTINUE_BOUNDED_ISSUE_WORK",
    )
    doctor["task"] = {"status": "UNKNOWN", "issue_number": 1600}

    receipt = guard.evaluate_doctor(
        binding,
        doctor,
        generated_at="2026-10-08T00:03:00Z",
    )

    assert receipt["decision"] == "BLOCK_RESUME"
    assert receipt["reason_code"] == "TRACKED_ISSUE_STATE_UNVERIFIED"
    assert receipt["provider_invocation_allowed"] is False


def test_resume_cli_does_not_spawn_dsh_for_closed_issue_then_allows_reopen(
    tmp_path: Path,
) -> None:
    binding = _binding(tmp_path)
    state_root = tmp_path / "state"
    guard.store_binding(state_root, binding)

    doctor_bin = tmp_path / "doctor"
    dsh_bin = tmp_path / "dsh"
    marker = tmp_path / "dsh-invoked.json"
    _write_fake_dsh(dsh_bin)

    _write_doctor(
        doctor_bin,
        _doctor(state="closed", disposition="SAFE", gate="NO_PENDING_GATE"),
    )
    env = os.environ.copy()
    env["FAKE_DSH_MARKER"] = str(marker)
    blocked = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "resume",
            "--session-id",
            binding["session_id"],
            "--state-root",
            str(state_root),
            "--doctor-bin",
            str(doctor_bin),
            "--dsh-bin",
            str(dsh_bin),
            "--json",
            "--task",
            "continue exact tracked work",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert blocked.returncode == guard.EXIT_BLOCKED
    assert not marker.exists()
    blocked_receipt = json.loads(blocked.stdout.strip().splitlines()[-1])
    assert blocked_receipt["reason_code"] == "TRACKED_ISSUE_TERMINAL"
    assert blocked_receipt["provider_invocation_allowed"] is False

    _write_doctor(
        doctor_bin,
        _doctor(
            state="open",
            disposition="SAFE",
            gate="CONTINUE_BOUNDED_ISSUE_WORK",
        ),
    )
    allowed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "resume",
            "--session-id",
            binding["session_id"],
            "--state-root",
            str(state_root),
            "--doctor-bin",
            str(doctor_bin),
            "--dsh-bin",
            str(dsh_bin),
            "--profile",
            "headless",
            "--patch",
            "/tmp/adapter.patch.yml",
            "--json",
            "--task",
            "continue exact tracked work",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert allowed.returncode == 0, allowed.stderr
    assert marker.is_file()
    invocation = json.loads(marker.read_text(encoding="utf-8"))
    assert invocation["cwd"] == binding["repo_root"]
    assert invocation["dsh_home"] == binding["dsh_home"]
    preflight_path = Path(invocation["preflight_receipt"])
    assert preflight_path.is_file()
    persisted_preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert persisted_preflight["decision"] == "ALLOW_RESUME"
    assert persisted_preflight["provider_invocation_allowed"] is True
    assert invocation["argv"] == [
        "--profile",
        "headless",
        "--patch",
        "/tmp/adapter.patch.yml",
        "--json",
        "--session-id",
        binding["session_id"],
        "continue exact tracked work",
    ]

    assert allowed.stdout == ""


def test_current_goal_identity_mismatch_blocks_before_doctor_call(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    projection = _write_goal_projection(
        Path(binding["dsh_home"]),
        session_id=binding["session_id"],
        goal_id="goal-successor",
    )
    assert projection.is_file()
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    receipt = guard.run_preflight(
        binding,
        doctor_bin="/unused/doctor",
        runner=runner,
        generated_at="2026-10-08T00:04:00Z",
    )

    assert receipt["decision"] == "BLOCK_RESUME"
    assert receipt["reason_code"] == "DSH_GOAL_IDENTITY_MISMATCH"
    assert receipt["provider_invocation_allowed"] is False
    assert calls == []


def test_complete_goal_blocks_before_doctor_call(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    _write_goal_projection(
        Path(binding["dsh_home"]),
        session_id=binding["session_id"],
        goal_id=binding["goal_id"],
        phase="complete",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    receipt = guard.run_preflight(
        binding,
        doctor_bin="/unused/doctor",
        runner=runner,
        generated_at="2026-10-08T00:05:00Z",
    )

    assert receipt["decision"] == "BLOCK_RESUME"
    assert receipt["reason_code"] == "DSH_GOAL_ALREADY_COMPLETE"
    assert receipt["provider_invocation_allowed"] is False
    assert calls == []


def test_log_cwd_must_match_bound_repo_root(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    expected = tmp_path / "expected"
    expected.mkdir()
    dsh_home = tmp_path / "dsh-home"
    dsh_home.mkdir()
    log = tmp_path / "turn.jsonl"
    _write_log(log, cwd=actual)

    with pytest.raises(guard.DshWorkflowError, match="does not match"):
        guard.build_binding_from_log(
            log_path=log,
            repository="James3014/Nexus-new",
            issue_number=1600,
            repo_root=expected,
            dsh_home=dsh_home,
        )


def test_legacy_dsh_log_parses_custom_session_and_durable_goal_change(
    tmp_path: Path,
) -> None:
    log = tmp_path / "legacy.log"
    event = {
        "type": "goal/change",
        "seq": 17,
        "data": {
            "kind": "goal/change",
            "version": 1,
            "operation": "create",
            "goal": {
                "id": "goal-92295c62-ce51-4f66-9657-d3a84eccb52e",
                "revision": 1,
                "objective": "IMPLEMENT_RIE_ISSUE_57_GUARD_SEMANTIC_DELTA",
                "phase": "active",
                "maxGoalRounds": 12,
            },
            "roundsStarted": 0,
        },
    }
    log.write_text(
        f"DSH_SESSION_ID=rie57-dsh-agy-20261008-v2\nDSH_EVENT={json.dumps(event)}\n",
        encoding="utf-8",
    )

    observed = guard._parse_created_goal_log(log)

    assert observed == {
        "session_id": "rie57-dsh-agy-20261008-v2",
        "observed_cwd": None,
        "goal": {
            "id": "goal-92295c62-ce51-4f66-9657-d3a84eccb52e",
            "revision": 1,
            "objective": "IMPLEMENT_RIE_ISSUE_57_GUARD_SEMANTIC_DELTA",
        },
    }


def _run_cli(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def _assert_receipt_hash_verifies(path: Path) -> dict:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    body = dict(receipt)
    claimed = body.pop("receipt_hash")
    assert claimed == guard._sha256_bytes(guard._canonical_json(body).encode("utf-8"))
    return receipt


def test_receipts_record_check_and_resume_invocation_under_hash(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    state_root = tmp_path / "state"
    guard.store_binding(state_root, binding)
    doctor_bin = tmp_path / "doctor"
    dsh_bin = tmp_path / "dsh"
    marker = tmp_path / "dsh-invoked.json"
    _write_fake_dsh(dsh_bin)
    _write_doctor(
        doctor_bin,
        _doctor(state="closed", disposition="SAFE", gate="NO_PENDING_GATE"),
    )
    env = os.environ.copy()
    env["FAKE_DSH_MARKER"] = str(marker)
    common = [
        "--session-id",
        binding["session_id"],
        "--state-root",
        str(state_root),
        "--doctor-bin",
        str(doctor_bin),
    ]

    checked = _run_cli("check", *common, env=env)
    assert checked.returncode == guard.EXIT_BLOCKED
    assert json.loads(checked.stdout.strip().splitlines()[-1])["invocation"] == "check"
    latest = state_root / "preflights"
    latest_path = next(latest.glob("*/latest.json"))
    assert _assert_receipt_hash_verifies(latest_path)["invocation"] == "check"

    resumed = _run_cli(
        "resume",
        *common,
        "--dsh-bin",
        str(dsh_bin),
        "--task",
        "continue exact tracked work",
        env=env,
    )
    assert resumed.returncode == guard.EXIT_BLOCKED
    assert not marker.exists()
    assert json.loads(resumed.stdout.strip().splitlines()[-1])["invocation"] == "resume"
    persisted = _assert_receipt_hash_verifies(latest_path)
    assert persisted["invocation"] == "resume"
    assert persisted["decision"] == "BLOCK_RESUME"


def test_generic_guard_error_exits_blocked_without_spawning_dsh(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    state_root = tmp_path / "state"
    guard.store_binding(state_root, binding)
    # A regular file where the receipt directory belongs makes persistence raise OSError.
    (state_root / "preflights").write_text("not a directory", encoding="utf-8")
    doctor_bin = tmp_path / "doctor"
    dsh_bin = tmp_path / "dsh"
    marker = tmp_path / "dsh-invoked.json"
    _write_fake_dsh(dsh_bin)
    _write_doctor(
        doctor_bin,
        _doctor(state="open", disposition="SAFE", gate="CONTINUE_BOUNDED_ISSUE_WORK"),
    )
    env = os.environ.copy()
    env["FAKE_DSH_MARKER"] = str(marker)

    result = _run_cli(
        "resume",
        "--session-id",
        binding["session_id"],
        "--state-root",
        str(state_root),
        "--doctor-bin",
        str(doctor_bin),
        "--dsh-bin",
        str(dsh_bin),
        "--task",
        "continue exact tracked work",
        env=env,
    )

    assert result.returncode == guard.EXIT_BLOCKED
    assert not marker.exists()
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["decision"] == "BLOCK_RESUME"
    assert payload["reason_code"] == "DSH_WORKFLOW_GUARD_ERROR"
    assert payload["invocation"] == "resume"
    assert payload["provider_invocation_allowed"] is False


def _write_failing_fake_dsh(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "marker = Path(os.environ['FAKE_DSH_MARKER'])\n"
        "marker.write_text(marker.read_text() + 'x' if marker.exists() else 'x')\n"
        "edit = os.environ.get('FAKE_DSH_EDIT')\n"
        "if edit:\n"
        "    Path(edit).write_text('broken = undefined_name\\n')\n"
        "    Path(edit).with_name('scratch.py').write_text('x = 1\\n')\n"
        "sys.exit(int(os.environ.get('FAKE_DSH_EXIT', '0')))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _quarantine_setup(tmp_path: Path) -> dict:
    binding = _binding(tmp_path)
    repo = Path(binding["repo_root"])
    for cmd in (
        ["init", "-q"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    (repo / "mod.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    state_root = tmp_path / "state"
    guard.store_binding(state_root, binding)
    doctor_bin = tmp_path / "doctor"
    _write_doctor(
        doctor_bin,
        _doctor(state="open", disposition="SAFE", gate="CONTINUE_BOUNDED_ISSUE_WORK"),
    )
    dsh_bin = tmp_path / "dsh"
    _write_failing_fake_dsh(dsh_bin)
    return {
        "binding": binding,
        "repo": repo,
        "state_root": state_root,
        "doctor": doctor_bin,
        "dsh": dsh_bin,
        "marker": tmp_path / "dsh-count",
    }


def _resume(ctx: dict, *, exit_code: int, edit: bool) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["FAKE_DSH_MARKER"] = str(ctx["marker"])
    env["FAKE_DSH_EXIT"] = str(exit_code)
    if edit:
        env["FAKE_DSH_EDIT"] = str(ctx["repo"] / "mod.py")
    else:
        env.pop("FAKE_DSH_EDIT", None)
    return _run_cli(
        "resume",
        "--session-id",
        ctx["binding"]["session_id"],
        "--state-root",
        str(ctx["state_root"]),
        "--doctor-bin",
        str(ctx["doctor"]),
        "--dsh-bin",
        str(ctx["dsh"]),
        "--task",
        "continue",
        env=env,
    )


def _turn_state(ctx: dict) -> dict:
    path = ctx["state_root"] / "turn-state" / f"{ctx['binding']['session_id']}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_failed_dirty_turn_is_quarantined_blocks_next_resume_until_ack(tmp_path: Path) -> None:
    ctx = _quarantine_setup(tmp_path)
    binding_file = guard._binding_path(ctx["state_root"], ctx["binding"]["session_id"])
    binding_before = binding_file.read_bytes()

    failed = _resume(ctx, exit_code=1, edit=True)
    assert failed.returncode == 1  # DSH's own exit code is preserved
    assert ctx["marker"].read_text() == "x"
    state = _turn_state(ctx)
    assert state["state"] == "TURN_FAILED_DIRTY"
    assert binding_file.read_bytes() == binding_before
    # Never reverts: the broken edit and scratch file are still on disk.
    assert (ctx["repo"] / "mod.py").read_text() == "broken = undefined_name\n"
    assert (ctx["repo"] / "scratch.py").is_file()

    quarantine = _assert_receipt_hash_verifies(Path(state["quarantine_receipt"]))
    assert quarantine["schema"] == "nexus.dsh_turn_quarantine.v1"
    assert quarantine["state"] == "TURN_FAILED_DIRTY"
    assert quarantine["dsh_exit_code"] == 1
    assert quarantine["new_untracked_paths"] == ["scratch.py"]
    assert quarantine["automatic_revert"] is False
    patch = Path(quarantine["turn_patch"]["path"])
    assert "undefined_name" in patch.read_text(encoding="utf-8")
    assert quarantine["turn_patch"]["sha256"] == guard._sha256_file(patch)
    assert (
        quarantine["pre_turn"]["worktree_diff_sha256"]
        != (quarantine["post_turn"]["worktree_diff_sha256"])
    )
    assert "quarantine" in Path(state["quarantine_receipt"]).parts

    for command in ("check", "resume"):
        argv = [
            command,
            "--session-id",
            ctx["binding"]["session_id"],
            "--state-root",
            str(ctx["state_root"]),
            "--doctor-bin",
            str(ctx["doctor"]),
        ]
        if command == "resume":
            argv += ["--dsh-bin", str(ctx["dsh"]), "--task", "continue"]
        env = os.environ.copy()
        env["FAKE_DSH_MARKER"] = str(ctx["marker"])
        blocked = _run_cli(*argv, env=env)
        assert blocked.returncode == guard.EXIT_BLOCKED
        receipt = json.loads(blocked.stdout.strip().splitlines()[-1])
        assert receipt["decision"] == "BLOCK_RESUME"
        assert receipt["reason_code"] == "PREVIOUS_TURN_FAILED_DIRTY"
        assert receipt["provider_invocation_allowed"] is False
    assert ctx["marker"].read_text() == "x"  # provider not invoked again

    acked = _run_cli(
        "ack-turn-failure",
        "--session-id",
        ctx["binding"]["session_id"],
        "--state-root",
        str(ctx["state_root"]),
        "--reason",
        "reviewed quarantine patch",
    )
    assert acked.returncode == 0, acked.stderr
    ack = _assert_receipt_hash_verifies(Path(json.loads(acked.stdout)["receipt_path"]))
    assert ack["schema"] == "nexus.dsh_turn_failure_ack.v1"
    assert ack["reason"] == "reviewed quarantine patch"
    assert ack["acknowledged_by"]
    assert ack["generated_at"]
    assert ack["acknowledged_state"] == "TURN_FAILED_DIRTY"
    assert ack["current_worktree"]["worktree_diff_sha256"].startswith("sha256:")
    assert _turn_state(ctx)["state"] == "TURN_FAILURE_ACKNOWLEDGED"

    allowed = _resume(ctx, exit_code=0, edit=False)
    assert allowed.returncode == 0, allowed.stderr
    assert ctx["marker"].read_text() == "xx"
    assert _turn_state(ctx)["state"] == "TURN_OK"


def test_failed_clean_turn_does_not_block_and_is_reported(tmp_path: Path) -> None:
    ctx = _quarantine_setup(tmp_path)
    failed = _resume(ctx, exit_code=1, edit=False)
    assert failed.returncode == 1
    state = _turn_state(ctx)
    assert state["state"] == "TURN_FAILED_CLEAN"
    quarantine = _assert_receipt_hash_verifies(Path(state["quarantine_receipt"]))
    assert quarantine["turn_patch"] is None
    assert quarantine["new_untracked_paths"] == []

    env = os.environ.copy()
    env["FAKE_DSH_MARKER"] = str(ctx["marker"])
    checked = _run_cli(
        "check",
        "--session-id",
        ctx["binding"]["session_id"],
        "--state-root",
        str(ctx["state_root"]),
        "--doctor-bin",
        str(ctx["doctor"]),
        env=env,
    )
    assert checked.returncode == 0
    receipt = json.loads(checked.stdout)
    assert receipt["decision"] == "ALLOW_RESUME"
    assert receipt["previous_turn_state"] == "TURN_FAILED_CLEAN"

    again = _resume(ctx, exit_code=0, edit=False)
    assert again.returncode == 0
    assert ctx["marker"].read_text() == "xx"


def test_ack_without_pending_failure_or_reason_is_rejected(tmp_path: Path) -> None:
    ctx = _quarantine_setup(tmp_path)
    base = [
        "ack-turn-failure",
        "--session-id",
        ctx["binding"]["session_id"],
        "--state-root",
        str(ctx["state_root"]),
    ]
    nothing = _run_cli(*base, "--reason", "why")
    assert nothing.returncode == guard.EXIT_BLOCKED
    assert json.loads(nothing.stdout)["reason_code"] == "NO_TURN_FAILURE_TO_ACK"

    _resume(ctx, exit_code=1, edit=True)
    blank = _run_cli(*base, "--reason", "  ")
    assert blank.returncode == guard.EXIT_BLOCKED
    assert json.loads(blank.stdout)["reason_code"] == "TURN_ACK_REASON_REQUIRED"
    assert _turn_state(ctx)["state"] == "TURN_FAILED_DIRTY"
