"""#2783: headless denials preserve targets and never consume healthy accounts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.executors import worker_registry
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.services.agy_failure_signals import (
    AgyHeadlessDenial,
    agy_headless_denial,
    classify_agy_account_failure,
    format_headless_denial_reason,
    last_tool_call_target,
)
from nexus.services.external_account_pool import AccountFailureKind
from tests.nexus.executors import test_agy_worker_outage_cap_2415 as gateway
from tests.services import test_agy_failure_signals_2415 as dispatch_harness


@pytest.fixture
def gateway_pool_env(tmp_path, monkeypatch):
    # The provider is fake; do not invoke the host's macOS keychain service.
    monkeypatch.setattr(
        "nexus.executors.agy_write_admission.isolate_run_home_keychain", lambda _: None
    )
    return gateway.pool_env.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture
def dispatch_pool_env(tmp_path, monkeypatch):
    return dispatch_harness.pool_env.__wrapped__(tmp_path, monkeypatch)


DENIAL = (
    'jetski: no output produced — a tool required the "read_file" permission that '
    "headless mode cannot prompt for, so it was auto-denied."
)
TARGET = "/srv/403/unavailable/authentication/outside.py"
TRANSCRIPT = "\n".join([
    "malformed line",
    json.dumps({"tool_calls": [{"name": "list_dir", "args": {"DirectoryPath": "/old"}}]}),
    json.dumps({
        "step_index": 1,
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "tool_calls": [
            {"name": "view_file", "args": {"AbsolutePath": TARGET, "toolAction": "read"}}
        ],
    }),
    json.dumps({"step_index": 2, "type": "TOOL_RESULT", "status": "DENIED"}),
    "[]",
])


def _transcript(home: Path, session: str = "session-2783") -> Path:
    path = (
        home
        / ".gemini/antigravity-cli/brain"
        / session
        / ".system_generated/logs/transcript_full.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TRANSCRIPT)
    return path


@pytest.mark.parametrize("stderr", [DENIAL, DENIAL + f" Denied path: {TARGET}"])
def test_denial_is_work_failure_even_with_account_keywords(stderr):
    denial = agy_headless_denial("", stderr, stdout_is_envelope=False)
    assert denial == AgyHeadlessDenial("read_file", None, "stderr")
    assert format_headless_denial_reason(denial) == (
        "agy_permission_denied: tool=read_file path=unknown"
    )
    assert classify_agy_account_failure("", stderr, stdout_is_envelope=False) is None


def test_stdout_reply_is_never_denial_evidence():
    for stdout in (
        DENIAL,
        json.dumps({"conversation_id": "id", "status": "SUCCESS", "response": DENIAL}),
        json.dumps({"response": {"denied_actions": [{"action": "read_file"}]}}),
    ):
        assert agy_headless_denial(stdout, "", stdout_is_envelope=True) is None
    assert classify_agy_account_failure(
        DENIAL, "authentication failed", stdout_is_envelope=True
    ) is (AccountFailureKind.AUTH_OR_SESSION_INVALID)


@pytest.mark.parametrize("key", ["path", "file_path", "AbsolutePath", "target"])
def test_envelope_denial_metadata(key):
    stdout = json.dumps({
        "conversation_id": "id",
        "status": "SUCCESS",
        "denied_actions": [{"action": "read_file", key: TARGET}],
    })
    denial = agy_headless_denial(stdout, "", stdout_is_envelope=True)
    assert denial == AgyHeadlessDenial("read_file", TARGET, "envelope")
    assert agy_headless_denial(stdout, "", stdout_is_envelope=False) is None
    assert classify_agy_account_failure(stdout, TARGET, stdout_is_envelope=True) is None


def test_envelope_display_name_and_non_string_path():
    stdout = json.dumps({
        "conversation_id": "id",
        "status": "SUCCESS",
        "denied_actions": [{"display_name": "ViewFile", "path": {"path": TARGET}}],
    })
    assert agy_headless_denial(stdout, "", stdout_is_envelope=True) == AgyHeadlessDenial(
        "ViewFile", None, "envelope"
    )


def test_last_tool_call_is_used_and_missing_target_does_not_reuse_old_path():
    assert last_tool_call_target(TRANSCRIPT) == ("view_file", TARGET)
    assert last_tool_call_target(TRANSCRIPT + '\n{"tool_calls":[{"name":"command"}]}') == (
        "command",
        None,
    )
    assert last_tool_call_target('null\n{"tool_calls":null}\ninvalid') == (None, None)


def test_structured_quota_after_denial_still_decides():
    assert (
        classify_agy_account_failure(
            "", DENIAL + "\n" + gateway.QUOTA_STDERR.decode(), stdout_is_envelope=True
        )
        is AccountFailureKind.QUOTA_EXHAUSTED
    )


@pytest.mark.parametrize("exit_code", [0, 1])
@pytest.mark.parametrize("with_transcript", [False, True])
def test_gateway_denial_preserves_transcript_and_never_rotates(
    gateway_pool_env, exit_code, with_transcript
):
    env = gateway_pool_env
    gateway._install_pool(env, {"a": "denial", "b": "ok", "c": "ok"})
    calls = []
    transcript_paths = []

    def run(request, on_process_group=None):
        calls.append(request)
        if with_transcript:
            transcript_paths.append(_transcript(Path(request.env["HOME"])))
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=exit_code,
            stdout=b"",
            stderr=(DENIAL + TARGET).encode(),
            wall_time_ms=3,
            process_group_id=None,
            timed_out=False,
            descendants_swept=True,
        )

    env.monkeypatch.setattr(worker_registry, "run_cli_worker", run)
    receipt = gateway._invoke(env, calls=3)
    assert len(calls) == receipt.provider_calls == receipt.provider_attempt_count == 1, (
        receipt.failure_reason
    )
    assert receipt.account_rotation_attempts == 0
    assert gateway._retired(env) == set()
    expected_path = TARGET if with_transcript else "unknown"
    assert receipt.failure_reason == f"agy_permission_denied: tool=read_file path={expected_path}"
    assert all(not path.exists() for path in transcript_paths)


@pytest.mark.parametrize(
    "stderr",
    [
        b'AGY_ERROR: {"status":"UNAUTHENTICATED","error_code":401,"code_kind":"http"}',
        b"Authentication required. Please visit the URL to log in",
        gateway.QUOTA_STDERR,
    ],
)
def test_gateway_real_account_failures_still_rotate(gateway_pool_env, stderr):
    env = gateway_pool_env
    gateway._install_pool(env, {"bad": "bad", "good": "ok"})
    seen = []

    def run(request, on_process_group=None):
        seen.append(request)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1 if len(seen) == 1 else 0,
            stdout=gateway._envelope(status="ERROR") if len(seen) == 1 else gateway.OK_STDOUT,
            stderr=stderr if len(seen) == 1 else b"",
            wall_time_ms=3,
            process_group_id=None,
            timed_out=False,
            descendants_swept=True,
        )

    env.monkeypatch.setattr(worker_registry, "run_cli_worker", run)
    receipt = gateway._invoke(env, calls=3)
    assert len(seen) == 2
    assert receipt.account_rotation_attempts >= 1
    assert receipt.failure_reason is None
    markers = list(env.leases.glob("*.quarantine.json")) + list(
        env.leases.glob("*.family-unavailable.gemini.json")
    )
    assert markers


@pytest.mark.parametrize("effect", [False, True])
def test_dispatch_denial_operation_and_envelope_survive_home_cleanup(dispatch_pool_env, effect):
    env = dispatch_pool_env
    dispatch = dispatch_harness.dispatch
    coordinator = env.make(["a", "b", "c"])
    work = env.tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True, capture_output=True)
    target = work / "edited.txt"
    homes = []

    class Boundary:
        worker_failure = None
        sweep_roots = ()

        def __init__(self, source_env):
            self.env = dict(source_env)
            self.run_home = env.tmp_path / "disposable-home"
            self.run_home.mkdir()
            self.env["HOME"] = str(self.run_home)
            homes.append(self.run_home)

        def cleanup(self):
            shutil.rmtree(self.run_home)

        def sweep(self):
            return True

    from types import SimpleNamespace

    env.monkeypatch.setattr(dispatch, "_write_boundary_available", lambda: True)
    env.monkeypatch.setattr(
        dispatch,
        "_agy_dispatch_boundary",
        lambda: SimpleNamespace(
            prepare_accept_edits_boundary=lambda source_env, **_: Boundary(source_env),
            is_expected_run_home_denial=lambda *_: False,
        ),
    )
    calls = []

    def runner(*, env, operation_hook, write_boundary=None, **kwargs):
        calls.append(env)
        _transcript(Path(env["HOME"]))
        operation_hook(provider_session_id="session-2783")
        if effect:
            target.write_text("partial effect")
        return 1, "", DENIAL, False, 3

    original = dispatch.dispatch_run

    def dispatch_run(**kwargs):
        return original(**kwargs, coordinator=coordinator, run_agy_fn=runner)

    env.monkeypatch.setattr(dispatch, "dispatch_run", dispatch_run)
    env.monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "a" * 40)
    journal = dispatch.AgyOperationJournal(env.tmp_path / "operations")
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(work),
        provider="agy",
        model=dispatch_harness.GEMINI,
        effort=None,
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    prompt_file = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_file, "read outside target")
    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_file),
        cwd=str(work),
        mode="accept-edits",
        model=dispatch_harness.GEMINI,
        effort=None,
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=journal.root,
        write_paths=[str(target)],
        heartbeat_interval=0.01,
    )
    assert code == 1
    assert len(calls) == 1
    assert all(not home.exists() for home in homes)
    meta = env.metas[-1]
    assert meta["failure_kind"] == "HEADLESS_TOOL_PERMISSION_DENIED"
    assert meta["attempts"] == 1 and meta["rotations"] == 0
    assert meta["denied_tool"] == "read_file" and meta["denied_path"] == TARGET
    assert bool(meta.get("reconciliation_required")) is effect
    history = journal.read(operation_id)["failure_history"][-1]
    assert history["denied_tool"] == "read_file" and history["denied_path"] == TARGET
    assert dispatch_harness._retired(env) == set()


@pytest.mark.parametrize(
    "stderr",
    [
        'AGY_ERROR: {"status":"UNAUTHENTICATED","error_code":401,"code_kind":"http"}',
        "Authentication required. Please visit the URL to log in",
        dispatch_harness.QUOTA_STDERR,
    ],
)
def test_dispatch_real_account_failures_still_rotate(dispatch_pool_env, stderr):
    env = dispatch_pool_env
    coordinator = env.make(["bad", "good"])
    calls = []

    def runner(**kwargs):
        calls.append(kwargs["env"])
        return (1, "", stderr, False, 3) if len(calls) == 1 else (0, "done", "", False, 3)

    assert dispatch_harness._run(env, coordinator, runner) == 0
    assert len(calls) == 2
    assert env.metas[-1]["rotations"] >= 1
    assert "denied_tool" not in env.metas[-1]
    markers = list((env.tmp_path / "leases").glob("*.quarantine.json")) + list(
        (env.tmp_path / "leases").glob("*.family-unavailable.gemini.json")
    )
    assert markers


@pytest.mark.parametrize(
    ("args", "absolute"),
    [
        ({"file_content": "#!/bin/sh\nexport TOKEN=secret", "file_path": "/w/a.sh"}, True),
        ({"direction": "down"}, False),
        ({"redirect": "https://example.com/x"}, False),
        ({"path": "/w/a\n/w/b"}, True),
        ({"path": "x" * 2000}, False),
    ],
)
def test_target_arg_ignores_non_path_arguments(args, absolute):
    from nexus.services.agy_failure_signals import _target_arg

    value = _target_arg(args, absolute=absolute)
    assert value == ("/w/a.sh" if "file_path" in args else None)


def test_transcript_target_never_copies_file_bodies():
    line = json.dumps({
        "tool_calls": [
            {"name": "write_file", "args": {"file_content": "/*secret*/", "file_path": "/w/b.c"}},
        ]
    })
    assert last_tool_call_target(line) == ("write_file", "/w/b.c")
