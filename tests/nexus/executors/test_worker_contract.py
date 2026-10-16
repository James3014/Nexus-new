import subprocess
import time

import pytest

from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.codex_executor import CodexExecutionReceipt
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerOutcome,
    WorkerProviderUnavailable,
)
from nexus.executors.worker_registry import (
    AgyWorkerAdapter,
    CodexWorkerAdapter,
    OllamaPatchWorkerAdapter,
    WorkerRegistry,
)

# Agy delivery requires a parseable JSON result with status SUCCESS (#1912).
AGY_JSON_OK = b'{"status": "SUCCESS", "response": "done"}'


def test_registry_recognizes_all_governed_provider_names():
    registry = WorkerRegistry.default()

    assert registry.providers == (
        "codex",
        "gemini",
        "agy",
        "opencode",
        "mimo",
        "ollama",
        "grok",
        "cline",
    )
    assert registry.providers == SUPPORTED_WORKER_PROVIDERS


def test_unauthorized_provider_fails_closed_even_when_binary_is_installed(monkeypatch):
    registry = WorkerRegistry.default()
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)

    preflight = registry.preflight("gemini")

    assert preflight.provider == "gemini"
    assert preflight.ready is False
    assert preflight.implementation_status == "IMPLEMENTED"
    with pytest.raises(WorkerProviderUnavailable, match="NEXUS_EXTERNAL_RUNTIME_AUTHORIZED"):
        registry.invoke("gemini", None, None, prompt="bounded")


def test_agy_adapter_requires_external_runtime_authorization(monkeypatch, tmp_path):
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.delenv("NEXUS_AGY_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.setenv("NEXUS_AGY_PROJECT_ID", "project-123")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    adapter = AgyWorkerAdapter()

    preflight = adapter.preflight()

    assert preflight.provider == "agy"
    assert preflight.ready is False
    assert preflight.authorized is False
    assert preflight.implementation_status == "IMPLEMENTED"
    with pytest.raises(WorkerProviderUnavailable, match="NEXUS_AGY_RUNTIME_AUTHORIZED"):
        adapter.invoke(
            type("Contract", (), {"task_id": "agy-task"})(),
            type("Lease", (), {"target_worktree": str(tmp_path)})(),
            prompt="bounded",
            worker_role="implementation",
        )


def test_agy_adapter_accepts_provider_scoped_runtime_authorization(monkeypatch):
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    monkeypatch.setenv("NEXUS_AGY_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")

    preflight = AgyWorkerAdapter().preflight()

    assert preflight.ready is True
    assert preflight.authorized is True


def test_agy_adapter_uses_isolated_project_without_project_id(monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_PROJECT_ID", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    adapter = AgyWorkerAdapter()

    preflight = adapter.preflight()

    assert preflight.ready is True
    assert preflight.executable_available is True
    assert preflight.reason == "ready"


def test_agy_adapter_discovers_binary_from_path_and_uses_policy_model(monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_EXECUTABLE", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/opt/agy/bin/agy")

    adapter = AgyWorkerAdapter()

    assert adapter._configured_executable() == "/opt/agy/bin/agy"
    assert adapter._model() == "gemini-3.8-flash-medium"


def test_agy_adapter_requires_executable(monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_AGY_PROJECT_ID", "project-123")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: None)
    adapter = AgyWorkerAdapter()

    preflight = adapter.preflight()

    assert preflight.ready is False
    assert preflight.executable_available is False
    assert preflight.reason.endswith("executable not found: " + adapter._configured_executable())


@pytest.mark.parametrize(
    ("timeout_seconds", "expected"),
    (
        (42.0, "42s"),
        (42.5, "42.5s"),
        (1200.0, "1200s"),
    ),
)
def test_agy_timeout_arg_serializes_go_duration_seconds(timeout_seconds, expected):
    assert AgyWorkerAdapter._timeout_arg(timeout_seconds) == expected


def test_agy_adapter_invokes_headless_project_scoped_cli_and_records_evidence(monkeypatch, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    executable = tmp_path / "bin" / "agy"
    resolved_executable = str(executable)
    prompt = "WHAT: keep the full Nexus contract\nWHY: --mode must not become the prompt"
    callback_events = []
    process_group_callback = callback_events.append
    captured = {}

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_AGY_PROJECT_ID", "project-123")
    monkeypatch.setenv("NEXUS_AGY_EXECUTABLE", str(executable))
    monkeypatch.delenv("NEXUS_AGY_WORKER_MODEL", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: resolved_executable)

    def fake_worker(request, on_process_group=None):
        captured["request"] = request
        captured["on_process_group"] = on_process_group
        if on_process_group is not None:
            on_process_group(777)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"agy stderr",
            wall_time_ms=25,
            process_group_id=777,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)

    receipt = AgyWorkerAdapter().invoke(
        type("Contract", (), {"task_id": "agy-task"})(),
        type("Lease", (), {"target_worktree": str(target)})(),
        prompt=prompt,
        timeout_seconds=42,
        on_process_group=process_group_callback,
        worker_role="implementation",
    )

    assert captured["request"].cwd == str(target.resolve())
    assert captured["request"].argv == (
        "--new-project",
        "--add-dir",
        str(target.resolve()),
        "--mode",
        "accept-edits",
        "--model",
        "gemini-3.8-flash-medium",
        "--output-format",
        "json",
        "--print-timeout",
        "42s",
        "--print",
        prompt,
    )
    assert captured["request"].argv[-2:] == ("--print", prompt)
    assert captured["on_process_group"] is process_group_callback
    assert callback_events == [777]
    assert receipt.provider == "agy"
    assert receipt.executable_identity == str(executable.resolve())
    assert receipt.argv == captured["request"].argv
    assert receipt.target_worktree == str(target.resolve())
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.stdout_sha256 == CliWorkerResult.hash_bytes(AGY_JSON_OK)
    assert receipt.stderr_sha256 == CliWorkerResult.hash_bytes(b"agy stderr")
    assert receipt.wall_time_ms == 25
    assert receipt.process_group_id == 777
    assert receipt.process_group_killed is False
    assert receipt.timed_out is False
    assert receipt.commit_created is False
    assert receipt.merge_performed is False
    assert receipt.push_performed is False


def test_cline_adapter_is_registered_and_binds_glm_52_on_target(monkeypatch, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    executable = tmp_path / "bin" / "cline"
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_CLINE_WORKER_MODEL", raising=False)
    monkeypatch.setattr(
        "nexus.executors.worker_registry.shutil.which", lambda name: str(executable)
    )
    # #2195: the protected canonical checkout is fingerprinted around the run.
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=canonical, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "i",
        ],
        cwd=canonical,
        check=True,
    )
    monkeypatch.setattr(
        "nexus.executors.worker_registry._default_canonical_checkout_root", lambda: canonical
    )
    captured = {}

    def fake_worker(request, on_process_group=None):
        captured["request"] = request
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b'{"type":"run_result","finishReason":"stop"}\n',
            stderr=b"",
            wall_time_ms=11,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    registry = WorkerRegistry.default()

    preflight = registry.preflight("cline")
    # #2195: the registry binds Cline to the contract's leased worktree.
    receipt = registry.invoke(
        "cline",
        type(
            "Contract",
            (),
            {
                "task_id": "cline-glm-52",
                "target_worktree_root": str(tmp_path),
                "target_repo_root": str(target),
            },
        )(),
        type("Lease", (), {"task_id": "cline-glm-52", "target_worktree": str(target)})(),
        prompt="bounded candidate",
    )

    assert preflight.ready is True
    assert captured["request"].argv == (
        "--cwd",
        str(target.resolve()),
        "--json",
        "--auto-approve",
        "false",
        "--model",
        "glm-5.2",
        "bounded candidate",
    )
    assert captured["request"].cwd == str(target.resolve())
    assert receipt.provider == "cline"
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.evidence_complete is True


def test_codex_adapter_normalizes_provider_receipt_to_common_contract(tmp_path, monkeypatch):
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(executable))

    class FakeExecutor:
        def invoke(self, contract, lease, *, prompt):
            return CodexExecutionReceipt(
                provider="codex",
                task_id="task-1",
                target_worktree=str(tmp_path),
                worker_status="COMPLETED",
                exit_code=0,
                executable_identity="/bin/codex",
                argv=("exec", prompt),
                stdout_sha256="a" * 64,
                stderr_sha256="b" * 64,
                wall_time_ms=17,
                process_group_id=123,
                provider_calls=1,
                provider_attempt_count=1,
                commit_created=False,
                merge_performed=False,
            )

    receipt = CodexWorkerAdapter(executor=FakeExecutor()).invoke(
        object(),
        object(),
        prompt="bounded",
    )

    assert receipt.provider == "codex"
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.evidence_complete is True
    assert receipt.commit_created is False
    assert receipt.merge_performed is False
    assert receipt.push_performed is False


def test_codex_adapter_uses_registered_binary_override_and_fails_closed(tmp_path, monkeypatch):
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(executable))
    adapter = CodexWorkerAdapter()
    preflight = adapter.preflight()
    assert preflight.ready is True
    assert preflight.executable == str(executable.resolve())

    monkeypatch.setenv("NEXUS_CODEX_BIN", str(tmp_path / "missing-codex"))
    blocked = adapter.preflight()
    assert blocked.ready is False
    with pytest.raises(WorkerProviderUnavailable):
        adapter.invoke(object(), object(), prompt="blocked")


