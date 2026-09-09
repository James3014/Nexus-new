"""Witnesses through the actual compatibility service entrypoints; no providers."""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator import runtime_coordination_bridge as bridge
from tests.nexus.orchestrator.test_self_hosted_task_service import (
    _request,
    _setup_lc2_task,
    _m3c_receipt,
)


def seed(service, request):
    service._write_state(
        request["task_id"],
        {
            "task_id": request["task_id"],
            "request": request,
            "status": "SUBMITTED",
            "attempt_id": "attempt",
            "worker_pid": None,
            "status_history": [],
        },
    )


def test_actual_launch_thread_registers_before_run_and_returns_fresh_state(tmp_path, monkeypatch):
    seen = []

    def runner(contract, request, update):
        state = service._read_state(contract.task_id)
        assert state["worker_pid"] == os.getpid()
        assert contract.task_id in service._threads
        seen.append(state["status"])
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "public_claim_allowed": True}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, ephemeral=True, auto_reconcile=False
    )
    request = _request(tmp_path)
    seed(service, request)

    def start_and_join(_port, thread):
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()

    monkeypatch.setattr(bridge._Processes, "start_thread", start_and_join)
    state = service._launch_worker(request["task_id"], "attempt")
    assert seen == ["SUBMITTED"]
    assert state["status"] == "PENDING_HUMAN_APPROVAL"
    assert state["public_claim_allowed"] is False
    assert [entry["status"] for entry in state["status_history"]] == ["PENDING_HUMAN_APPROVAL"]


def test_actual_launch_process_metadata_does_not_checkpoint(tmp_path, monkeypatch):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False
    )
    request = _request(tmp_path)
    seed(service, request)
    real_popen = subprocess.Popen
    launched = []

    def deterministic_process(command, **kwargs):
        assert command[1:3] == ["-m", "nexus.orchestrator.self_hosted_task_worker"]
        assert kwargs["start_new_session"] is True
        process = real_popen([sys.executable, "-c", "import time; time.sleep(15)"], **kwargs)
        launched.append(process)
        return process

    monkeypatch.setattr(bridge.subprocess, "Popen", deterministic_process)
    monkeypatch.setattr(
        service,
        "_checkpoint",
        lambda *a, **kw: pytest.fail("launch metadata must not emit a status checkpoint"),
    )
    try:
        state = service._launch_worker(request["task_id"], "attempt")
        assert state["worker_pid"] == launched[0].pid
        assert state["worker_pgid"] == os.getpgid(launched[0].pid)
        assert state["status"] == "SUBMITTED" and state["status_history"] == []
        assert (
            service._launch_worker(request["task_id"], "attempt")["worker_pid"] == launched[0].pid
        )
        assert len(launched) == 1
        assert service._launch_worker(request["task_id"], "wrong")["worker_pid"] == launched[0].pid
    finally:
        for process in launched:
            process.terminate()
            process.wait(timeout=5)


@pytest.mark.parametrize(
    "status",
    [
        "WORKER_COMPLETED",
        "CANDIDATE_CAPTURED",
        "VERIFIED",
        "CANDIDATE_COMMITTED",
        "CANDIDATE_REF_PROTECTED",
    ],
)
def test_actual_resumable_status_preserves_candidate_callback_without_provider(
    tmp_path, monkeypatch, status
):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False
    )
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, "resume-status")
    state = service._read_state(contract.task_id)
    receipt = _m3c_receipt(contract.task_id, lease.target_worktree)
    state.update(status=status, execution=receipt.__dict__, executions=[receipt.__dict__])
    service._write_state(contract.task_id, state)
    monkeypatch.setattr(
        service.worker_registry,
        "invoke",
        lambda *a, **kw: pytest.fail("resume must not replay provider"),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CandidateVerifier",
        SimpleNamespace(validate_static_contract=lambda *_: None),
    )
    seen = []

    def finalize(contract, request, lease, state, attempts, update, **kwargs):
        seen.append(state["status"])
        return {"resumed": state["status"]}

    monkeypatch.setattr(service, "_finalize_runtime_candidate", finalize)
    result = service._run_default_resumable(
        contract, state["request"], lambda *_: None, task_id=contract.task_id, attempt_id=attempt_id
    )
    assert result == {"resumed": status}
    assert seen == [status]


def test_actual_target_leased_resume_denies_without_provider(tmp_path, monkeypatch):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False
    )
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, "resume-denial")
    state = service._read_state(contract.task_id)
    state["status"] = "TARGET_LEASED"
    service._write_state(contract.task_id, state)
    monkeypatch.setattr(
        service.worker_registry, "invoke", lambda *a, **kw: pytest.fail("must not invoke")
    )
    with pytest.raises(RuntimeError, match="worker lost before execution receipt"):
        service._run_default_resumable(
            contract,
            state["request"],
            lambda *_: None,
            task_id=contract.task_id,
            attempt_id=attempt_id,
        )


def test_actual_resumable_negative_receipt_budget_fails_closed(tmp_path, monkeypatch):
    from dataclasses import replace

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False
    )
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, "negative-budget")
    state = service._read_state(contract.task_id)
    state.update(status="WORKER_RUNNING", active_provider="codex", executions=[])
    service._write_state(contract.task_id, state)
    receipt = replace(_m3c_receipt(contract.task_id, lease.target_worktree), provider_calls=-1)
    calls = []

    def invoke(*args, **kwargs):
        calls.append(args[0])
        return receipt

    monkeypatch.setattr(service.worker_registry, "invoke", invoke)
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CandidateVerifier",
        SimpleNamespace(validate_static_contract=lambda *_: None),
    )
    with pytest.raises(RuntimeError, match="aggregate call budget"):
        service._run_default_resumable(
            contract,
            state["request"],
            lambda *_: None,
            task_id=contract.task_id,
            attempt_id=attempt_id,
        )
    assert calls == ["codex"]
    assert service._read_state(contract.task_id)["status"] == "WORKER_RUNNING"
