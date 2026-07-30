from pathlib import Path

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


def test_registry_recognizes_all_governed_provider_names():
    registry = WorkerRegistry.default()

    assert registry.providers == (
        "codex",
        "gemini",
        "agy",
        "opencode",
        "mimo",
        "ollama",
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
    monkeypatch.setenv("NEXUS_AGY_PROJECT_ID", "project-123")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    adapter = AgyWorkerAdapter()

    preflight = adapter.preflight()

    assert preflight.provider == "agy"
    assert preflight.ready is False
    assert preflight.authorized is False
    assert preflight.implementation_status == "IMPLEMENTED"
    with pytest.raises(WorkerProviderUnavailable, match="NEXUS_EXTERNAL_RUNTIME_AUTHORIZED"):
        adapter.invoke(
            type("Contract", (), {"task_id": "agy-task"})(),
            type("Lease", (), {"target_worktree": str(tmp_path)})(),
            prompt="bounded",
        )


def test_agy_adapter_uses_isolated_project_without_project_id(monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_PROJECT_ID", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    adapter = AgyWorkerAdapter()

    preflight = adapter.preflight()

    assert preflight.ready is True
    assert preflight.executable_available is True
    assert preflight.reason == "ready"


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
            stdout=b"agy stdout",
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
    )

    assert captured["request"].cwd == str(target.resolve())
    assert captured["request"].argv == (
        "--new-project",
        "--add-dir",
        str(target.resolve()),
        "--dangerously-skip-permissions",
        "--mode",
        "accept-edits",
        "--model",
        "gemini-3.6-flash-medium",
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
    assert receipt.stdout_sha256 == CliWorkerResult.hash_bytes(b"agy stdout")
    assert receipt.stderr_sha256 == CliWorkerResult.hash_bytes(b"agy stderr")
    assert receipt.wall_time_ms == 25
    assert receipt.process_group_id == 777
    assert receipt.process_group_killed is False
    assert receipt.timed_out is False
    assert receipt.commit_created is False
    assert receipt.merge_performed is False
    assert receipt.push_performed is False
    assert receipt.evidence_complete is True


def test_codex_adapter_normalizes_provider_receipt_to_common_contract(tmp_path):
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
            stdout=b"{}",
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
    agy_receipt = agy_adapter.invoke(contract, lease, prompt="test")
    assert agy_receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert agy_receipt.evidence_complete is True


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

    candidate = SimpleNamespace(changed_files=["file.py"], untracked_files=[], deleted_files=[], candidate_state_hash="hash")
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
            stdout=b"ok",
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
            stdout=b"ok",
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
            stdout=b"success",
            stderr=b"",
            wall_time_ms=15,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-quota"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
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
            stdout=b"ok",
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-3calls"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
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
            stdout=b"ok",
            stderr=b"",
            wall_time_ms=5,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(account_pool=pool)
    receipt = adapter.invoke(
        type("Contract", (), {"task_id": "task-auth"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
    )
    assert receipt.provider_calls == 2
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value


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
        type("Contract", (), {"task_id": "task-no-overcount"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
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
        type("Contract", (), {"task_id": "task-fail-rotate"})(),
        type("Lease", (), {"target_worktree": str(tmp_path)})(),
        prompt="hello",
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
            stdout=b"ok",
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
            stdout=b"ok",
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
    )
    assert receipt.account_alias_hash == acc.alias_hash
    assert "user@example.com" not in str(receipt)
    assert "secret_identity" not in str(receipt)


def test_no_unified_runtime_changes():
    from pathlib import Path
    unified_runtime_path = Path("nexus/orchestrator/unified_runtime.py")
    if unified_runtime_path.exists():
        import subprocess
        diff = subprocess.run(["git", "diff", "--name-only", str(unified_runtime_path)], capture_output=True, text=True)
        assert diff.stdout.strip() == "", "nexus/orchestrator/unified_runtime.py must not be modified"