def test_ollama_adapter_applies_only_a_validated_unified_diff(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    (target / "file.txt").write_text("before\n")
    patch = b"diff --git a/file.txt b/file.txt\nindex 8f3f5f0..9b5f0b1 100644\n--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-before\n+after\n"

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/ollama")
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=patch,
            stderr=b"",
            wall_time_ms=1,
            process_group_id=None,
        ),
    )

    receipt = OllamaPatchWorkerAdapter(executable="ollama").invoke(
        type("Contract", (), {"task_id": "ollama-task"})(),
        type("Lease", (), {"target_worktree": str(target)})(),
        prompt="change file",
    )

    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.evidence_complete is True
    assert (target / "file.txt").read_text() == "after\n"


def test_opencode_args_match_current_cli_without_removed_auto_flag():
    from nexus.executors.worker_registry import _opencode_args

    argv = _opencode_args("test prompt", "opencode/mimo-v2.5-free")

    assert argv == ("run", "--model", "opencode/mimo-v2.5-free", "test prompt")
    assert "--auto" not in argv


def test_grok_args_match_current_headless_cli():
    from nexus.executors.worker_registry import _grok_args

    argv = _grok_args("test prompt", "grok-4.6")

    assert argv == (
        "--model",
        "grok-4.6",
        "--single",
        "test prompt",
        "--output-format",
        "json",
        "--no-alt-screen",
    )
    assert "--prompt" not in argv


def test_every_adapter_exit_0_result_is_execution_completed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from nexus.executors.worker_registry import (
        DirectCliWorkerAdapter,
        _gemini_args,
        _mimo_args,
        _opencode_args,
    )

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_AGY_PROJECT_ID", "project-123")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=1,
            process_group_id=None,
        ),
    )

    contract = SimpleNamespace(task_id="test-task")
    lease = SimpleNamespace(target_worktree=str(tmp_path))

    for provider, model_env, default_m, args_fn in [
        ("gemini", "NEXUS_GEMINI_WORKER_MODEL", "gemini-2.5-flash", _gemini_args),
        ("opencode", "NEXUS_OPENCODE_WORKER_MODEL", "opencode/big-pickle", _opencode_args),
        ("mimo", "NEXUS_MIMO_WORKER_MODEL", "mimo", _mimo_args),
    ]:
        adapter = DirectCliWorkerAdapter(provider, provider, model_env, default_m, args_fn)
        receipt = adapter.invoke(contract, lease, prompt="test")
        assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
        assert receipt.evidence_complete is True

    agy_adapter = AgyWorkerAdapter()
    agy_receipt = agy_adapter.invoke(contract, lease, prompt="test", worker_role="implementation")
    assert agy_receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert agy_receipt.evidence_complete is True


def test_explicit_worker_model_is_used_in_direct_cli_argv(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from nexus.executors.worker_registry import DirectCliWorkerAdapter, _opencode_args

    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: f"/bin/{name}")
    captured = []
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: (
            captured.append(request)
            or CliWorkerResult(
                status=CliWorkerStatus.COMPLETED,
                executable_identity=request.executable,
                argv=request.argv,
                cwd=request.cwd,
                exit_code=0,
                stdout=b"{}",
                stderr=b"",
                wall_time_ms=1,
                process_group_id=None,
            )
        ),
    )
    adapter = DirectCliWorkerAdapter(
        "opencode", "opencode", "NEXUS_OPENCODE_WORKER_MODEL", "opencode/big-pickle", _opencode_args
    )
    adapter.invoke(
        SimpleNamespace(task_id="model-task"),
        SimpleNamespace(target_worktree=str(tmp_path)),
        prompt="test",
        model="opencode/mimo-v2.5-free",
    )
    assert "opencode/mimo-v2.5-free" in captured[0].argv
    assert "opencode/big-pickle" not in captured[0].argv


def test_deterministic_resolver_all_gates_and_non_empty_diff():
    from types import SimpleNamespace

    from nexus.executors.worker_contract import (
        AttemptResolutionVerdict,
        WorkerExecutionReceipt,
        resolve_attempt,
    )

    exec_receipt = WorkerExecutionReceipt(
        provider="codex",
        task_id="t1",
        target_worktree="/tmp",
        worker_status="COMPLETED",
        outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
        exit_code=0,
        executable_identity="/bin/codex",
        argv=(),
        stdout_sha256="",
        stderr_sha256="",
        wall_time_ms=1,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )

    candidate = SimpleNamespace(changed_files=["a.py"], untracked_files=[], deleted_files=[])
    verified = SimpleNamespace(
        verified=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=True,
        failure_reasons=[],
    )

    res = resolve_attempt(exec_receipt, candidate, verified)
    assert res.verdict == AttemptResolutionVerdict.PROVEN.value
    assert res.candidate_non_empty is True
    assert res.verified is True


def test_deterministic_resolver_empty_candidate_fails():
    from types import SimpleNamespace

    from nexus.executors.worker_contract import (
        AttemptResolutionVerdict,
        WorkerExecutionReceipt,
        resolve_attempt,
    )

    exec_receipt = WorkerExecutionReceipt(
        provider="codex",
        task_id="t1",
        target_worktree="/tmp",
        worker_status="COMPLETED",
        outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
        exit_code=0,
        executable_identity="/bin/codex",
        argv=(),
        stdout_sha256="",
        stderr_sha256="",
        wall_time_ms=1,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )

    candidate = SimpleNamespace(changed_files=[], untracked_files=[], deleted_files=[])
    verified = SimpleNamespace(
        verified=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=True,
        failure_reasons=[],
    )

    res = resolve_attempt(exec_receipt, candidate, verified)
    assert res.verdict == AttemptResolutionVerdict.FAILED.value
    assert res.candidate_non_empty is False
    assert "candidate diff is empty" in res.failure_reasons


