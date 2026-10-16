"""Characterization tests for the gateway's assisted-provider cluster (Issue #2443).

Big-file split G4-pre: pins the behaviour of the methods that G4 (probe evidence /
decode), G5 (assist refresh / response) and G6 (assist submit / wait / cancel / retry)
will move out of ``UnifiedMCPGateway`` into mixins.

* Job lifecycle tests go through the public MCP entry point ``handle`` ->
  ``_call_tool`` (``nexus_assist_submit``, ``nexus_assist_result``,
  ``nexus_assist_cancel``, ``nexus_task_wait``, ``nexus_task_retry``,
  ``nexus_task_status``).  The provider is a real fake-``cline`` shell script started
  by the gateway's own ``subprocess.Popen``, so cancellation kills a real process group.
* Probe-evidence and decode helpers have no public entry point that can be driven
  without a live provider, so they are called as methods on the instance or class;
  that access survives a mixin move.

Every test lists the future-moved methods it exercises in ``@exercises(...)``;
``test_exercised_methods_exist`` keeps those names honest.  ``_assist_command``,
``_run_agy_plan`` and ``_compile_agy_command`` are only used, never altered.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway

EXERCISED: dict[str, tuple[str, ...]] = {}
EMPTY_DELTA = {"created": [], "removed": [], "changed": []}
VALID_PATCH = (
    "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-a\n+b\n"
)
DEAD_PID = 99_999_999  # above any pid_max: os.kill(pid, 0) always fails


def exercises(*names: str) -> Callable:
    def mark(function: Callable) -> Callable:
        EXERCISED[function.__name__] = names
        return function

    return mark


class _Service(SelfHostedTaskService):
    def __init__(self, state_dir: Path) -> None:  # no task-service state needed
        self.state_dir = state_dir

    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self, *, include_details=False):
        return {"actionable_count": 0, "details_included": include_details, "tasks": []}


FAKE_CLINE = """#!/bin/sh
if [ -n "$FAKE_CLINE_IGNORE_TERM" ]; then trap '' TERM; fi
if [ -n "$FAKE_CLINE_ARGS" ]; then printf '%s\\n' "$@" > "$FAKE_CLINE_ARGS"; fi
if [ -n "$FAKE_CLINE_TOUCH" ]; then : > "$FAKE_CLINE_TOUCH"; fi
if [ -n "$FAKE_CLINE_STDOUT" ]; then cat "$FAKE_CLINE_STDOUT"; fi
if [ -n "$FAKE_CLINE_STDERR" ]; then cat "$FAKE_CLINE_STDERR" >&2; fi
if [ -n "$FAKE_CLINE_SLEEP" ]; then sleep "$FAKE_CLINE_SLEEP"; fi
exit "${FAKE_CLINE_EXIT:-0}"
"""


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    for name in (
        "FAKE_CLINE_ARGS",
        "FAKE_CLINE_TOUCH",
        "FAKE_CLINE_STDOUT",
        "FAKE_CLINE_STDERR",
        "FAKE_CLINE_SLEEP",
        "FAKE_CLINE_EXIT",
        "FAKE_CLINE_IGNORE_TERM",
    ):
        monkeypatch.delenv(name, raising=False)
    cline = tmp_path / "bin" / "cline"
    cline.parent.mkdir()
    cline.write_text(FAKE_CLINE, encoding="utf-8")
    cline.chmod(0o755)
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(cline))
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "a" * 40)
    monkeypatch.setattr(gateway_module, "CONTROLLER_BINDING_PROBLEM", None)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", False)
    state = tmp_path / "state"
    gateway = UnifiedMCPGateway(service=_Service(state))

    value = SimpleNamespace()
    value.gateway = gateway
    value.cline = cline
    value.state = state
    value.tmp = tmp_path
    value.monkeypatch = monkeypatch

    def provider_output(
        stdout: str = "", *, stderr: str = "", exit_code: int = 0, sleep: str = "", touch: str = ""
    ) -> None:
        out = tmp_path / f"out-{len(stdout)}-{exit_code}.txt"
        out.write_text(stdout, encoding="utf-8")
        monkeypatch.setenv("FAKE_CLINE_STDOUT", str(out))
        if stderr:
            err = tmp_path / "err.txt"
            err.write_text(stderr, encoding="utf-8")
            monkeypatch.setenv("FAKE_CLINE_STDERR", str(err))
        monkeypatch.setenv("FAKE_CLINE_EXIT", str(exit_code))
        if sleep:
            monkeypatch.setenv("FAKE_CLINE_SLEEP", sleep)
        if touch:
            monkeypatch.setenv("FAKE_CLINE_TOUCH", touch)

    value.provider_output = provider_output
    yield value
    for process in list(gateway._assist_processes.values()):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    for job_path in (state / "assisted_provider_jobs").glob("*.json"):
        try:
            stored = json.loads(job_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        workspace = str(stored.get("workspace_root") or "") if isinstance(stored, dict) else ""
        if workspace.startswith(("/tmp/nexus-assist-", "/tmp/nexus-retry-")):
            shutil.rmtree(workspace, ignore_errors=True)


def _call(gateway: UnifiedMCPGateway, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response is not None
    return response["result"]


def _ok(gateway: UnifiedMCPGateway, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = _call(gateway, name, arguments)
    assert not result.get("isError"), result
    return result["structuredContent"]


def _error(gateway: UnifiedMCPGateway, name: str, arguments: dict[str, Any]) -> str:
    result = _call(gateway, name, arguments)
    assert result.get("isError") is True, result
    return str(result["structuredContent"].get("error") or result["structuredContent"].get("code"))


def _submit(env, task_id: str, **extra: Any) -> dict[str, Any]:
    arguments = {
        "task_id": task_id,
        "what": "Suggest a README patch",
        "why": "characterization",
        "allowed_files": ["README.md"],
        **extra,
    }
    return _ok(env.gateway, "nexus_assist_submit", arguments)


def _wait(env, task_id: str, timeout: float = 15) -> dict[str, Any]:
    return _ok(
        env.gateway,
        "nexus_task_wait",
        {"task_id": task_id, "timeout_seconds": timeout, "poll_interval_seconds": 0.05},
    )


def _run_result(payload: Any) -> str:
    return json.dumps({"type": "run_result", "text": json.dumps(payload)}) + "\n"


def _sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- G6 submit -> G5 refresh/response through the public tools -------------------


@exercises(
    "_assist_submit",
    "_assist_root",
    "_assist_path",
    "_assist_write",
    "_assist_read",
    "_snapshot_workspace",
    "_assist_response",
    "_assist_action",
)
def test_submit_persists_job_and_starts_bounded_cline_command(env) -> None:
    args_file = env.tmp / "args.txt"
    env.monkeypatch.setenv("FAKE_CLINE_ARGS", str(args_file))
    env.provider_output(_run_result({"patch": VALID_PATCH}), sleep="2")
    submitted = _submit(env, "assist-submit-1", model="glm-5.2", apply=True)
    assert submitted["operation"] == "submit"
    assert submitted["status"] == "RUNNING"
    assert (submitted["execution_lane"], submitted["candidate_only"]) == (
        "ASSISTED_CANONICAL",
        True,
    )
    assert (submitted["apply_requested"], submitted["apply_ignored"]) == (False, True)
    assert (submitted["provider"], submitted["model"]) == ("cline", "cline-pass/glm-5.2")
    assert (submitted["next_action"], submitted["pending"] if "pending" in submitted else None) == (
        "nexus_assist_result",
        None,
    )
    assert submitted["attention_required"] is False
    assert submitted["pid"] == submitted["pgid"] and submitted["pid"] > 0
    job = json.loads(
        (env.state / "assisted_provider_jobs" / "assist-submit-1.json").read_text(encoding="utf-8")
    )
    command = job["command"]
    assert command[0] == str(env.cline)
    assert command[1:-1] == [
        "--json",
        "--plan",
        "--auto-approve",
        "false",
        "--thinking",
        "none",
        "--timeout",
        str(gateway_module.CLINE_RUN_TIMEOUT_SECONDS),
        "--model",
        "cline-pass/glm-5.2",
    ]
    assert (
        job["command_hash"]
        == hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest()
        == submitted["command_hash"]
    )
    assert job["bound_action_request"] == {
        "task_id": "assist-submit-1",
        "what": "Suggest a README patch",
        "why": "characterization",
        "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"],
        "apply": False,
    }
    assert job["action"]["mutation"] is False and job["action"]["permission_profile"] == "VERIFY"
    assert job["output_schema"] == {
        "type": "object",
        "required": ["patch"],
        "properties": {"patch": {"type": "string", "minLength": 1}},
    }
    assert Path(job["workspace_root"]).is_dir() and job["workspace_mode"] == "isolated"
    assert job["filesystem_before"] == {} and job["filesystem_delta"] == EMPTY_DELTA
    assert not list((env.state / "assisted_provider_jobs").glob(".*.tmp"))
    _wait(env, "assist-submit-1")
    assert args_file.read_text(encoding="utf-8") == "\n".join(command[1:]) + "\n"


@exercises(
    "_assist_submit",
    "_assist_refresh",
    "_decode_assist_payload",
    "_validate_output_schema",
    "_assist_patch_is_substantive",
    "_assist_record_stream_artifacts",
    "_snapshot_workspace",
    "_assist_wait",
    "_assist_response",
    "_assist_action",
)
def test_completed_job_records_result_streams_and_cleans_workspace(env) -> None:
    env.provider_output(_run_result({"patch": VALID_PATCH}), stderr="provider note\n")
    submitted = _submit(env, "assist-done-1")
    waited = _wait(env, "assist-done-1")
    assert waited["operation"] == "wait"
    assert waited["status"] == "COMPLETED"
    assert waited["result"] == {"patch": VALID_PATCH}
    assert (waited["exit_code"], waited["blocker"], waited["schema_error"]) == (0, None, "")
    assert (waited["retry_required"], waited["attention_required"], waited["next_action"]) == (
        False,
        False,
        "none",
    )
    assert waited["stream_flush_status"] == "FLUSHED"
    assert waited["stdout_sha256"] == _sha256_file(waited["artifacts"]["stdout"])
    assert waited["stderr_sha256"] == _sha256_file(waited["artifacts"]["stderr"])
    assert waited["stderr_bytes"] == len("provider note\n")
    assert waited["provider_error"] == "" and waited["provider_error_sha256"] is None
    assert waited["process_cleanup"] is True and waited["filesystem_delta"] == EMPTY_DELTA
    assert not Path(submitted["workspace_root"]).exists()
    assert waited["model_response_verified"] is False
    result = _ok(env.gateway, "nexus_assist_result", {"task_id": "assist-done-1"})
    assert result["operation"] == "result" and result["status"] == "COMPLETED"
    status = _ok(env.gateway, "nexus_task_status", {"task_id": "assist-done-1"})
    assert status["operation"] == "status" and status["result"] == {"patch": VALID_PATCH}


@exercises("_assist_refresh", "_snapshot_workspace")
def test_provider_writes_in_workspace_are_reported_as_filesystem_delta(env) -> None:
    env.provider_output(_run_result({"patch": VALID_PATCH}), touch="created-by-provider.txt")
    _submit(env, "assist-delta-1")
    waited = _wait(env, "assist-delta-1")
    assert waited["filesystem_delta"] == {
        "created": ["created-by-provider.txt"],
        "removed": [],
        "changed": [],
    }
    assert waited["status"] == "COMPLETED" and waited["process_cleanup"] is True


@exercises("_assist_submit", "_assist_read", "_assist_refresh", "_assist_response")
def test_resubmit_of_known_task_returns_existing_job_without_relaunch(env) -> None:
    args_file = env.tmp / "args.txt"
    env.monkeypatch.setenv("FAKE_CLINE_ARGS", str(args_file))
    env.provider_output(_run_result({"patch": VALID_PATCH}))
    first = _submit(env, "assist-idem-1")
    _wait(env, "assist-idem-1")
    args_file.unlink()
    again = _submit(env, "assist-idem-1", what="something else")
    assert again["operation"] == "submit"
    assert again["job_id"] == first["job_id"] and again["status"] == "COMPLETED"
    assert not args_file.exists()


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"provider": "codex"}, "ASSIST_ASYNC_PROVIDER_UNSUPPORTED"),
        ({"allowed_files": []}, "allowed_files must contain 1-4 bounded paths"),
        (
            {"allowed_files": ["a", "b", "c", "d", "e"]},
            "allowed_files must contain 1-4 bounded paths",
        ),
        ({"allowed_files": ["../escape.md"]}, "allowed_files must be a bounded relative path"),
        ({"allowed_files": [".git/config"]}, "allowed_files cannot access .git"),
    ],
)
@exercises("_assist_submit")
def test_submit_rejects_invalid_requests_before_launch(env, extra: dict, message: str) -> None:
    arguments = {
        "task_id": "assist-invalid-1",
        "what": "x",
        "why": "y",
        "allowed_files": ["README.md"],
        **extra,
    }
    assert _error(env.gateway, "nexus_assist_submit", arguments) == message
    assert env.gateway._assist_read("assist-invalid-1") is None


@exercises("_assist_submit")
def test_submit_requires_an_existing_provider_executable(env) -> None:
    env.monkeypatch.setenv("NEXUS_CLINE_BIN", str(env.tmp / "missing-cline"))
    assert (
        _error(
            env.gateway,
            "nexus_assist_submit",
            {"task_id": "assist-noexe-1", "what": "x", "why": "y", "allowed_files": ["README.md"]},
        )
        == "ASSIST_PROVIDER_UNAVAILABLE"
    )


@exercises("_assist_submit", "_assist_write", "_assist_response")
def test_submit_records_launch_failure_and_removes_workspace(env) -> None:
    def refuse(*args, **kwargs):
        raise OSError("exec format error")

    env.monkeypatch.setattr(gateway_module.subprocess, "Popen", refuse)
    submitted = _submit(env, "assist-nolaunch-1")
    assert (submitted["status"], submitted["blocker"], submitted["provider_error"]) == (
        "FAILED",
        "ASSIST_PROVIDER_FAILED",
        "provider process could not start",
    )
    assert not Path(submitted["workspace_root"]).exists()
    assert submitted["next_action"] == "nexus_task_retry" and submitted["retry_required"] is True


@exercises("_assist_refresh", "_assist_response", "_assist_action")
def test_nonzero_provider_exit_fails_with_redacted_error_digest(env) -> None:
    env.provider_output("", stderr="secret token in stderr\n", exit_code=3)
    _submit(env, "assist-exit-1")
    waited = _wait(env, "assist-exit-1")
    assert (waited["status"], waited["exit_code"], waited["blocker"]) == (
        "FAILED",
        3,
        "ASSIST_PROVIDER_FAILED",
    )
    assert waited["provider_error"] == "provider process failed"
    assert (
        waited["provider_error_sha256"] == hashlib.sha256(b"secret token in stderr\n").hexdigest()
    )
    assert "secret token" not in json.dumps(waited)
    assert waited["result"] is None
    assert (waited["next_action"], waited["retry_required"]) == ("nexus_task_retry", True)


@pytest.mark.parametrize(
    ("stdout", "blocker", "schema_error"),
    [
        ("not json at all\n", "ASSIST_PROVIDER_MALFORMED_OUTPUT", "output_schema_type:$:object"),
        (
            _run_result({"patch": "I cannot help with that."}),
            "ASSIST_PROVIDER_DEGENERATE_OUTPUT",
            "degenerate_patch",
        ),
    ],
)
@exercises(
    "_assist_refresh",
    "_decode_assist_payload",
    "_validate_output_schema",
    "_assist_patch_is_substantive",
)
def test_unusable_provider_output_fails_closed(
    env, stdout: str, blocker: str, schema_error: str
) -> None:
    env.provider_output(stdout)
    _submit(env, "assist-bad-1")
    waited = _wait(env, "assist-bad-1")
    assert (waited["status"], waited["blocker"], waited["schema_error"]) == (
        "FAILED",
        blocker,
        schema_error,
    )
    assert waited["result"] is None
    assert waited["retry_required"] is True


@exercises("_assist_wait", "_assist_refresh", "_assist_response")
def test_wait_timeout_reports_running_without_cancelling(env) -> None:
    env.provider_output("", sleep="30")
    _submit(env, "assist-slow-1")
    waited = _wait(env, "assist-slow-1", timeout=0)
    assert waited["status"] == "RUNNING" and waited["operation"] == "wait"
    assert env.gateway._assist_processes["assist-slow-1"].poll() is None
    job = env.gateway._assist_read("assist-slow-1")
    assert job["last_polled_at"]


@exercises(
    "_assist_cancel",
    "_assist_refresh",
    "_assist_record_stream_artifacts",
    "_cleanup_assist_workspace",
    "_snapshot_workspace",
    "_assist_response",
    "_assist_action",
)
def test_cancel_kills_running_provider_process_group_and_cleans_up(env) -> None:
    env.provider_output("partial output\n", stderr="partial warning\n", sleep="30")
    submitted = _submit(env, "assist-cancel-1")
    process = env.gateway._assist_processes["assist-cancel-1"]
    job = env.gateway._assist_read("assist-cancel-1")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not (
        Path(job["stdout_artifact"]).stat().st_size and Path(job["stderr_artifact"]).stat().st_size
    ):
        time.sleep(0.02)
    cancelled = _ok(env.gateway, "nexus_assist_cancel", {"task_id": "assist-cancel-1"})
    assert cancelled["operation"] == "cancel"
    assert (cancelled["status"], cancelled["blocker"], cancelled["process_killed"]) == (
        "CANCELLED",
        "ASSIST_CANCELLED",
        True,
    )
    assert process.poll() is not None
    assert cancelled["exit_code"] == process.returncode
    assert cancelled["stream_flush_status"] == "FLUSHED"
    assert cancelled["stdout_bytes"] == len("partial output\n") and cancelled[
        "stderr_bytes"
    ] == len("partial warning\n")
    assert cancelled["process_cleanup"] is True and not Path(submitted["workspace_root"]).exists()
    assert "assist-cancel-1" not in env.gateway._assist_processes
    assert (cancelled["next_action"], cancelled["attention_required"]) == ("nexus_task_retry", True)
    again = _ok(env.gateway, "nexus_task_cancel", {"task_id": "assist-cancel-1"})
    assert again["status"] == "CANCELLED" and again["operation"] == "cancel"


def _wait_for_streams(env, task_id: str) -> None:
    job = env.gateway._assist_read(task_id)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not Path(job["stdout_artifact"]).stat().st_size:
        time.sleep(0.02)


@exercises("_assist_cancel", "_assist_record_stream_artifacts", "_cleanup_assist_workspace")
def test_cancel_escalates_to_sigkill_when_provider_ignores_sigterm(env) -> None:
    env.monkeypatch.setenv("FAKE_CLINE_IGNORE_TERM", "1")
    env.provider_output("started\n", sleep="30")
    _submit(env, "assist-stubborn-1")
    process = env.gateway._assist_processes["assist-stubborn-1"]
    _wait_for_streams(env, "assist-stubborn-1")
    started = time.monotonic()
    cancelled = _ok(env.gateway, "nexus_assist_cancel", {"task_id": "assist-stubborn-1"})
    assert time.monotonic() - started >= 2.0  # SIGTERM grace period elapsed first
    assert (cancelled["status"], cancelled["blocker"], cancelled["process_killed"]) == (
        "CANCELLED",
        "ASSIST_CANCELLED",
        True,
    )
    assert process.returncode == -9 and cancelled["exit_code"] == -9


@exercises("_assist_retry", "_assist_write", "_assist_response")
def test_retry_records_relaunch_failure_and_removes_workspace(env) -> None:
    env.provider_output("", exit_code=1)
    _submit(env, "assist-retry-nolaunch-1")
    _wait(env, "assist-retry-nolaunch-1")

    def refuse(*args, **kwargs):
        raise OSError("exec format error")

    env.monkeypatch.setattr(gateway_module.subprocess, "Popen", refuse)
    retried = _ok(env.gateway, "nexus_task_retry", {"task_id": "assist-retry-nolaunch-1"})
    assert (retried["operation"], retried["status"], retried["blocker"]) == (
        "retry",
        "FAILED",
        "ASSIST_PROVIDER_FAILED",
    )
    assert retried["provider_error"] == "provider process could not start"
    assert not Path(retried["workspace_root"]).exists()
    assert len(retried["attempt_history"]) == 1


@exercises("_assist_cancel", "_assist_refresh")
def test_cancel_of_completed_job_is_a_no_op(env) -> None:
    env.provider_output(_run_result({"patch": VALID_PATCH}))
    _submit(env, "assist-cancel-done-1")
    _wait(env, "assist-cancel-done-1")
    cancelled = _ok(env.gateway, "nexus_assist_cancel", {"task_id": "assist-cancel-done-1"})
    assert (cancelled["status"], cancelled["operation"]) == ("COMPLETED", "cancel")
    assert cancelled["result"] == {"patch": VALID_PATCH}


@exercises("_assist_cancel", "_assist_wait", "_assist_refresh")
def test_unknown_task_is_reported_by_result_cancel_and_wait(env) -> None:
    assert (
        _error(env.gateway, "nexus_assist_result", {"task_id": "assist-unknown-1"})
        == "'unknown task_id: assist-unknown-1'"
    )
    assert (
        _error(env.gateway, "nexus_assist_cancel", {"task_id": "assist-unknown-1"})
        == "'unknown task_id: assist-unknown-1'"
    )
    with pytest.raises(KeyError, match="unknown task_id: assist-unknown-1"):
        env.gateway._assist_wait("assist-unknown-1", timeout_seconds=0)


def _write_job(env, **fields: Any) -> dict[str, Any]:
    root = env.gateway._assist_root()
    job = {
        "schema": "nexus.assisted_provider_job.v1",
        "job_kind": "assist",
        "task_id": "assist-crafted-1",
        "job_id": "assist-crafted-job",
        "status": "RUNNING",
        "provider": "cline",
        "pid": DEAD_PID,
        "stdout_artifact": str(root / "assist-crafted-job.stdout"),
        "stderr_artifact": str(root / "assist-crafted-job.stderr"),
        "workspace_root": str(env.tmp / "no-such-workspace"),
        "output_schema": {
            "type": "object",
            "required": ["patch"],
            "properties": {"patch": {"type": "string", "minLength": 1}},
        },
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    job.update(fields)
    return env.gateway._assist_write(job)


@exercises("_assist_refresh", "_assist_response", "_assist_action")
def test_lost_provider_process_without_exit_marker_requires_reconcile(env) -> None:
    _write_job(env)
    result = _ok(env.gateway, "nexus_assist_result", {"task_id": "assist-crafted-1"})
    assert (result["status"], result["blocker"], result["reconciliation_required"]) == (
        "UNKNOWN_REQUIRES_RECONCILE",
        "ASSIST_PROVIDER_PROCESS_LOST",
        True,
    )
    assert (result["next_action"], result["attention_required"]) == ("nexus_task_reconcile", True)


@exercises("_assist_cancel", "_assist_record_stream_artifacts", "_cleanup_assist_workspace")
def test_cancel_of_lost_process_records_missing_streams(env) -> None:
    _write_job(env)
    cancelled = _ok(env.gateway, "nexus_assist_cancel", {"task_id": "assist-crafted-1"})
    assert (cancelled["status"], cancelled["blocker"], cancelled["process_killed"]) == (
        "CANCELLED",
        "ASSIST_PROVIDER_PROCESS_LOST",
        False,
    )
    assert cancelled["stream_flush_status"] == "PARTIAL_OR_MISSING"
    assert (cancelled["stdout_sha256"], cancelled["stdout_bytes"]) == (None, 0)
    assert cancelled["process_cleanup"] is True


@exercises("_assist_refresh", "_decode_model_probe_payload")
def test_agy_print_timeout_with_turn_in_progress_is_a_transport_failure(env) -> None:
    root = env.gateway._assist_root()
    (root / "assist-crafted-job.stdout").write_text(
        '{"status": "SUCCESS", "response": {"ok": true}}', encoding="utf-8"
    )
    (root / "assist-crafted-job.stderr").write_text(
        "[agy] print timeout after 25s; turn in progress\n", encoding="utf-8"
    )
    _write_job(
        env,
        provider="agy",
        job_kind="model_probe",
        resolved_model="m",
        durable_exit_marker=True,
        exit_code=0,
        output_schema={"type": "object"},
    )
    result = _ok(env.gateway, "nexus_assist_result", {"task_id": "assist-crafted-1"})
    assert (result["status"], result["blocker"]) == ("FAILED", "ASSIST_PROVIDER_PRINT_TIMEOUT")
    assert result["provider_error"] == "provider print timeout while turn remained in progress"
    assert result["model_response_verified"] is False and result["result"] is None
    assert (
        result["provider_error_sha256"]
        == hashlib.sha256(b"[agy] print timeout after 25s; turn in progress\n").hexdigest()
    )
    assert result["next_action"] == "nexus_task_retry"


@exercises(
    "_assist_refresh",
    "_decode_model_probe_payload",
    "_validate_output_schema",
    "_write_probe_evidence",
)
def test_crafted_model_probe_with_durable_exit_completes_without_evidence(env) -> None:
    root = env.gateway._assist_root()
    (root / "assist-crafted-job.stdout").write_text(
        '{"status": "SUCCESS", "response": {"ok": true}}', encoding="utf-8"
    )
    (root / "assist-crafted-job.stderr").write_text("", encoding="utf-8")
    _write_job(
        env,
        provider="agy",
        job_kind="model_probe",
        resolved_model="m",
        durable_exit_marker=True,
        exit_code=0,
        output_schema={"type": "object", "required": ["ok"]},
    )
    result = _ok(env.gateway, "nexus_assist_result", {"task_id": "assist-crafted-1"})
    assert (result["status"], result["model_response_verified"], result["result"]) == (
        "COMPLETED",
        True,
        {"ok": True},
    )
    assert result["next_action"] == "none"
    assert result["probe_evidence_hash"] is None  # incomplete job identity: no evidence written


@exercises(
    "_assist_retry", "_assist_refresh", "_assist_response", "_snapshot_workspace", "_assist_write"
)
def test_retry_of_failed_job_relaunches_with_fresh_attempt_through_task_retry(env) -> None:
    env.provider_output("", stderr="boom\n", exit_code=2)
    first = _submit(env, "assist-retry-1")
    failed = _wait(env, "assist-retry-1")
    assert failed["status"] == "FAILED"
    before = env.gateway._assist_read("assist-retry-1")
    retried = _ok(env.gateway, "nexus_task_retry", {"task_id": "assist-retry-1"})
    assert retried["operation"] == "retry" and retried["status"] == "RUNNING"
    assert retried["job_id"] != first["job_id"] and retried["attempt_id"] != first["attempt_id"]
    assert retried["attempt_history"] == [
        {
            "job_id": first["job_id"],
            "attempt_id": first["attempt_id"],
            "status": "FAILED",
            "exit_code": 2,
            "result_artifact": str(
                env.state.resolve() / "assisted_provider_jobs" / "assist-retry-1.json"
            ),
        }
    ]
    job = env.gateway._assist_read("assist-retry-1")
    assert job["action"]["action_type"] == "TASK_RETRY"
    assert job["idempotency_key"].startswith(before["idempotency_key"] + ":retry-")
    assert job["command"] == before["command"] and job["command_hash"] == before["command_hash"]
    assert job["bound_action_request"] == before["bound_action_request"]
    assert job["job_id"].startswith("assist-") and job["reconnected_at"]
    again = _wait(env, "assist-retry-1")
    assert again["status"] == "FAILED" and again["exit_code"] == 2


@exercises("_assist_retry")
def test_retry_requires_a_terminal_failure(env) -> None:
    env.provider_output(_run_result({"patch": VALID_PATCH}))
    _submit(env, "assist-retry-done-1")
    _wait(env, "assist-retry-done-1")
    assert (
        _error(env.gateway, "nexus_task_retry", {"task_id": "assist-retry-done-1"})
        == "ASSIST_RETRY_REQUIRES_TERMINAL_FAILURE"
    )


@exercises("_assist_retry")
def test_retry_requires_released_agy_lease_and_retained_command(env) -> None:
    env.provider_output("", exit_code=1)
    _submit(env, "assist-retry-guard-1")
    _wait(env, "assist-retry-guard-1")
    job = env.gateway._assist_read("assist-retry-guard-1")
    env.gateway._assist_write({
        **job,
        "account_lease_id_hash": "h",
        "account_lease_cleanup_status": "PENDING",
    })
    assert (
        _error(env.gateway, "nexus_task_retry", {"task_id": "assist-retry-guard-1"})
        == "ASSIST_RETRY_REQUIRES_AGY_LEASE_CLEANUP"
    )
    env.gateway._assist_write({**job, "command": []})
    assert (
        _error(env.gateway, "nexus_task_retry", {"task_id": "assist-retry-guard-1"})
        == "ASSIST_RETRY_COMMAND_NOT_RETAINED"
    )
    env.gateway._assist_write({**job, "action": "not-a-mapping"})
    result = _call(env.gateway, "nexus_task_retry", {"task_id": "assist-retry-guard-1"})
    assert (
        result["isError"] is True
        and result["structuredContent"]["code"] == "ACTION_ENVELOPE_INVALID"
    )


# --- G4 job storage ----------------------------------------------------------------


@exercises(
    "_assist_path",
    "_assist_read",
    "_assist_read_snapshot",
    "_assist_write",
    "_assist_read_root",
    "_assist_root",
)
def test_job_storage_validates_slugs_and_tolerates_corrupt_files(env) -> None:
    gateway = env.gateway
    with pytest.raises(GatewayInputError, match="task_id must be a stable bounded slug"):
        gateway._assist_path("../escape")
    assert (
        _error(gateway, "nexus_assist_result", {"task_id": "-bad"})
        == "task_id must be a stable bounded slug"
    )
    assert gateway._assist_read_snapshot("../escape") is None
    assert not (env.state / "assisted_provider_jobs").exists()
    assert gateway._assist_read_snapshot("missing") is None
    assert not (env.state / "assisted_provider_jobs").exists()
    assert gateway._assist_read_root() == env.state.resolve() / "assisted_provider_jobs"
    root = gateway._assist_root()
    assert root.is_dir() and root == gateway._assist_read_root()
    (root / "corrupt.json").write_text("{not json", encoding="utf-8")
    (root / "listy.json").write_text("[1, 2]", encoding="utf-8")
    for task_id in ("corrupt", "listy", "missing"):
        assert gateway._assist_read(task_id) is None
        assert gateway._assist_read_snapshot(task_id) is None
    written = gateway._assist_write({"task_id": "stored-1", "status": "RUNNING"})
    assert written == {"task_id": "stored-1", "status": "RUNNING"}
    assert (root / "stored-1.json").read_text(encoding="utf-8") == json.dumps(
        written, sort_keys=True, ensure_ascii=False, indent=2
    ) + "\n"
    assert gateway._assist_read("stored-1") == gateway._assist_read_snapshot("stored-1") == written
    with pytest.raises(GatewayInputError, match="task_id is required"):
        gateway._assist_write({"status": "x"})


# --- G4 probe evidence -------------------------------------------------------------

MODEL = "cline-pass/glm-5.2"
PROMPT = 'Return exactly {"ok": true}'
CLI_VERSION = "cline 9.9.9"


def _completed_probe_job(env) -> dict[str, Any]:
    gateway = env.gateway
    root = gateway._assist_root()
    stdout = root / "model_probe-1.stdout"
    stderr = root / "model_probe-1.stderr"
    stdout.write_bytes(b'{"ok": true}')
    stderr.write_bytes(b"")
    binary = str(env.cline)
    command = [binary, "--json", "--model", MODEL, PROMPT]
    now = datetime.now(timezone.utc)
    job = {
        "task_id": "probe-1",
        "job_id": "model_probe-1",
        "job_kind": "model_probe",
        "status": "COMPLETED",
        "provider": "cline",
        "requested_model": MODEL,
        "resolved_model": MODEL,
        "binary_path": binary,
        "binary_sha256": "b" * 64,
        "cli_version": CLI_VERSION,
        "cli_version_sha256": hashlib.sha256(CLI_VERSION.encode("utf-8")).hexdigest(),
        "command": command,
        "command_hash": hashlib.sha256(
            json.dumps(command, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "probe_prompt_hash": UnifiedMCPGateway._canonical_hash(PROMPT),
        "probe_semantics_hash": "s" * 64,
        "action_request_hash": "r" * 64,
        "action_id": "action-1",
        "attempt_id": "attempt-1",
        "result": {"ok": True},
        "output_schema": {"type": "object", "required": ["ok"]},
        "submitted_at": (now - timedelta(seconds=30)).isoformat(),
        "started_at": (now - timedelta(seconds=20)).isoformat(),
        "finished_at": now.isoformat(),
        "stdout_artifact": str(stdout),
        "stderr_artifact": str(stderr),
        "stdout_sha256": hashlib.sha256(stdout.read_bytes()).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "stdout_bytes": stdout.stat().st_size,
        "stderr_bytes": 0,
        "filesystem_delta": dict(EMPTY_DELTA),
        "process_cleanup": True,
        "durable_exit_marker": True,
        "stream_flush_status": "FLUSHED",
        "workspace_mode": "isolated",
        "model_response_provenance": "cline_run_result",
        "model_response_verified": True,
        "exit_code": 0,
        "schema_error": "",
    }
    gateway._assist_write(job)
    return job


def _read_evidence(env, **overrides: str):
    values = {
        "provider": "cline",
        "requested_model": MODEL,
        "resolved_model": MODEL,
        "executable": str(env.cline),
        "binary_sha256": "b" * 64,
        "cli_version": CLI_VERSION,
    }
    values.update(overrides)
    return env.gateway._read_probe_evidence(**values)


def _evidence_path(env) -> Path:
    return env.gateway._probe_evidence_read_root() / "{}.json".format(
        UnifiedMCPGateway._probe_evidence_identity({
            "provider": "cline",
            "requested_model": MODEL,
            "resolved_model": MODEL,
            "binary_path": str(env.cline),
            "binary_sha256": "b" * 64,
            "cli_version": CLI_VERSION,
        })
    )


@exercises(
    "_write_probe_evidence",
    "_read_probe_evidence",
    "_probe_evidence_identity",
    "_probe_evidence_root",
    "_probe_evidence_read_root",
    "_probe_command_identity_valid",
    "_provider_requires_authentication",
    "_assist_read_snapshot",
)
def test_probe_evidence_round_trip_binds_job_artifacts_and_identity(env) -> None:
    job = _completed_probe_job(env)
    assert _read_evidence(env) is None  # nothing written yet
    payload = env.gateway._write_probe_evidence(job)
    assert payload is not None
    assert (payload["schema"], payload["status"], payload["exit_code"]) == (
        "nexus.model_probe_evidence.v1",
        "SUCCESS",
        0,
    )
    assert (payload["authenticated"], payload["authentication_evidence"]) == (
        True,
        "successful_exact_model_probe",
    )
    assert "result" not in payload and "output_schema" not in payload
    assert payload["result_hash"] == UnifiedMCPGateway._canonical_hash({"ok": True})
    assert payload["output_schema_hash"] == UnifiedMCPGateway._canonical_hash(job["output_schema"])
    trust = {key: value for key, value in payload.items() if key != "evidence_hash"}
    assert payload["evidence_hash"] == UnifiedMCPGateway._canonical_hash(trust)
    expires = datetime.fromisoformat(payload["expires_at"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=59) < expires <= timedelta(hours=1)
    assert json.loads(_evidence_path(env).read_text(encoding="utf-8")) == payload
    assert env.gateway._probe_evidence_root() == env.gateway._probe_evidence_read_root()
    assert _read_evidence(env) == payload
    assert _read_evidence(env, cli_version="cline 0.0.1") is None
    assert _read_evidence(env, binary_sha256="c" * 64) is None


def _rehash(value: dict[str, Any]) -> dict[str, Any]:
    trust = {key: item for key, item in value.items() if key != "evidence_hash"}
    return {**trust, "evidence_hash": UnifiedMCPGateway._canonical_hash(trust)}


@pytest.mark.parametrize(
    "tamper",
    [
        "expired",
        "finished_in_future",
        "window_too_long",
        "naive_timestamp",
        "status",
        "evidence_hash",
        "unauthenticated",
        "job_missing",
        "job_field_drift",
        "job_failed",
        "artifact_changed",
        "artifact_outside_root",
        "schema_error",
        "result_drift",
        "command_drift",
    ],
)
@exercises("_read_probe_evidence", "_probe_command_identity_valid", "_assist_read_snapshot")
def test_probe_evidence_tamper_matrix_fails_closed(env, tamper: str) -> None:
    job = _completed_probe_job(env)
    payload = env.gateway._write_probe_evidence(job)
    path = _evidence_path(env)
    now = datetime.now(timezone.utc)
    if tamper == "expired":
        path.write_text(
            json.dumps(_rehash({**payload, "expires_at": (now - timedelta(seconds=1)).isoformat()}))
        )
    elif tamper == "finished_in_future":
        path.write_text(
            json.dumps(
                _rehash({**payload, "finished_at": (now + timedelta(minutes=5)).isoformat()})
            )
        )
    elif tamper == "window_too_long":
        path.write_text(
            json.dumps(_rehash({**payload, "finished_at": (now - timedelta(hours=2)).isoformat()}))
        )
    elif tamper == "naive_timestamp":
        path.write_text(
            json.dumps(
                _rehash({
                    **payload,
                    "expires_at": (now + timedelta(minutes=5)).replace(tzinfo=None).isoformat(),
                })
            )
        )
    elif tamper == "status":
        path.write_text(json.dumps(_rehash({**payload, "status": "FAILED"})))
    elif tamper == "evidence_hash":
        path.write_text(json.dumps({**payload, "evidence_hash": "0" * 64}))
    elif tamper == "unauthenticated":
        path.write_text(json.dumps(_rehash({**payload, "authenticated": False})))
    elif tamper == "job_missing":
        (env.gateway._assist_root() / "probe-1.json").unlink()
    elif tamper == "job_field_drift":
        env.gateway._assist_write({**job, "stdout_bytes": job["stdout_bytes"] + 1})
    elif tamper == "job_failed":
        env.gateway._assist_write({**job, "status": "FAILED"})
    elif tamper == "artifact_changed":
        Path(job["stdout_artifact"]).write_bytes(b'{"ok": false}')
    elif tamper == "artifact_outside_root":
        outside = env.tmp / "model_probe-1.stdout"
        outside.write_bytes(Path(job["stdout_artifact"]).read_bytes())
        env.gateway._assist_write({**job, "stdout_artifact": str(outside)})
    elif tamper == "schema_error":
        env.gateway._assist_write({**job, "schema_error": "late"})
    elif tamper == "result_drift":
        env.gateway._assist_write({**job, "result": {"ok": False}})
    elif tamper == "command_drift":
        env.gateway._assist_write({**job, "command": [*job["command"][:-1], "other prompt"]})
    assert _read_evidence(env) is None


@pytest.mark.parametrize(
    "change",
    [
        {"job_kind": "assist"},
        {"status": "FAILED"},
        {"exit_code": 1},
        {"stdout_sha256": ""},
        {"model_response_verified": False},
        {"durable_exit_marker": False},
        {"process_cleanup": False},
        {"filesystem_delta": {"created": ["x"], "removed": [], "changed": []}},
        {"schema_error": "bad"},
        {"stream_flush_status": "PARTIAL_OR_MISSING"},
        {"workspace_mode": "shared"},
        {"command_hash": "0" * 64},
    ],
)
@exercises("_write_probe_evidence", "_probe_command_identity_valid")
def test_probe_evidence_is_only_written_for_complete_verified_isolated_probes(
    env, change: dict
) -> None:
    job = {**_completed_probe_job(env), **change}
    assert env.gateway._write_probe_evidence(job) is None
    assert not env.gateway._probe_evidence_read_root().exists() or not list(
        env.gateway._probe_evidence_read_root().glob("*.json")
    )


def _identity_job(
    provider: str, command: list[str], *, model: str = "m1", prompt: str = "the prompt"
) -> dict[str, Any]:
    return {
        "provider": provider,
        "binary_path": command[0] if command else None,
        "resolved_model": model,
        "command": command,
        "command_hash": hashlib.sha256(
            json.dumps(command, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "probe_prompt_hash": UnifiedMCPGateway._canonical_hash(prompt),
    }


@pytest.mark.parametrize(
    ("provider", "command", "expected"),
    [
        ("cline", ["/b", "--json", "--model", "m1", "the prompt"], True),
        ("opencode", ["/b", "run", "--model", "m1", "the prompt"], True),
        ("mimo", ["/b", "run", "--model", "m1", "the prompt"], True),
        ("grok", ["/b", "--model", "m1", "--single", "the prompt"], True),
        ("agy", ["/b", "--model", "m1", "--prompt", "the prompt", "--print-timeout", "25s"], True),
        ("codex", ["/b", "exec", "-m", "m1", "the prompt"], True),
        ("gemini", ["/b", "-m", "m1", "-p", "the prompt", "--output-format", "json"], True),
        ("ollama", ["/b", "run", "m1", "the prompt"], True),
        ("cline", ["/b", "--json", "--model", "m2", "the prompt"], False),
        ("cline", ["/b", "--json", "the prompt"], False),
        ("cline", ["/b", "--json", "--model", "m1", "another prompt"], False),
        ("agy", ["/b", "--model", "m1", "the prompt"], False),
        ("gemini", ["/b", "-m", "m1", "the prompt"], False),
        ("unknown", ["/b", "--model", "m1", "the prompt"], False),
        ("cline", ["/b", "", "--model", "m1", "the prompt"], False),
    ],
)
@exercises("_probe_command_identity_valid")
def test_probe_command_identity_per_provider(
    provider: str, command: list[str], expected: bool
) -> None:
    job = _identity_job(provider, command)
    if command[-1] == "another prompt":
        job["probe_prompt_hash"] = UnifiedMCPGateway._canonical_hash("the prompt")
    assert UnifiedMCPGateway._probe_command_identity_valid(job) is expected


@exercises("_probe_command_identity_valid")
def test_probe_command_identity_rejects_shape_binary_and_hash_drift() -> None:
    good = _identity_job("cline", ["/b", "--model", "m1", "the prompt"])
    assert UnifiedMCPGateway._probe_command_identity_valid(good) is True
    assert (
        UnifiedMCPGateway._probe_command_identity_valid({**good, "command": "not-a-list"}) is False
    )
    assert UnifiedMCPGateway._probe_command_identity_valid({**good, "command": []}) is False
    assert (
        UnifiedMCPGateway._probe_command_identity_valid({**good, "binary_path": "/other"}) is False
    )
    assert (
        UnifiedMCPGateway._probe_command_identity_valid({**good, "command_hash": "0" * 64}) is False
    )


# --- G4 readiness of provider preflight ---------------------------------------------


def _preflight(**changes: Any) -> dict[str, Any]:
    value = {
        "provider": "cline",
        "requested_model": "m1",
        "resolved_model": "m1",
        "status": "VERSION_VERIFIED",
        "readiness_status": "MODEL_VERIFIED",
        "execution_ready": True,
        "model_reachable": True,
        "requested_model_verified": True,
        "probe_evidence_hash": "e" * 64,
        "binary_path": "/b",
        "binary_sha256": "b" * 64,
        "cli_version_sha256": "v" * 64,
        "probe_expires_at": "2099-01-01T00:00:00+00:00",
        "authenticated": True,
        "authentication_evidence": "successful_exact_model_probe",
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, (True, None)),
        ({"provider": "agy"}, (False, "WORKER_PREFLIGHT_PROVIDER_MISMATCH")),
        ({"requested_model": "m2"}, (False, "WORKER_PREFLIGHT_REQUESTED_MODEL_MISMATCH")),
        ({"resolved_model": "m2"}, (False, "WORKER_PREFLIGHT_RESOLVED_MODEL_MISMATCH")),
        ({"status": "BLOCKED", "blocker": "X_BLOCKER"}, (False, "X_BLOCKER")),
        ({"status": "BLOCKED"}, (False, "WORKER_PREFLIGHT_FAILED")),
        ({"blocker": "MODEL_PROBE_ASYNC_REQUIRED"}, (False, "MODEL_PROBE_ASYNC_REQUIRED")),
        ({"execution_ready": False}, (False, "MODEL_PROBE_REQUIRED")),
        ({"model_reachable": False}, (False, "MODEL_PROBE_REQUIRED")),
        ({"probe_expires_at": ""}, (False, "MODEL_PROBE_REQUIRED")),
        ({"authenticated": False}, (False, "PROVIDER_AUTHENTICATION_REQUIRED")),
        ({"authentication_evidence": "metadata"}, (False, "PROVIDER_AUTHENTICATION_REQUIRED")),
    ],
)
@exercises("_provider_execution_ready", "_provider_requires_authentication")
def test_provider_execution_ready_matrix(env, changes: dict, expected: tuple) -> None:
    assert (
        env.gateway._provider_execution_ready(_preflight(**changes), provider="cline", model="m1")
        == expected
    )


@exercises("_provider_execution_ready", "_provider_requires_authentication")
def test_local_provider_needs_no_authentication_and_model_is_optional(env) -> None:
    local = sorted(gateway_module.LOCAL_ONLY_PROVIDERS)[0]
    assert UnifiedMCPGateway._provider_requires_authentication(local) is False
    assert UnifiedMCPGateway._provider_requires_authentication("cline") is True
    assert UnifiedMCPGateway._provider_requires_authentication("no-such-provider") is False
    preflight = _preflight(provider=local, authenticated=False, authentication_evidence=None)
    assert env.gateway._provider_execution_ready(preflight, provider=local, model=None) == (
        True,
        None,
    )


# --- G4 decoders and schema --------------------------------------------------------


@exercises("_decode_assist_payload")
def test_decode_assist_payload_shapes() -> None:
    decode = UnifiedMCPGateway._decode_assist_payload
    assert decode('{"patch": "p"}', "grok") == {"patch": "p"}
    assert decode('noise\n{"other": 1}\n', "grok") == {"other": 1}
    assert decode('{"other": 1}', "grok", require_patch=True) is None
    assert decode(
        json.dumps({"type": "agent_message", "text": json.dumps({"patch": "p"})}),
        "codex",
        require_patch=True,
    ) == {"patch": "p"}
    assert decode(json.dumps({"item": {"patch": "p"}}), "codex", require_patch=True) == {
        "patch": "p"
    }
    assert decode(
        json.dumps([{"x": 1}, {"result": {"patch": "late"}}]), "cline", require_patch=True
    ) == {"patch": "late"}
    assert decode(
        'log line [{"text": "{\\"patch\\": \\"wrapped\\"}"}] tail', "cline", require_patch=True
    ) == {"patch": "wrapped"}
    assert decode('{"message": "no patch here"}', "cline") == {"message": "no patch here"}
    assert decode('{"message": "no patch here"}', "cline", require_patch=True) is None
    assert decode("", "cline") is None and decode("plain prose", "grok") is None


@exercises("_decode_model_probe_payload")
def test_decode_model_probe_payload_shapes() -> None:
    decode = UnifiedMCPGateway._decode_model_probe_payload
    assert decode('{"ok": true}', "ollama", "m") == ({"ok": True}, "direct_json_document")
    assert decode('{"type": "run_result", "ok": true}', "ollama", "m") == (None, None)
    assert decode('{"ok": true}', "cline", "m") == (None, None)
    assert decode('{"status": "ERROR", "response": {"ok": true}}', "agy", "m") == (None, None)
    assert decode('{"status": "success", "response": "{\\"ok\\": 1}"}', "agy", "m") == (
        {"ok": 1},
        "agy_json_envelope",
    )
    assert decode('{"status": "SUCCESS", "response": 5}', "agy", "m") == (None, None)
    start = json.dumps({"type": "run_start", "providerId": "cline", "modelId": "m"})
    good = json.dumps({
        "type": "run_result",
        "model": {"provider": "cline", "id": "m"},
        "text": '{"ok": true}',
    })
    error = json.dumps({
        "type": "run_result",
        "finishReason": "error",
        "model": {"provider": "cline", "id": "m"},
        "text": '{"ok": false}',
    })
    other = json.dumps({
        "type": "run_result",
        "model": {"provider": "cline", "id": "x"},
        "text": '{"ok": false}',
    })
    assert decode("\n".join([start, good, error, other]), "cline", "m") == (
        {"ok": True},
        "cline_run_result",
    )
    assert decode("\n".join([good]), "cline", "m") == (None, None)
    codex = [
        {"type": "thread.started"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": '{"ok": true}'}},
        {"type": "turn.completed"},
    ]
    assert decode("\n".join(json.dumps(event) for event in codex), "codex", "m") == (
        {"ok": True},
        "codex_jsonl_sequence",
    )
    assert decode("\n".join(json.dumps(event) for event in codex[:3]), "codex", "m") == (None, None)


@pytest.mark.parametrize(
    ("value", "schema", "expected"),
    [
        ({"a": 1}, None, (True, "")),
        ("x", {"type": "object"}, (False, "output_schema_type:$:object")),
        (True, {"type": "integer"}, (False, "output_schema_type:$:integer")),
        (1.5, {"type": "number"}, (True, "")),
        ("b", {"enum": ["a"]}, (False, "output_schema_enum:$")),
        ("  ", {"type": "string", "minLength": 1}, (False, "output_schema_min_length:$:1")),
        ({}, {"type": "object", "required": ["p", "q"]}, (False, "output_schema_missing:$.p,$.q")),
        (
            {"p": 1},
            {"type": "object", "properties": {"p": {"type": "string"}}},
            (False, "output_schema_type:$.p:string"),
        ),
        (
            {"p": "x", "z": 1},
            {"type": "object", "properties": {"p": {}}, "additionalProperties": False},
            (False, "output_schema_additional:$:z"),
        ),
        (
            [1, "x"],
            {"type": "array", "items": {"type": "integer"}},
            (False, "output_schema_type:$[1]:integer"),
        ),
        (None, {"type": "null"}, (True, "")),
    ],
)
@exercises("_validate_output_schema")
def test_validate_output_schema_bounded_subset(value: Any, schema: Any, expected: tuple) -> None:
    assert UnifiedMCPGateway._validate_output_schema(value, schema) == expected


@exercises("_snapshot_workspace")
def test_snapshot_workspace_hashes_files_relative_to_root(tmp_path: Path) -> None:
    assert UnifiedMCPGateway._snapshot_workspace(tmp_path / "missing") == {}
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f.txt").write_bytes(b"x")
    assert UnifiedMCPGateway._snapshot_workspace(tmp_path) == {
        os.path.join("d", "f.txt"): hashlib.sha256(b"x").hexdigest()
    }


def test_exercised_methods_exist() -> None:
    names = {name for exercised in EXERCISED.values() for name in exercised}
    assert len(EXERCISED) >= 30
    missing = sorted(name for name in names if not hasattr(UnifiedMCPGateway, name))
    assert missing == []
    assert not names & {"_assist_command", "_run_agy_plan", "_compile_agy_command"}


def test_fake_provider_is_a_real_executable(env) -> None:
    completed = subprocess.run([str(env.cline)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0
