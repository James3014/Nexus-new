from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.worker_registry import GrokWorkerAdapter, WorkerRegistry
from nexus.services.external_account_pool import AccountFailureKind
from nexus.services.grok_account_pool import GrokAccount, GrokAccountPoolManager


def _contract(tmp_path: Path, calls: int = 2):
    return SimpleNamespace(task_id="task-grok", target_worktree=str(tmp_path), maximum_provider_calls=calls)


def _lease(tmp_path: Path):
    return SimpleNamespace(target_worktree=str(tmp_path))


def _result(request, *, stderr: bytes = b"", exit_code: int = 0):
    return CliWorkerResult(
        status=CliWorkerStatus.COMPLETED,
        executable_identity=request.executable,
        argv=request.argv,
        cwd=request.cwd,
        exit_code=exit_code,
        stdout=b"ok" if exit_code == 0 else b"",
        stderr=stderr,
        wall_time_ms=1,
        process_group_id=None,
    )


def _pool(tmp_path: Path) -> GrokAccountPoolManager:
    return GrokAccountPoolManager([
        GrokAccount("alpha", str(tmp_path / "alpha")),
        GrokAccount("beta", str(tmp_path / "beta")),
    ])


def test_default_registry_uses_grok_pool_adapter_without_changing_other_providers():
    registry = WorkerRegistry.default()
    assert isinstance(registry.adapter("grok"), GrokWorkerAdapter)
    assert registry.adapter("gemini").provider == "gemini"


def test_grok_adapter_rotates_only_eligible_failure_and_keeps_nonsecret_lineage(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    pool = _pool(tmp_path)
    adapter = GrokWorkerAdapter(executable=sys.executable, account_pool=pool)
    calls = []

    def fake_run(request, on_process_group=None):
        calls.append(request)
        if len(calls) == 1:
            return _result(request, stderr=b"quota exhausted", exit_code=1)
        return _result(request)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_run)
    receipt = adapter.invoke(_contract(tmp_path), _lease(tmp_path), prompt="bounded")

    assert receipt.outcome == "EXECUTION_COMPLETED"
    assert receipt.provider_attempt_count == 2
    assert receipt.provider_calls == 2
    assert receipt.account_alias_hash == pool._accounts[1].alias_hash
    assert calls[0].env["HOME"] != calls[1].env["HOME"]
    assert "alpha" not in calls[0].env["HOME"]
    assert "beta" not in calls[1].env["HOME"]
    assert all(key not in calls[0].env for key in ("XAI_API_KEY", "GROK_API_KEY", "NEXUS_GROK_API_KEY"))


def test_grok_adapter_does_not_rotate_non_account_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    pool = _pool(tmp_path)
    adapter = GrokWorkerAdapter(executable=sys.executable, account_pool=pool)
    calls = []

    def fake_run(request, on_process_group=None):
        calls.append(request)
        return _result(request, stderr=b"syntax error", exit_code=2)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_run)
    receipt = adapter.invoke(_contract(tmp_path), _lease(tmp_path), prompt="bounded")

    assert receipt.outcome == "FAILED"
    assert receipt.provider_attempt_count == 1
    assert receipt.account_alias_hash == pool._accounts[0].alias_hash
    assert len(calls) == 1
    assert pool._accounts[0].is_active is True


@pytest.mark.parametrize("stderr", [b"401 unauthorized", b"quota exhausted", b"429 rate limit"])
def test_grok_adapter_rotates_auth_quota_and_rate_limit_failures(tmp_path, monkeypatch, stderr):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    pool = _pool(tmp_path)
    adapter = GrokWorkerAdapter(executable=sys.executable, account_pool=pool)
    calls = []

    def fake_run(request, on_process_group=None):
        calls.append(request)
        return _result(request, stderr=stderr, exit_code=1) if len(calls) == 1 else _result(request)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_run)
    receipt = adapter.invoke(_contract(tmp_path), _lease(tmp_path), prompt="bounded")

    assert receipt.outcome == "EXECUTION_COMPLETED"
    assert receipt.provider_attempt_count == 2
    assert calls[0].env["HOME"] != calls[1].env["HOME"]


def test_grok_adapter_reports_exhaustion_without_leaking_pool_error(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    pool = GrokAccountPoolManager([GrokAccount("only", str(tmp_path / "only"))])
    adapter = GrokWorkerAdapter(executable=sys.executable, account_pool=pool)

    def fake_run(request, on_process_group=None):
        return _result(request, stderr=b"quota exhausted", exit_code=1)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_run)
    receipt = adapter.invoke(_contract(tmp_path), _lease(tmp_path), prompt="bounded")

    assert receipt.outcome == "FAILED"
    assert receipt.provider_attempt_count == 1
    assert receipt.failure_reason == "grok account rotation unavailable"
    assert "only" not in receipt.failure_reason


def test_grok_without_pool_keeps_direct_cli_behavior(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    adapter = GrokWorkerAdapter(executable=sys.executable, account_pool=None)
    calls = []

    def fake_run(request, on_process_group=None):
        calls.append(request)
        return _result(request)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_run)
    receipt = adapter.invoke(_contract(tmp_path), _lease(tmp_path), prompt="bounded")

    assert receipt.outcome == "EXECUTION_COMPLETED"
    assert receipt.provider_attempt_count is None
    assert receipt.account_alias_hash is None
    assert len(calls) == 1