def test_deterministic_resolver_timeout_is_incomplete():
    from types import SimpleNamespace

    from nexus.executors.worker_contract import (
        AttemptResolutionVerdict,
        WorkerExecutionReceipt,
        resolve_attempt,
    )

    exec_receipt = WorkerExecutionReceipt(
        provider="codex",
        task_id="t1",
        target_worktree="/tmp",
        worker_status="TIMED_OUT",
        outcome=WorkerOutcome.INCOMPLETE.value,
        exit_code=None,
        executable_identity="/bin/codex",
        argv=(),
        stdout_sha256="",
        stderr_sha256="",
        wall_time_ms=1000,
        process_group_id=None,
        process_group_killed=True,
        timed_out=True,
        provider_calls=1,
        evidence_complete=False,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )

    candidate = SimpleNamespace(changed_files=["a.py"], untracked_files=[], deleted_files=[])
    verified = SimpleNamespace(
        verified=False,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=False,
        failure_reasons=["timeout"],
    )

    res = resolve_attempt(exec_receipt, candidate, verified)
    assert res.verdict == AttemptResolutionVerdict.INCOMPLETE.value
    assert res.escalation_allowed is True


def test_deterministic_resolver_carries_identity_and_candidate_hash():
    from types import SimpleNamespace

    from nexus.executors.worker_contract import (
        AttemptResolutionVerdict,
        WorkerExecutionReceipt,
        resolve_attempt,
    )

    exec_receipt = WorkerExecutionReceipt(
        provider="gemini",
        task_id="task-xyz-789",
        target_worktree="/tmp",
        worker_status="COMPLETED",
        outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
        exit_code=0,
        executable_identity="/bin/gemini",
        argv=(),
        stdout_sha256="",
        stderr_sha256="",
        wall_time_ms=10,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )

    candidate = SimpleNamespace(
        changed_files=["nexus.py"],
        untracked_files=[],
        deleted_files=[],
        candidate_state_hash="cand-hash-1234567890abcdef",
    )
    verified = SimpleNamespace(
        verified=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=True,
        failure_reasons=[],
    )

    res = resolve_attempt(exec_receipt, candidate, verified)
    assert res.task_id == "task-xyz-789"
    assert res.provider == "gemini"
    assert res.execution_outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert res.candidate_state_hash == "cand-hash-1234567890abcdef"
    assert res.verdict == AttemptResolutionVerdict.PROVEN.value
    assert res.escalation_allowed is False


def test_escalation_allowed_is_true_only_for_incomplete():
    from types import SimpleNamespace

    from nexus.executors.worker_contract import (
        AttemptResolutionVerdict,
        WorkerExecutionReceipt,
        resolve_attempt,
    )

    exec_incomplete = WorkerExecutionReceipt(
        provider="codex",
        task_id="t-inc",
        target_worktree="/tmp",
        worker_status="TIMED_OUT",
        outcome=WorkerOutcome.INCOMPLETE.value,
        exit_code=None,
        executable_identity="/bin/codex",
        argv=(),
        stdout_sha256="",
        stderr_sha256="",
        wall_time_ms=1,
        process_group_id=None,
        process_group_killed=False,
        timed_out=True,
        provider_calls=1,
        evidence_complete=False,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )

    exec_failed = WorkerExecutionReceipt(
        provider="codex",
        task_id="t-fail",
        target_worktree="/tmp",
        worker_status="FAILED",
        outcome=WorkerOutcome.FAILED.value,
        exit_code=1,
        executable_identity="/bin/codex",
        argv=(),
        stdout_sha256="",
        stderr_sha256="",
        wall_time_ms=1,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )

    candidate = SimpleNamespace(
        changed_files=["file.py"], untracked_files=[], deleted_files=[], candidate_state_hash="hash"
    )
    verified_fail = SimpleNamespace(
        verified=False,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=False,
        failure_reasons=["failed"],
    )

    res_inc = resolve_attempt(exec_incomplete, candidate, verified_fail)
    assert res_inc.verdict == AttemptResolutionVerdict.INCOMPLETE.value
    assert res_inc.escalation_allowed is True

    res_fail = resolve_attempt(exec_failed, candidate, verified_fail)
    assert res_fail.verdict == AttemptResolutionVerdict.FAILED.value
    assert res_fail.escalation_allowed is False


def test_deterministic_resolver_unknown_candidate_shape_fails_closed():
    from types import SimpleNamespace

    from nexus.executors.worker_contract import (
        AttemptResolutionVerdict,
        WorkerExecutionReceipt,
        resolve_attempt,
    )

    exec_receipt = WorkerExecutionReceipt(
        provider="codex",
        task_id="t-unknown",
        target_worktree="/tmp",
        worker_status="COMPLETED",
        outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
        exit_code=0,
        executable_identity="/bin/codex",
        argv=(),
        stdout_sha256="",
        stderr_sha256="",
        wall_time_ms=1,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )

    candidate = SimpleNamespace(candidate_state_hash="unknown-shape-hash")
    verified = SimpleNamespace(
        verified=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=True,
        failure_reasons=[],
    )

    res = resolve_attempt(exec_receipt, candidate, verified)
    assert res.verdict == AttemptResolutionVerdict.FAILED.value
    assert res.candidate_non_empty is False
    assert "candidate diff is empty" in res.failure_reasons


def test_agy_pool_disabled_preserves_existing_behavior(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    captured = {}

    def fake_worker(request, on_process_group=None):
        captured["request"] = request
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=10,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter()
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-disabled"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 1
    assert receipt.account_alias_hash is None
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value


def test_agy_injected_pool_applies_without_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([AgyAccount(alias="injected", home_dir=str(tmp_path / "h1"))])
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=12,
            process_group_id=None,
        ),
    )
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-injected"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 1
    assert receipt.account_alias_hash == pool.active_account_alias_hash


def test_agy_quota_failure_rotates_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CliWorkerResult(
                status=CliWorkerStatus.COMPLETED,
                executable_identity=request.executable,
                argv=request.argv,
                cwd=request.cwd,
                exit_code=1,
                stdout=b"",
                stderr=b"RESOURCE_EXHAUSTED: Quota exceeded",
                wall_time_ms=10,
                process_group_id=None,
            )
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=15,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-quota", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 2
    assert receipt.wall_time_ms == 25
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value


