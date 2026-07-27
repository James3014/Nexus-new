from dataclasses import replace
from pathlib import Path

import pytest

from nexus.executors.codex_executor import CodexExecutionReceipt
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerOutcome,
    WorkerProviderUnavailable,
)
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.worker_registry import AgyWorkerAdapter, CodexWorkerAdapter, OllamaPatchWorkerAdapter, WorkerRegistry


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


def test_agy_adapter_requires_project_id(monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_PROJECT_ID", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    adapter = AgyWorkerAdapter()

    preflight = adapter.preflight()

    assert preflight.ready is False
    assert preflight.executable_available is True
    assert preflight.reason == "NEXUS_AGY_PROJECT_ID is required"


def test_agy_adapter_requires_executable(monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.setenv("NEXUS_AGY_PROJECT_ID", "project-123")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: None)
    adapter = AgyWorkerAdapter()

    preflight = adapter.preflight()

    assert preflight.ready is False
    assert preflight.executable_available is False
    assert preflight.reason.endswith("executable not found: " + str(Path.home() / ".local/bin/agy"))


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
        "--project",
        "project-123",
        "--add-dir",
        str(target.resolve()),
        "--dangerously-skip-permissions",
        "--mode",
        "accept-edits",
        "--model",
        "gemini-3.6-flash-medium",
        "--print-timeout",
        "42",
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
    assert receipt.outcome == WorkerOutcome.PROVEN.value
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
    assert receipt.outcome == WorkerOutcome.PROVEN.value
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

    assert receipt.outcome == "PROVEN"
    assert receipt.evidence_complete is True
    assert (target / "file.txt").read_text() == "after\n"
