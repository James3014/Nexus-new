from dataclasses import replace
from pathlib import Path

import pytest

from nexus.executors.codex_executor import CodexExecutionReceipt
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerOutcome,
    WorkerProviderUnavailable,
)
from nexus.executors.worker_registry import CodexWorkerAdapter, WorkerRegistry


def test_registry_recognizes_all_governed_provider_names():
    registry = WorkerRegistry.default()

    assert registry.providers == (
        "codex",
        "gemini",
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
