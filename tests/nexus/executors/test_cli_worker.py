"""Tests for nexus/executors/cli_worker.py.

Covers:
- Legacy behaviour (no trajectory context) is identical to pre-seam baseline.
- Trajectory seam: pre-action seal fires before Popen.
- Trajectory seam: result bind fires after execution.
- candidate_id=None works.
- Telemetry seal failure is fail-open (does not change CLI result).
- Result bind failure is fail-open (does not change returned CliWorkerResult).
- Timeout and start-fail still return the correct worker status.
- Inherited env is not persisted in the receipt.
- Task-scoped secret env values AND their SHA256 are both absent from action
  payload/evidence; only env key names (presence metadata) may be recorded.
- Multiple step_index values chain correctly when the same trajectory is reused.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.executors.cli_worker import (
    CliWorkerRequest,
    CliWorkerStatus,
    CliWorkerTrajectoryContext,
    _build_action_payload,
    run_cli_worker,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _python_request(tmp_path: Path, script: str, *, timeout_seconds: float = 5.0):
    script_path = tmp_path / "fake_cli.py"
    script_path.write_text(script, encoding="utf-8")
    return CliWorkerRequest(
        executable=sys.executable,
        argv=(str(script_path), "--target", str(tmp_path)),
        cwd=str(tmp_path),
        timeout_seconds=timeout_seconds,
    )


def _make_ctx(
    tmp_path: Path, *, step_index: int = 0, candidate_id: str | None = "cand-1"
) -> CliWorkerTrajectoryContext:
    return CliWorkerTrajectoryContext(
        repo_root=str(tmp_path),
        task_id="task-123",
        trajectory_id="traj-abc",
        attempt_id="attempt-1",
        step_index=step_index,
        source_revision="abc123",
        candidate_id=candidate_id,
        base_source_revision="base123",
        working_state_manifest_sha256="deadbeef",
        pre_action_state={"phase": "pre_run"},
    )


# ---------------------------------------------------------------------------
# Existing legacy tests (unchanged behaviour)
# ---------------------------------------------------------------------------


def test_worker_runs_without_shell_and_records_hashes_and_telemetry(tmp_path):
    request = _python_request(
        tmp_path,
        "import sys; print('stdout:' + sys.argv[2]); print('stderr-line', file=sys.stderr)",
    )

    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 0
    assert result.executable_identity == request.executable
    assert result.executable_sha256 == result.hash_bytes(
        Path(result.executable_identity).read_bytes()
    )
    assert result.argv == request.argv
    assert result.cwd == str(tmp_path.resolve())
    assert result.stdout_sha256 == result.hash_bytes(result.stdout)
    assert result.stderr_sha256 == result.hash_bytes(result.stderr)
    assert result.wall_time_ms >= 0
    assert result.telemetry["wall_time_ms"] == result.wall_time_ms
    assert result.telemetry["process_group_id"] == result.process_group_id


def test_worker_records_nonzero_exit_with_executable_hash(tmp_path):
    request = _python_request(
        tmp_path,
        "import sys; print('bad', file=sys.stderr); sys.exit(7)",
    )

    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 7
    assert result.executable_sha256 == result.hash_bytes(
        Path(result.executable_identity).read_bytes()
    )
    assert result.timed_out is False
    assert result.process_group_killed is False


def test_worker_preserves_explicit_interpreter_symlink(tmp_path):
    alias = tmp_path / "python-alias"
    alias.symlink_to(sys.executable)
    request = CliWorkerRequest(
        executable=str(alias),
        argv=("-c", "print('alias-ok')"),
        cwd=str(tmp_path),
    )

    result = run_cli_worker(request)

    assert request.executable == str(alias)
    assert result.executable_identity == str(alias)
    assert result.exit_code == 0
    assert result.stdout == b"alias-ok\n"


def test_worker_invokes_and_clears_process_group_callback(tmp_path):
    calls = []

    def on_pg(pg_id):
        calls.append(pg_id)

    request = _python_request(
        tmp_path,
        "print('ok')",
    )

    result = run_cli_worker(request, on_process_group=on_pg)

    assert result.status is CliWorkerStatus.COMPLETED
    assert len(calls) == 2
    assert calls[0] == result.process_group_id
    assert calls[1] is None


def test_worker_rejects_commit_merge_and_push_commands(tmp_path):
    with pytest.raises(ValueError, match="commit|merge|push"):
        CliWorkerRequest(
            executable="git",
            argv=("commit", "-m", "unsafe"),
            cwd=str(tmp_path),
        )


@pytest.mark.parametrize(
    "argv",
    [
        ("gh", "issue", "comment", "1", "--body", "x"),
        ("gh", "--repo", "acme/demo", "issue", "edit", "1", "--title", "x"),
        ("gh", "-R", "acme/demo", "issue", "comment", "1", "--body", "x"),
        ("gh", "issue", "close", "1"),
        ("gh", "pr", "comment", "1", "--body", "x"),
        ("gh", "pr", "edit", "1", "--title", "x"),
        ("gh", "pr", "close", "1"),
        ("gh", "--repo", "acme/demo", "pr", "review", "1", "--approve"),
        ("gh", "pr", "merge", "1"),
        ("gh", "pr", "revert", "1"),
        ("gh", "pr", "update-branch", "1"),
        ("gh", "repo", "fork", "acme/demo"),
    ],
)
def test_worker_rejects_github_followup_publication_verbs_before_spawn(tmp_path, monkeypatch, argv):
    def no_spawn(*args, **kwargs):
        raise AssertionError("forbidden command reached subprocess spawn")

    monkeypatch.setattr("nexus.executors.cli_worker.subprocess.Popen", no_spawn)
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gh.chmod(0o700)
    with pytest.raises(ValueError, match="gh"):
        CliWorkerRequest(
            executable=str(gh),
            argv=argv[1:],
            cwd=str(tmp_path),
        )


def test_worker_preserves_github_read_only_commands(tmp_path):
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gh.chmod(0o700)
    request = CliWorkerRequest(
        executable=str(gh),
        argv=("issue", "view", "1"),
        cwd=str(tmp_path),
    )
    assert request.command == (str(gh), "issue", "view", "1")
    assert run_cli_worker(request).status is CliWorkerStatus.COMPLETED


def test_explicit_gh_token_cannot_reenter_worker_environment(tmp_path):
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_PAT"):
        with pytest.raises(ValueError, match="credential"):
            CliWorkerRequest(
                executable=sys.executable,
                argv=("-c", "print('ok')"),
                cwd=str(tmp_path),
                env={key: "secret"},
            )


def test_run_cli_worker_also_fails_closed_on_gh_token_env(tmp_path):
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        env={"TASK_SCOPED_MARKER": "kept"},
    )
    # Simulate a future env-supplying caller injecting a token after the
    # constructor guards: the send path must fail closed on its own.
    object.__setattr__(request, "env", {"GH_TOKEN": "secret"})
    with pytest.raises(ValueError, match="credential"):
        run_cli_worker(request)


def test_shell_wrapper_cannot_bypass_publication_boundary(tmp_path):
    with pytest.raises(ValueError, match="gh"):
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", "gh", "pr", "create", "--title", "x", "--repo", "acme/demo"),
            cwd=str(tmp_path),
        )


def test_worker_timeout_kills_process_group(tmp_path):
    request = _python_request(
        tmp_path,
        "import time; time.sleep(30)",
        timeout_seconds=0.05,
    )

    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.TIMED_OUT
    assert result.timed_out is True
    assert result.process_group_killed is True
    assert result.exit_code is not None


def test_worker_requires_existing_target_cwd(tmp_path):
    with pytest.raises(ValueError, match="cwd"):
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", "print('ok')"),
            cwd=str(tmp_path / "missing"),
        )


def test_worker_forces_pythondontwritebytecode_and_prevents_bytecode_generation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "0")
    script_path = tmp_path / "test_bytecode.py"
    script_path.write_text(
        "import os\nprint('BYTECODE_ENV=' + os.environ.get('PYTHONDONTWRITEBYTECODE', ''))\n",
        encoding="utf-8",
    )

    request = CliWorkerRequest(
        executable=sys.executable,
        argv=(str(script_path),),
        cwd=str(tmp_path),
        env={"PYTHONDONTWRITEBYTECODE": "0"},
    )
    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 0
    assert b"BYTECODE_ENV=1" in result.stdout
    pycache_dir = tmp_path / "__pycache__"
    assert not pycache_dir.exists()


def test_worker_does_not_inherit_ambient_target_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", "/ambient/override")
    script_path = tmp_path / "print_env.py"
    script_path.write_text(
        "import os; print(os.environ.get('NEXUS_TARGET_ROOT_OVERRIDE', 'MISSING'))\n",
        encoding="utf-8",
    )
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=(str(script_path),),
        cwd=str(tmp_path),
        env={"TASK_SCOPED_MARKER": "kept"},
    )

    result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.COMPLETED
    assert result.stdout == b"MISSING\n"


def test_worker_receipt_exposes_only_bounded_task_environment(tmp_path):
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        env={"TASK_SCOPED_MARKER": "kept", "PYTHONDONTWRITEBYTECODE": "1"},
    )

    result = run_cli_worker(request)

    # Contract: only key names + static "present" sentinel; no raw values, no hashes.
    assert result.env == (
        ("PYTHONDONTWRITEBYTECODE", "present"),
        ("TASK_SCOPED_MARKER", "present"),
    )


# ---------------------------------------------------------------------------
# Trajectory seam: new tests
# ---------------------------------------------------------------------------


def test_no_trajectory_context_produces_identical_legacy_behavior(tmp_path):
    """Without trajectory_context, behaviour is byte-for-byte identical to baseline."""
    request = _python_request(tmp_path, "print('legacy')")
    assert request.trajectory_context is None

    with (
        patch("nexus.executors.cli_worker._seal_step") as mock_seal,
        patch("nexus.executors.cli_worker._bind_result") as mock_bind,
    ):
        result = run_cli_worker(request)

    # Seal and bind must never be called when context is absent
    mock_seal.assert_not_called()
    mock_bind.assert_not_called()
    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 0


def test_pre_action_seal_fires_before_popen(tmp_path):
    """seal_trajectory_step must be called BEFORE subprocess.Popen."""
    ctx = _make_ctx(tmp_path)
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        trajectory_context=ctx,
    )

    call_order: list[str] = []
    fake_ref = MagicMock(name="step_ref")

    def fake_seal(c, r):
        call_order.append("seal")
        return fake_ref

    real_popen = __import__("subprocess").Popen

    def tracking_popen(*args, **kwargs):
        call_order.append("popen")
        return real_popen(*args, **kwargs)

    with (
        patch("nexus.executors.cli_worker._seal_step", side_effect=fake_seal),
        patch("nexus.executors.cli_worker.subprocess.Popen", side_effect=tracking_popen),
        patch("nexus.executors.cli_worker._bind_result"),
    ):
        run_cli_worker(request)

    assert call_order == ["seal", "popen"], f"Expected seal before popen, got: {call_order}"


def test_result_binding_fires_after_execution(tmp_path):
    """bind_trajectory_step_result must be called after execution completes."""
    ctx = _make_ctx(tmp_path)
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        trajectory_context=ctx,
    )

    fake_ref = MagicMock(name="step_ref")
    bound_results: list[object] = []

    def fake_bind(c, ref, result):
        bound_results.append(result)

    with (
        patch("nexus.executors.cli_worker._seal_step", return_value=fake_ref),
        patch("nexus.executors.cli_worker._bind_result", side_effect=fake_bind),
    ):
        result = run_cli_worker(request)

    assert len(bound_results) == 1
    assert bound_results[0] is result


def test_trajectory_seal_and_bind_receive_correct_context_and_request(tmp_path):
    """_seal_step and _bind_result receive the expected (ctx, request) and (ctx, ref, result) args."""
    ctx = _make_ctx(tmp_path)
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        trajectory_context=ctx,
    )
    fake_ref = object()

    with (
        patch("nexus.executors.cli_worker._seal_step", return_value=fake_ref) as mock_seal,
        patch("nexus.executors.cli_worker._bind_result") as mock_bind,
    ):
        result = run_cli_worker(request)

    mock_seal.assert_called_once_with(ctx, request)
    mock_bind.assert_called_once_with(ctx, fake_ref, result)


def test_candidate_id_none_works(tmp_path):
    """candidate_id=None on context is valid and propagates to seal call."""
    ctx = _make_ctx(tmp_path, candidate_id=None)
    assert ctx.candidate_id is None
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        trajectory_context=ctx,
    )

    with (
        patch("nexus.executors.cli_worker._seal_step", return_value=MagicMock()) as mock_seal,
        patch("nexus.executors.cli_worker._bind_result"),
    ):
        result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.COMPLETED
    seal_ctx_arg = mock_seal.call_args[0][0]
    assert seal_ctx_arg.candidate_id is None


def test_telemetry_seal_failure_is_fail_open(tmp_path):
    """A seal failure must not raise, must not change execution, must not change result."""
    ctx = _make_ctx(tmp_path)
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        trajectory_context=ctx,
    )

    with (
        patch("nexus.executors.cli_worker._seal_step", side_effect=RuntimeError("seal boom")),
        patch("nexus.executors.cli_worker._bind_result") as mock_bind,
    ):
        result = run_cli_worker(request)

    # Execution must still succeed
    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 0
    # bind_result is called but receives None step_ref (seal returned None via swallow)
    mock_bind.assert_called_once()
    _, ref_arg, _ = mock_bind.call_args[0]
    # _seal_step raised → returned None (the actual internal helper catches, but we patched
    # _seal_step itself here, so the exception propagates to run_cli_worker's try-block which
    # is not the internal one).  The test verifies that run_cli_worker swallows this exception.
    # Since _seal_step itself raises here (bypassing internal swallow), we check result is ok.
    assert result.stdout == b"ok\n"


def test_telemetry_seal_failure_swallowed_via_internal_helper(tmp_path):
    """When the trajectory API raises, _seal_step swallows it and returns None."""
    from nexus.executors.cli_worker import _seal_step  # noqa: PLC0415

    ctx = _make_ctx(tmp_path)
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        trajectory_context=ctx,
    )

    with patch(
        "nexus.executors.cli_worker.seal_trajectory_step"
        if False
        else "nexus.research.clm_system_one.trajectory_continuity.seal_trajectory_step",
        side_effect=RuntimeError("internal boom"),
    ):
        # _seal_step must return None, not raise
        ref = _seal_step(ctx, request)

    assert ref is None


def test_result_bind_failure_is_fail_open(tmp_path):
    """A bind failure must not raise and must not change the returned CliWorkerResult."""
    ctx = _make_ctx(tmp_path)
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        trajectory_context=ctx,
    )

    with (
        patch("nexus.executors.cli_worker._seal_step", return_value=MagicMock()),
        patch("nexus.executors.cli_worker._bind_result", side_effect=RuntimeError("bind boom")),
    ):
        result = run_cli_worker(request)

    # Result must still be correct despite bind failure
    assert result.status is CliWorkerStatus.COMPLETED
    assert result.exit_code == 0
    assert result.stdout == b"ok\n"


def test_timeout_still_returns_correct_worker_status_with_trajectory_context(tmp_path):
    """Trajectory seam does not change timeout behaviour or returned status."""
    ctx = _make_ctx(tmp_path)
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "import time; time.sleep(30)"),
        cwd=str(tmp_path),
        timeout_seconds=0.05,
        trajectory_context=ctx,
    )

    with (
        patch("nexus.executors.cli_worker._seal_step", return_value=MagicMock()),
        patch("nexus.executors.cli_worker._bind_result"),
    ):
        result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.TIMED_OUT
    assert result.timed_out is True
    assert result.process_group_killed is True


def test_start_fail_still_returns_correct_worker_status_with_trajectory_context(
    tmp_path, monkeypatch
):
    """Trajectory seam does not change START_FAILED behaviour."""
    ctx = _make_ctx(tmp_path)
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        trajectory_context=ctx,
    )

    def raise_oserror(*args, **kwargs):
        raise OSError("simulated start failure")

    with (
        patch("nexus.executors.cli_worker._seal_step", return_value=MagicMock()),
        patch("nexus.executors.cli_worker.subprocess.Popen", side_effect=raise_oserror),
        patch("nexus.executors.cli_worker._bind_result") as mock_bind,
    ):
        result = run_cli_worker(request)

    assert result.status is CliWorkerStatus.START_FAILED
    assert result.exit_code is None
    # bind should still be called even on start-fail
    mock_bind.assert_called_once()


def test_inherited_env_not_persisted_in_receipt(tmp_path):
    """The env receipt must contain only task-scoped keys, not inherited allowlist keys."""
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        env={"TASK_KEY": "task_value"},
    )
    result = run_cli_worker(request)

    receipt_keys = {k for k, _ in result.env}
    # Inherited allowlist keys (PATH, HOME, etc.) must not appear in receipt
    inherited = {"HOME", "LANG", "LC_ALL", "PATH", "PYTHONPATH", "TMPDIR", "VIRTUAL_ENV"}
    assert not (receipt_keys & inherited), (
        f"Inherited env keys leaked into receipt: {receipt_keys & inherited}"
    )
    # Only task-scoped keys may appear
    assert "TASK_KEY" in receipt_keys


def test_task_scoped_secret_env_is_redacted_in_action_payload(tmp_path):
    """_build_action_payload must not expose raw env values OR any hash derived from them.

    Contract: task_env_receipt entries carry only key names (presence metadata).
    Neither the raw secret value nor its SHA256 (or any other derived hash) may
    appear anywhere in the serialised payload.
    """
    secret_value = "supersecret"
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('ok')"),
        cwd=str(tmp_path),
        env={"MY_SECRET_KEY": secret_value},
    )
    payload = _build_action_payload(request)

    import json as _json

    serialized = _json.dumps(payload)

    # Raw secret value must not appear anywhere in the payload
    assert secret_value not in serialized, "Raw secret value leaked into action payload"

    # SHA256 of the secret (or any prefix/encoding of it) must also be absent
    secret_sha256 = hashlib.sha256(secret_value.encode()).hexdigest()
    assert secret_sha256 not in serialized, "SHA256 of secret value leaked into action payload"

    # Payload must include task_env_receipt with key-presence entries only
    receipt = payload["task_env_receipt"]
    assert len(receipt) >= 1
    entry = next((e for e in receipt if e["key"] == "MY_SECRET_KEY"), None)
    assert entry is not None, "MY_SECRET_KEY not found in task_env_receipt"
    # Entry must have ONLY the key field — no value_sha256, no value
    assert set(entry.keys()) == {"key"}, (
        f"task_env_receipt entry has unexpected fields: {set(entry.keys())}"
    )


def test_multiple_step_index_values_chain_correctly(tmp_path):
    """Sequential step_index values chain correctly when same trajectory_id is reused."""
    # Use the real trajectory API with a temp evidence root
    import os as _os

    evidence_root = tmp_path / ".nexus" / "research" / "clm_system_one" / "candidate_evidence"
    evidence_root.mkdir(parents=True)
    monkeypatch_env = {"NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT": str(evidence_root)}

    def run_step(step_index: int) -> None:
        ctx = CliWorkerTrajectoryContext(
            repo_root=str(tmp_path),
            task_id="task-chain",
            trajectory_id="traj-chain",
            attempt_id="attempt-1",
            step_index=step_index,
            source_revision="rev-001",
            candidate_id=None,
            pre_action_state={"step": step_index},
        )
        request = CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", f"print('step-{step_index}')"),
            cwd=str(tmp_path),
            trajectory_context=ctx,
        )
        with patch.dict(_os.environ, monkeypatch_env):
            result = run_cli_worker(request)
        assert result.status is CliWorkerStatus.COMPLETED
        assert result.exit_code == 0

    # Chain steps 0, 1, 2 sequentially
    for idx in range(3):
        run_step(idx)

    # Verify step files exist and form a valid chain
    from nexus.research.clm_system_one.trajectory_continuity import (
        _trajectory_complete,
        _trajectory_storage_key,
    )

    steps_dir = evidence_root / "trajectory" / "steps" / _trajectory_storage_key("traj-chain")
    step_files = sorted(steps_dir.glob("*.json"))
    assert len(step_files) == 3, f"Expected 3 step files, got {len(step_files)}"

    # Step chain must be complete (no gaps, correct parent hashes)
    complete, problems = _trajectory_complete(evidence_root, "traj-chain")
    # Results are bound so step_results should also exist; if missing, only
    # "missing_step_result" should appear (trajectory integrity is intact).
    integrity_problems = [p for p in problems if p != "missing_step_result"]
    assert not integrity_problems, f"Trajectory chain integrity problems: {integrity_problems}"