def test_agy_two_rotations_then_success_exactly_three_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
        AgyAccount(alias="acc3", home_dir=str(tmp_path / "h3")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CliWorkerResult(
                status=CliWorkerStatus.COMPLETED,
                executable_identity=request.executable,
                argv=request.argv,
                cwd=request.cwd,
                exit_code=1,
                stdout=b"",
                stderr=b"429 Rate Limit Exceeded",
                wall_time_ms=5,
                process_group_id=None,
            )
        elif call_count == 2:
            return CliWorkerResult(
                status=CliWorkerStatus.COMPLETED,
                executable_identity=request.executable,
                argv=request.argv,
                cwd=request.cwd,
                exit_code=1,
                stdout=b"",
                stderr=b"401 Unauthorized",
                wall_time_ms=5,
                process_group_id=None,
            )
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-3calls", "maximum_provider_calls": 3})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 3
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert call_count == 3


def test_agy_auth_failure_rotates(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CliWorkerResult(
                status=CliWorkerStatus.COMPLETED,
                executable_identity=request.executable,
                argv=request.argv,
                cwd=request.cwd,
                exit_code=1,
                stdout=b"",
                stderr=b"Invalid API Key",
                wall_time_ms=5,
                process_group_id=None,
            )
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-auth", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 2
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value


def test_agy_one_call_contract_cannot_execute_three_subprocesses(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
        AgyAccount(alias="acc3", home_dir=str(tmp_path / "h3")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"429 Rate Limit Exceeded",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = AgyWorkerAdapter(account_pool=pool).invoke(
        type("Contract", (), {"task_id": "task-one-call", "maximum_provider_calls": 1})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )

    assert call_count == 1
    assert receipt.provider_calls == 1
    assert receipt.outcome == WorkerOutcome.FAILED.value


def test_agy_zero_call_contract_performs_no_subprocess(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        raise AssertionError("worker must not be invoked when provider budget is zero")

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = AgyWorkerAdapter().invoke(
        type("Contract", (), {"task_id": "task-zero-budget", "maximum_provider_calls": 0})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )

    assert call_count == 0
    assert receipt.provider_calls == 0
    assert receipt.worker_status == CliWorkerStatus.START_FAILED.value
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "maximum_provider_calls is 0"


def test_agy_shared_timeout_decreases_across_retries(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
    ])
    seen_timeouts = []

    def fake_worker(request, on_process_group=None):
        seen_timeouts.append(request.timeout_seconds)
        time.sleep(0.02)
        if len(seen_timeouts) == 1:
            return CliWorkerResult(
                status=CliWorkerStatus.COMPLETED,
                executable_identity=request.executable,
                argv=request.argv,
                cwd=request.cwd,
                exit_code=1,
                stdout=b"",
                stderr=b"429 Rate Limit Exceeded",
                wall_time_ms=20,
                process_group_id=None,
            )
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = AgyWorkerAdapter(account_pool=pool).invoke(
        type("Contract", (), {"task_id": "task-shared-timeout", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        timeout_seconds=1.0,
        worker_role="implementation",
    )

    assert receipt.provider_calls == 2
    assert len(seen_timeouts) == 2
    assert 0 < seen_timeouts[1] < seen_timeouts[0] <= 1.0


def test_agy_exhausted_shared_timeout_stops_before_rotation(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        time.sleep(0.03)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"429 Rate Limit Exceeded",
            wall_time_ms=30,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = AgyWorkerAdapter(account_pool=pool).invoke(
        type("Contract", (), {"task_id": "task-budget-exhausted", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        timeout_seconds=0.01,
        worker_role="implementation",
    )

    assert call_count == 1
    assert receipt.provider_calls == 1
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "shared wall-time budget exhausted"


def test_agy_explicit_zero_timeout_executes_zero_subprocesses(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        raise AssertionError("worker must not be invoked when timeout is zero")

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = AgyWorkerAdapter().invoke(
        type("Contract", (), {"task_id": "task-zero-timeout", "maximum_provider_calls": 1})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        timeout_seconds=0,
        worker_role="implementation",
    )

    assert call_count == 0
    assert receipt.provider_calls == 0
    assert receipt.worker_status == CliWorkerStatus.START_FAILED.value
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "shared wall-time budget exhausted"


def test_agy_slow_ensure_active_exhausts_timeout_before_first_subprocess(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    class SlowEnsureActivePool(AgyAccountPoolManager):
        def ensure_active(self, target_worktree=None):
            time.sleep(0.03)
            return super().ensure_active(target_worktree=target_worktree)

    pool = SlowEnsureActivePool([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        raise AssertionError("worker must not be invoked when ensure_active exhausts budget")

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = AgyWorkerAdapter(account_pool=pool).invoke(
        type("Contract", (), {"task_id": "task-slow-ensure", "maximum_provider_calls": 1})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        timeout_seconds=0.01,
        worker_role="implementation",
    )

    assert call_count == 0
    assert receipt.provider_calls == 0
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "shared wall-time budget exhausted"


def test_agy_slow_build_isolated_env_exhausts_timeout_before_first_subprocess(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    class SlowEnvPool(AgyAccountPoolManager):
        def build_isolated_env(self):
            time.sleep(0.03)
            return {}

    pool = SlowEnvPool([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        raise AssertionError("worker must not be invoked when env build exhausts budget")

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = AgyWorkerAdapter(account_pool=pool).invoke(
        type("Contract", (), {"task_id": "task-slow-env", "maximum_provider_calls": 1})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        timeout_seconds=0.01,
        worker_role="implementation",
    )

    assert call_count == 0
    assert receipt.provider_calls == 0
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "shared wall-time budget exhausted"


def test_agy_receipt_wall_time_includes_setup_overhead(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    class SlowEnsureActivePool(AgyAccountPoolManager):
        def ensure_active(self, target_worktree=None):
            time.sleep(0.02)
            return super().ensure_active(target_worktree=target_worktree)

    pool = SlowEnsureActivePool([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
    ])

    def fake_worker(request, on_process_group=None):
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = AgyWorkerAdapter(account_pool=pool).invoke(
        type("Contract", (), {"task_id": "task-wall-time-overhead", "maximum_provider_calls": 1})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        timeout_seconds=1.0,
        worker_role="implementation",
    )

    assert receipt.provider_calls == 1
    assert receipt.wall_time_ms >= 15


def test_agy_syntax_failure_does_not_rotate(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"SyntaxError: invalid syntax",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-syntax"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 1
    assert call_count == 1
    assert receipt.outcome == WorkerOutcome.FAILED.value


def test_agy_timeout_does_not_rotate(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
    ])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        return CliWorkerResult(
            status=CliWorkerStatus.TIMED_OUT,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=None,
            stdout=b"",
            stderr=b"",
            wall_time_ms=100,
            process_group_id=None,
            timed_out=True,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-timeout"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 1
    assert call_count == 1
    assert receipt.outcome == WorkerOutcome.INCOMPLETE.value
    assert receipt.timed_out is True


def test_agy_ensure_active_failure_before_first_call_yields_zero_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")

    class BrokenPool:
        def ensure_active(self, target_worktree=None):
            raise RuntimeError("Pool is broken")

    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b"",
            stderr=b"",
            wall_time_ms=0,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=BrokenPool())
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-zero-calls"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 0
    assert call_count == 0
    assert receipt.outcome == WorkerOutcome.FAILED.value


def test_agy_ensure_active_failure_after_one_call_does_not_overcount(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")

    class FlakyPool:
        def __init__(self):
            self.calls = 0
            self.active_account_alias_hash = "hash123"

        def ensure_active(self, target_worktree=None):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("ensure_active failed on call 2")
            return self

        def rotate_account(self, reason=None, failed_account_hash=None):
            pass

        def build_isolated_env(self):
            return {}

    subprocess_calls = 0

    def fake_worker(request, on_process_group=None):
        nonlocal subprocess_calls
        subprocess_calls += 1
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"Quota exceeded",
            wall_time_ms=10,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=FlakyPool())
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-no-overcount", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 1
    assert subprocess_calls == 1


def test_agy_failed_rotation_stops_and_records_call(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([AgyAccount(alias="only_acc", home_dir=str(tmp_path / "h1"))])
    call_count = 0

    def fake_worker(request, on_process_group=None):
        nonlocal call_count
        call_count += 1
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"Quota exceeded",
            wall_time_ms=10,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-fail-rotate", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.provider_calls == 1
    assert call_count == 1
    assert receipt.outcome == WorkerOutcome.FAILED.value


def test_agy_subprocess_api_keys_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "secret_gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "secret_google")
    monkeypatch.setenv("GOOGLE_GENAI_API_KEY", "secret_genai")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))])
    captured_env = {}

    def fake_worker(request, on_process_group=None):
        nonlocal captured_env
        captured_env = dict(request.env or {})
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    adapter.invoke(
        type("Contract", (), {"task_id": "task-api-keys"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert "GEMINI_API_KEY" not in captured_env
    assert "GOOGLE_API_KEY" not in captured_env
    assert "GOOGLE_GENAI_API_KEY" not in captured_env


def test_agy_receipt_contains_alias_hash_only_no_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    acc = AgyAccount(alias="user@example.com_secret_identity", home_dir=str(tmp_path / "h1"))
    pool = AgyAccountPoolManager([acc])
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        ),
    )
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-hash-only"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert receipt.account_alias_hash == acc.alias_hash
    assert "user@example.com" not in str(receipt)
    assert "secret_identity" not in str(receipt)


def test_no_unified_runtime_changes():
    from pathlib import Path

    unified_runtime_path = Path("nexus/orchestrator/unified_runtime.py")
    if unified_runtime_path.exists():
        import subprocess

        diff = subprocess.run(
            ["git", "diff", "--name-only", str(unified_runtime_path)],
            capture_output=True,
            text=True,
        )
        assert diff.stdout.strip() == "", (
            "nexus/orchestrator/unified_runtime.py must not be modified"
        )


def test_agy_eligible_failover_continuation_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    acc1 = AgyAccount(alias="user1_secret_email@gmail.com", home_dir=str(tmp_path / "h1"))
    acc2 = AgyAccount(alias="user2_secret_email@gmail.com", home_dir=str(tmp_path / "h2"))
    pool = AgyAccountPoolManager([acc1, acc2])

    seen_requests = []

    def fake_worker(request, on_process_group=None):
        seen_requests.append(request)
        if len(seen_requests) == 1:
            return CliWorkerResult(
                status=CliWorkerStatus.COMPLETED,
                executable_identity=request.executable,
                argv=request.argv,
                cwd=request.cwd,
                exit_code=1,
                stdout=b"",
                stderr=b"RESOURCE_EXHAUSTED: Quota exceeded",
                wall_time_ms=10,
                process_group_id=None,
            )
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=15,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "agy-continuation-task", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="original prompt text",
        worker_role="implementation",
    )

    assert len(seen_requests) == 2
    assert seen_requests[0].argv[-1] == "original prompt text"

    second_prompt = seen_requests[1].argv[-1]
    assert "[Continuation Handoff]" in second_prompt
    assert "Task ID: agy-continuation-task" in second_prompt
    assert "Attempt: 2" in second_prompt
    assert f"Previous Account Hash: {acc1.alias_hash}" in second_prompt
    assert f"New Account Hash: {acc2.alias_hash}" in second_prompt
    assert "Failure Kind: QUOTA_EXHAUSTED" in second_prompt
    assert "Original Instruction: original prompt text" in second_prompt
    assert "user1_secret_email" not in second_prompt
    assert "user2_secret_email" not in second_prompt

    assert receipt.provider_calls == 2
    assert receipt.provider_attempt_count == 2
    assert receipt.account_alias_hash == acc2.alias_hash
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value


def test_agy_non_eligible_failure_aborts_loop(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    acc1 = AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))
    acc2 = AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2"))
    pool = AgyAccountPoolManager([acc1, acc2])

    seen_requests = []

    def fake_worker(request, on_process_group=None):
        seen_requests.append(request)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"403 Forbidden: Permission denied",
            wall_time_ms=10,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "agy-abort-task", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )

    assert len(seen_requests) == 1
    assert receipt.provider_calls == 1
    assert receipt.provider_attempt_count == 1
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason is not None
    assert "non-eligible account failure: PERMISSION_OR_SCOPE_ERROR" in receipt.failure_reason


def test_terminal_release_spy(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    acc = AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))
    pool = AgyAccountPoolManager([acc])

    released_leases = []
    original_release = pool.release

    def spy_release(lease):
        released_leases.append(lease)
        original_release(lease)

    monkeypatch.setattr(pool, "release", spy_release)

    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda req, **opts: CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=req.executable,
            argv=req.argv,
            cwd=req.cwd,
            exit_code=0,
            stdout=AGY_JSON_OK,
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        ),
    )
    adapter = AgyWorkerAdapter(account_pool=pool)
    adapter.invoke(
        type("Contract", (), {"task_id": "success-task", "maximum_provider_calls": 1})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert len(released_leases) == 1
    released_leases.clear()

    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda req, **opts: CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=req.executable,
            argv=req.argv,
            cwd=req.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"403 Forbidden",
            wall_time_ms=5,
            process_group_id=None,
        ),
    )
    adapter.invoke(
        type("Contract", (), {"task_id": "non-eligible-task", "maximum_provider_calls": 1})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert len(released_leases) == 1
    released_leases.clear()

    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda req, **opts: CliWorkerResult(
            status=CliWorkerStatus.TIMED_OUT,
            executable_identity=req.executable,
            argv=req.argv,
            cwd=req.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        ),
    )
    adapter.invoke(
        type("Contract", (), {"task_id": "timeout-task", "maximum_provider_calls": 1})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        worker_role="implementation",
    )
    assert len(released_leases) == 1
    released_leases.clear()


def test_clock_decrease_real_time(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    acc1 = AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))
    acc2 = AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2"))
    pool = AgyAccountPoolManager([acc1, acc2])

    seen_timeouts = []

    def fake_worker(request, on_process_group=None):
        seen_timeouts.append(request.timeout_seconds)
        time.sleep(0.01)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=1,
            stdout=b"",
            stderr=b"RESOURCE_EXHAUSTED: Quota exceeded",
            wall_time_ms=10,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    adapter.invoke(
        type("Contract", (), {"task_id": "clock-decrease-task", "maximum_provider_calls": 2})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
        timeout_seconds=0.5,
        worker_role="implementation",
    )

    assert len(seen_timeouts) == 2
    assert seen_timeouts[1] < seen_timeouts[0]


def test_mandatory_negative_tests(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    acc1 = AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))
    acc2 = AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2"))

    failures = [
        (CliWorkerStatus.TIMED_OUT, 1, b"", b"", "TIMEOUT"),
        (
            CliWorkerStatus.COMPLETED,
            2,
            b"",
            b"SyntaxError: unexpected EOF",
            "SYNTAX_OR_IMPLEMENTATION_ERROR",
        ),
        (
            CliWorkerStatus.COMPLETED,
            3,
            b"",
            b"ValueError: Invalid model option",
            "MODEL_OR_TASK_ERROR",
        ),
    ]

    for status, exit_code, stdout, stderr, expected_kind in failures:
        pool = AgyAccountPoolManager([acc1, acc2])
        monkeypatch.setattr(
            "nexus.executors.worker_registry.run_cli_worker",
            lambda req, **opts: CliWorkerResult(
                status=status,
                executable_identity=req.executable,
                argv=req.argv,
                cwd=req.cwd,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                wall_time_ms=5,
                process_group_id=None,
            ),
        )
        adapter = AgyWorkerAdapter(account_pool=pool)
        receipt = adapter.invoke(
            type(
                "Contract", (), {"task_id": f"neg-{expected_kind}", "maximum_provider_calls": 2}
            )(),
            type("Lease", (), {"target_worktree": str(tmp_path)})(),
            prompt="hello",
            worker_role="implementation",
        )
        assert receipt.provider_calls == 1


# ---------------------------------------------------------------------------
# #2195: Cline write admission (no auto-approve, integrity, denied actions)
# ---------------------------------------------------------------------------


def _cline_git_repo(root):
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "i"],
        cwd=root,
        check=True,
    )
    return root.resolve()


def _cline_ready(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_CLINE_WORKER_MODEL", raising=False)
    monkeypatch.setattr(
        "nexus.executors.worker_registry.shutil.which", lambda name: str(tmp_path / "cline")
    )


def _cline_run(monkeypatch, tmp_path, *, stdout, side_effect=None, target=None, contract=None):
    from nexus.executors.worker_registry import ClineWorkerAdapter

    _cline_ready(monkeypatch, tmp_path)
    canonical = _cline_git_repo(tmp_path / "canonical")
    if target is None:
        target = tmp_path / "target"
        target.mkdir()
    calls = []

    def fake_worker(request, on_process_group=None):
        calls.append(request)
        if side_effect is not None:
            side_effect(canonical)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=stdout,
            stderr=b"",
            wall_time_ms=1,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = ClineWorkerAdapter(canonical_root=canonical)
    receipt = adapter.invoke(
        contract or type("Contract", (), {"task_id": "cline-2195"})(),
        type("Lease", (), {"task_id": "cline-2195", "target_worktree": str(target)})(),
        prompt="bounded",
    )
    return receipt, calls, canonical


_CLINE_OK = (
    b'{"type":"run_start","providerId":"cline"}\n{"type":"run_result","finishReason":"stop"}\n'
)


def test_cline_permission_bypass_detects_every_auto_approve_shape():
    from nexus.executors.worker_registry import _cline_args, cline_permission_bypass

    assert cline_permission_bypass(_cline_args("p", "m")) is False
    assert (
        cline_permission_bypass(("--json", "--model", "m", "p")) is True
    )  # default is auto-approve
    assert cline_permission_bypass(("--json", "--yolo", "--model", "m", "p")) is True
    assert cline_permission_bypass(("--json", "-y", "--auto-approve", "false", "p")) is True
    assert cline_permission_bypass(("--json", "--auto-approve", "true", "p")) is True
    assert cline_permission_bypass(("--json", "--auto-approve=false", "p")) is True
    assert (
        cline_permission_bypass(("--auto-approve", "false", "--auto-approve", "true", "p")) is True
    )
    # Every element is scanned, the trailing prompt included.
    assert cline_permission_bypass(("--json", "--auto-approve", "false", "--yolo")) is True


def test_cline_delivery_requires_a_successful_run_result():
    from nexus.executors.worker_registry import cline_delivery_failure

    assert cline_delivery_failure(_CLINE_OK, b"") is None
    assert cline_delivery_failure(b"plain text", b"") == "cline_output_unparseable"
    assert (
        cline_delivery_failure(b'{"type":"run_result","finishReason":"error"}\n', b"")
        == "cline_status_not_success"
    )
    denied = (
        _CLINE_OK
        + b'{"type":"agent_event","event":{"type":"tool-result",'
        + b'"output":{"type":"execution-denied","reason":"no"}}}\n'
    )
    assert cline_delivery_failure(denied, b"") == "cline_permission_denied"
    assert cline_delivery_failure(_CLINE_OK, b"execution-denied: write_to_file") == (
        "cline_permission_denied"
    )


def test_cline_successful_run_on_isolated_target_is_delivery(monkeypatch, tmp_path):
    receipt, calls, _ = _cline_run(monkeypatch, tmp_path, stdout=_CLINE_OK)

    assert len(calls) == 1
    assert "--yolo" not in calls[0].argv
    assert calls[0].argv[calls[0].argv.index("--auto-approve") + 1] == "false"
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.provider_permission_mode == "auto_approve_false"
    assert receipt.failure_reason is None


def test_cline_denied_action_is_non_delivery(monkeypatch, tmp_path):
    stdout = (
        _CLINE_OK
        + b'{"type":"tool_result","is_error":true,"result":"Tool execution denied by user."}\n'
    )
    receipt, _, _ = _cline_run(monkeypatch, tmp_path, stdout=stdout)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.evidence_complete is False
    assert receipt.failure_reason == "cline_permission_denied"


def test_cline_canonical_checkout_change_fails_the_run(monkeypatch, tmp_path):
    def mutate(canonical):
        (canonical / "tracked.txt").write_text("changed\n", encoding="utf-8")

    receipt, _, canonical = _cline_run(monkeypatch, tmp_path, stdout=_CLINE_OK, side_effect=mutate)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "canonical_checkout_integrity_violation"
    # Reported, never reverted.
    assert (canonical / "tracked.txt").read_text(encoding="utf-8") == "changed\n"


def test_cline_target_overlapping_canonical_is_refused_before_launch(monkeypatch, tmp_path):
    from nexus.executors.worker_registry import ClineWorkerAdapter

    # The target is inside the canonical checkout.
    target = tmp_path / "canonical" / "nested"

    _cline_ready(monkeypatch, tmp_path)
    canonical = _cline_git_repo(tmp_path / "canonical")
    target.mkdir()
    launched = []
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: launched.append(request),
    )
    receipt = ClineWorkerAdapter(canonical_root=canonical).invoke(
        type("Contract", (), {"task_id": "cline-2195"})(),
        type("Lease", (), {"task_id": "cline-2195", "target_worktree": str(target)})(),
        prompt="bounded",
    )

    assert launched == []
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason == "cline_target_overlaps_canonical_checkout"


def test_cline_target_outside_the_lease_is_refused(monkeypatch, tmp_path):
    contract = type(
        "Contract",
        (),
        {
            "task_id": "cline-2195",
            "target_worktree_root": str(tmp_path / "leases"),
            "target_repo_root": str(tmp_path / "elsewhere"),
        },
    )()
    receipt, calls, _ = _cline_run(monkeypatch, tmp_path, stdout=_CLINE_OK, contract=contract)

    assert calls == []
    assert receipt.failure_reason == "cline_target_not_leased_worktree"


def test_cline_markers_in_model_text_are_not_a_denial():
    from nexus.executors.worker_registry import cline_delivery_failure

    quoted = (
        b'{"type":"agent_event","event":{"type":"text","text":'
        b'"execution-denied / Tool execution denied by user."}}\n'
        b'{"type":"tool_result","is_error":false,"result":"grep: execution denied, denied by user"}\n'
        b'{"type":"tool-call","input":{"type":"execution-denied"}}\n'
        b"plain log line: execution-denied\n"
    )
    assert cline_delivery_failure(quoted + _CLINE_OK, b"") is None


def test_cline_structured_denial_events_are_non_delivery():
    from nexus.executors.worker_registry import cline_delivery_failure

    for event in (
        b'{"type":"tool_result","is_error":true,"result":"Tool execution denied by user."}',
        b'{"type":"tool-result","output":{"type":"execution-denied"}}',
        b'{"type":"agent_event","event":{"content":[{"type":"tool-approval-response",'
        b'"approved":false}]}}',
    ):
        assert cline_delivery_failure(_CLINE_OK + event + b"\n", b"") == (
            "cline_permission_denied"
        ), event


def test_cline_flag_shaped_prompt_is_refused_before_launch(monkeypatch, tmp_path):
    from nexus.executors.worker_registry import ClineWorkerAdapter

    _cline_ready(monkeypatch, tmp_path)
    canonical = _cline_git_repo(tmp_path / "canonical")
    target = tmp_path / "target"
    target.mkdir()
    launched = []
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: launched.append(request),
    )
    for prompt in ("--yolo", "-y", "--auto-approve=true", "-"):
        receipt = ClineWorkerAdapter(canonical_root=canonical).invoke(
            type("Contract", (), {"task_id": "cline-2195"})(),
            type("Lease", (), {"task_id": "cline-2195", "target_worktree": str(target)})(),
            prompt=prompt,
        )
        assert receipt.failure_reason == "cline_prompt_shape_unsupported", prompt
        assert receipt.provider_calls == 0
    assert launched == []


def test_cline_registry_requires_a_leased_target(monkeypatch, tmp_path):
    _cline_ready(monkeypatch, tmp_path)
    canonical = _cline_git_repo(tmp_path / "canonical")
    monkeypatch.setattr(
        "nexus.executors.worker_registry._default_canonical_checkout_root", lambda: canonical
    )
    target = tmp_path / "target"
    target.mkdir()
    launched = []
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: launched.append(request),
    )
    # A contract without target_worktree_root must not skip the lease check.
    receipt = WorkerRegistry.default().invoke(
        "cline",
        type("Contract", (), {"task_id": "cline-2195"})(),
        type("Lease", (), {"task_id": "cline-2195", "target_worktree": str(target)})(),
        prompt="bounded",
    )

    assert launched == []
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason == "cline_target_not_leased_worktree"


# ---------------------------------------------------------------------------
# #2254: Cline runs under the Seatbelt + disposable HOME + exact env boundary
# ---------------------------------------------------------------------------

_CLINE_TTY_DENIAL = (
    b'{"type":"agent_event","event":{"type":"content_end","contentType":"tool",'
    b'"toolName":"editor","output":{"error":"Tool \\"editor\\" requires approval in a TTY '
    b'session -- NOT a tool or system failure. Clarify with user before proceeding."},'
    b'"error":"{\\"error\\":\\"Tool \\\\\\"editor\\\\\\" requires approval in a TTY session\\"}"}}\n'
)


def _cline_fake_home(tmp_path, monkeypatch):
    home = tmp_path / "realhome"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "id_ed25519").write_text("PRIVATE", encoding="utf-8")
    (home / ".config" / "gh").mkdir(parents=True)
    (home / ".config" / "gh" / "hosts.yml").write_text("token: x", encoding="utf-8")
    (home / ".gitconfig").write_text("[user]\nname=x\n", encoding="utf-8")
    settings = home / ".cline" / "data" / "settings"
    settings.mkdir(parents=True)
    (settings / "providers.json").write_text('{"version":1}', encoding="utf-8")
    (home / ".cline" / "data" / "sessions").mkdir()
    (home / ".cline" / "data" / "sessions" / "old.json").write_text("{}", encoding="utf-8")
    (home / ".cline" / "data" / "db").mkdir()
    (home / ".cline" / "data" / "db" / "teams.db").write_text("db", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GH_TOKEN", "leak")
    monkeypatch.setenv("NEXUS_SECRET", "leak")
    return home


def _cline_admitted_run(monkeypatch, tmp_path, *, stdout=_CLINE_OK, side_effect=None, result=None):
    """Run the adapter with a fake worker; return (receipt, requests, snapshots, target)."""
    from nexus.executors.worker_registry import ClineWorkerAdapter

    _cline_ready(monkeypatch, tmp_path)
    canonical = _cline_git_repo(tmp_path / "canonical")
    target = tmp_path / "target"
    target.mkdir()
    requests, snapshots = [], []

    def fake_worker(request, on_process_group=None):
        requests.append(request)
        from pathlib import Path

        home = Path((request.env or {}).get("HOME", "/nonexistent"))
        snapshots.append(
            sorted(p.relative_to(home).as_posix() for p in home.rglob("*"))
            if home.is_dir()
            else None
        )
        if side_effect is not None:
            side_effect(target, canonical)
        if result is not None:
            return result
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=stdout,
            stderr=b"",
            wall_time_ms=1,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = ClineWorkerAdapter(canonical_root=canonical).invoke(
        type("Contract", (), {"task_id": "cline-2254"})(),
        type("Lease", (), {"task_id": "cline-2254", "target_worktree": str(target)})(),
        prompt="bounded",
    )
    return receipt, requests, snapshots, target, canonical


def test_cline_request_carries_seatbelt_disposable_home_and_exact_env(monkeypatch, tmp_path):
    """r1 (#2254 item 1): the request must be confined, not inherit the host HOME."""
    real_home = _cline_fake_home(tmp_path, monkeypatch)
    receipt, requests, snapshots, target, canonical = _cline_admitted_run(monkeypatch, tmp_path)

    request = requests[0]
    assert request.seatbelt_profile, "cline must run under a Seatbelt write profile"
    assert request.exact_env is True
    assert request.sweep_descendants_on_exit is True
    env = dict(request.env or {})
    assert env.get("HOME") and env["HOME"] != str(real_home)
    assert "GH_TOKEN" not in env and "NEXUS_SECRET" not in env
    assert env["TMPDIR"].startswith(env["HOME"].rsplit("/", 1)[0])
    # the disposable HOME carries only cline's auth file, never other credentials
    assert snapshots[0] is not None
    assert ".cline/data/settings/providers.json" in snapshots[0]
    for forbidden in (".ssh", ".config", ".gitconfig", ".cline/data/sessions", ".cline/data/db"):
        assert not any(item == forbidden or item.startswith(forbidden + "/") for item in snapshots[0])
    # target and the run root are writable, the canonical checkout is not
    assert f'(subpath "{target.resolve()}")' in request.seatbelt_profile
    assert str(canonical) not in request.seatbelt_profile
    assert receipt.provider_write_sandbox and receipt.provider_write_sandbox.startswith("seatbelt:")
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value


def test_cline_run_home_is_removed_after_the_run(monkeypatch, tmp_path):
    from pathlib import Path

    _cline_fake_home(tmp_path, monkeypatch)
    _, requests, _, _, _ = _cline_admitted_run(monkeypatch, tmp_path)
    assert not Path(requests[0].env["HOME"]).exists()


def test_cline_planted_escaping_symlink_fails_the_run(monkeypatch, tmp_path):
    """r2 (#2254 item 3): a symlink planted in the target pointing outside is an escape."""
    import os

    outside = tmp_path / "outside"
    outside.mkdir()

    def plant(target, canonical):
        os.symlink(outside, target / "escape")

    receipt, _, _, _, _ = _cline_admitted_run(monkeypatch, tmp_path, side_effect=plant)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.evidence_complete is False
    assert receipt.failure_reason == "cline_target_symlink_escape"


def test_cline_preexisting_escaping_symlink_is_not_attributed_to_the_run(monkeypatch, tmp_path):
    """Same before/after comparison as agy: only a change fails the run."""
    import os

    from nexus.executors.worker_registry import ClineWorkerAdapter

    _cline_ready(monkeypatch, tmp_path)
    canonical = _cline_git_repo(tmp_path / "canonical")
    target = tmp_path / "target"
    target.mkdir()
    os.symlink(tmp_path, target / "old-link")

    def fake_worker(request, on_process_group=None):
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=_CLINE_OK,
            stderr=b"",
            wall_time_ms=1,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = ClineWorkerAdapter(canonical_root=canonical).invoke(
        type("Contract", (), {"task_id": "cline-2254"})(),
        type("Lease", (), {"task_id": "cline-2254", "target_worktree": str(target)})(),
        prompt="bounded",
    )
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value


def test_cline_gitdir_pointer_rewrite_fails_the_run(monkeypatch, tmp_path):
    """#2254 item 3: the target's .git entry may not be repointed by the worker."""

    def repoint(target, canonical):
        (target / ".git").write_text(f"gitdir: {canonical}/.git\n", encoding="utf-8")

    receipt, _, _, _, _ = _cline_admitted_run(monkeypatch, tmp_path, side_effect=repoint)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "cline_target_gitdir_tampered"


def test_cline_denied_tool_with_finish_reason_stop_is_non_delivery(monkeypatch, tmp_path):
    """r3 (#2254 item 5): the real cline headless denial shape, then a clean 'stop'."""
    stdout = _CLINE_TTY_DENIAL + _CLINE_OK
    receipt, _, _, _, _ = _cline_admitted_run(monkeypatch, tmp_path, stdout=stdout)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.evidence_complete is False
    assert receipt.failure_reason == "cline_permission_denied"


def test_cline_tty_denial_text_in_model_output_is_not_a_denial():
    from nexus.executors.worker_registry import cline_delivery_failure

    quoted = (
        b'{"type":"agent_event","event":{"type":"content_end","contentType":"text",'
        b'"text":"requires approval in a TTY session"}}\n'
        b'{"type":"agent_event","event":{"type":"content_end","contentType":"tool",'
        b'"toolName":"read_file","output":{"result":"requires approval in a TTY session"}}}\n'
    )
    assert cline_delivery_failure(quoted + _CLINE_OK, b"") is None


def test_cline_aborted_run_is_not_delivery():
    from nexus.executors.worker_registry import cline_delivery_failure

    assert (
        cline_delivery_failure(b'{"type":"run_result","finishReason":"aborted"}\n', b"")
        == "cline_status_not_success"
    )


def test_cline_without_seatbelt_fails_closed(monkeypatch, tmp_path):
    result = CliWorkerResult(
        status=CliWorkerStatus.START_FAILED,
        executable_identity="cline",
        argv=(),
        cwd=str(tmp_path),
        exit_code=1,
        stdout=b"",
        stderr=b"seatbelt_unavailable",
        wall_time_ms=0,
        process_group_id=None,
    )
    receipt, requests, _, _, _ = _cline_admitted_run(monkeypatch, tmp_path, result=result)

    assert requests[0].seatbelt_profile  # never launched without a profile
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "cline_seatbelt_unavailable"


def test_cline_descendant_sweep_failure_is_non_delivery(monkeypatch, tmp_path):
    result = CliWorkerResult(
        status=CliWorkerStatus.COMPLETED,
        executable_identity="cline",
        argv=(),
        cwd=str(tmp_path),
        exit_code=0,
        stdout=_CLINE_OK,
        stderr=b"",
        wall_time_ms=1,
        process_group_id=None,
        descendants_swept=False,
    )
    receipt, _, _, _, _ = _cline_admitted_run(monkeypatch, tmp_path, result=result)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "cline_descendant_sweep_failed"


def test_cline_run_home_helper_copies_only_the_auth_file(tmp_path):
    from nexus.executors.agy_write_admission import (
        CLINE_RUN_HOME_COPIED_FILES,
        materialize_cline_run_home,
    )

    source = tmp_path / "src"
    settings = source / ".cline" / "data" / "settings"
    settings.mkdir(parents=True)
    (settings / "providers.json").write_text('{"a":1}', encoding="utf-8")
    (settings / "cli-notices.json").write_text("{}", encoding="utf-8")
    (source / ".ssh").mkdir()
    (source / ".ssh" / "k").write_text("k", encoding="utf-8")
    run_home = tmp_path / "run" / "home"

    assert materialize_cline_run_home(source, run_home) is None
    copied = sorted(p.relative_to(run_home).as_posix() for p in run_home.rglob("*") if p.is_file())
    assert copied == sorted(p.as_posix() for p in CLINE_RUN_HOME_COPIED_FILES)
    assert oct((run_home / CLINE_RUN_HOME_COPIED_FILES[0]).stat().st_mode & 0o777) == "0o600"


def test_cline_seatbelt_denies_cline_workspace_customizations(tmp_path):
    from nexus.executors.agy_write_admission import build_seatbelt_profile

    target = tmp_path / "t"
    profile = build_seatbelt_profile(
        run_root=tmp_path / "r",
        writable_target=target,
        extra_protected_target_names=(".cline", ".clinerules"),
    )
    assert f'(subpath "{target}/.cline")' in profile
    assert f'(literal "{target}/.clinerules")' in profile


def test_cline_only_stop_finish_reason_is_delivery():
    from nexus.executors.worker_registry import cline_delivery_failure

    for reason in ("length", "max_iterations", "tool_calls", "weird", ""):
        event = ('{"type":"run_result","finishReason":"%s"}\n' % reason).encode()
        assert cline_delivery_failure(event, b"") == "cline_status_not_success", reason
    assert cline_delivery_failure(b'{"type":"run_result"}\n', b"") == "cline_status_not_success"
    assert cline_delivery_failure(_CLINE_OK, b"") is None


def test_cline_adapter_request_profile_denies_cline_customizations(monkeypatch, tmp_path):
    _cline_fake_home(tmp_path, monkeypatch)
    _, requests, _, target, _ = _cline_admitted_run(monkeypatch, tmp_path)

    profile = requests[0].seatbelt_profile
    real_target = target.resolve()
    for name in (".cline", ".clinerules"):
        assert f'(literal "{real_target}/{name}")' in profile
        assert f'(subpath "{real_target}/{name}")' in profile


@pytest.mark.parametrize(
    "reason",
    [
        "Tool approval requires an interactive session, but this session is non-interactive.",
        "Tool was not executed",
        "User rejected the tool call",
    ],
)
def test_cline_skip_reason_suffix_denial_is_non_delivery(reason):
    """#2332: every cline 3.0.69 skip reason ends with a fixed suffix; any of them
    on a tool ``content_end`` error is a denial even when the run ends ``stop``."""
    import json

    from nexus.executors.worker_registry import cline_delivery_failure

    skip = f"{reason} -- NOT a tool or system failure. Clarify with user before proceeding."
    event = {
        "type": "agent_event",
        "event": {
            "type": "content_end",
            "contentType": "tool",
            "toolName": "editor",
            "output": {"error": skip},
            "error": json.dumps({"error": skip}),
        },
    }
    stdout = (json.dumps(event) + "\n").encode() + _CLINE_OK
    assert cline_delivery_failure(stdout, b"") == "cline_permission_denied"


def test_cline_skip_suffix_in_tool_result_or_model_text_is_not_a_denial():
    """The suffix counts only in a tool's error fields, never in result/model text."""
    import json

    from nexus.executors.worker_registry import cline_delivery_failure

    suffix = "x -- NOT a tool or system failure. Clarify with user before proceeding."
    tool_result = {
        "type": "agent_event",
        "event": {
            "type": "content_end",
            "contentType": "tool",
            "toolName": "read_file",
            "output": {"result": suffix},
        },
    }
    text = {
        "type": "agent_event",
        "event": {"type": "content_end", "contentType": "text", "text": suffix},
    }
    stdout = (json.dumps(tool_result) + "\n" + json.dumps(text) + "\n").encode() + _CLINE_OK
    assert cline_delivery_failure(stdout, b"") is None


@pytest.mark.parametrize("field", ["event_error", "output_error", "error_object"])
def test_cline_skip_suffix_in_each_tool_error_field_is_a_denial(field):
    """#2335 review: each tool error field alone carries the denial."""
    import json

    from nexus.executors.worker_registry import cline_delivery_failure

    skip = "Tool was not executed -- NOT a tool or system failure. Clarify with user."
    event = {"type": "content_end", "contentType": "tool", "toolName": "editor"}
    if field == "event_error":
        event["error"] = skip
    elif field == "output_error":
        event["output"] = {"error": skip}
    else:
        event["error"] = {"message": skip}
    stdout = (json.dumps({"type": "agent_event", "event": event}) + "\n").encode() + _CLINE_OK
    assert cline_delivery_failure(stdout, b"") == "cline_permission_denied"


def test_cline_skip_suffix_on_stderr_is_a_denial():
    from nexus.executors.worker_registry import cline_delivery_failure

    stderr = b"Tool was not executed -- NOT a tool or system failure. Clarify with user.\n"
    assert cline_delivery_failure(_CLINE_OK, stderr) == "cline_permission_denied"


@pytest.mark.parametrize(
    "shape", ["error_object_error_key", "truncated_reason_event", "truncated_reason_output"]
)
def test_cline_structured_or_truncated_skip_reason_is_a_denial(shape):
    """#2335 Gemini r2: ``{"error": ...}`` objects and reasons cut before the suffix."""
    import json

    from nexus.executors.worker_registry import cline_delivery_failure

    event = {"type": "content_end", "contentType": "tool", "toolName": "editor"}
    if shape == "error_object_error_key":
        event["error"] = {"error": "User rejected the tool call -- NOT a tool or system failure."}
    elif shape == "truncated_reason_event":
        event["error"] = "Tool approval requires an interactive session, but this"
    else:
        event["output"] = {"error": "Tool was not executed"}
    stdout = (json.dumps({"type": "agent_event", "event": event}) + "\n").encode() + _CLINE_OK
    assert cline_delivery_failure(stdout, b"") == "cline_permission_denied"
