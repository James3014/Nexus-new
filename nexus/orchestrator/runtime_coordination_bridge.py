"""Donor adapters for the independent runtime execution coordinator."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Mapping

from nexus_runtime.execution_coordination import ExecutionCoordinator
from .self_hosted_task_service import (
    CandidateVerifier,
    SelfHostedDevelopmentController,
    WorktreeManager,
    _task_deadline,
    _tracked_dispatch_required,
    _utc_now,
    validate_workforce_dispatch_binding,
    resolve_attempt,
    CandidateCommitter,
    check_fast_lane_eligible,
)
from . import self_hosted_task_service as _service_module
import inspect


class _State:
    def __init__(self, service, request=None, update=None): self.service, self.request, self.update = service, request, update
    def read_snapshot(self, task_id):
        state = self.service._read_state(task_id)
        if state is not None and self.request is not None and not isinstance(state.get("request"), Mapping):
            state = {**state, "request": self.request}
        return state
    def checkpoint(self, task_id, status, values, attempt_id):
        if self.update is not None:
            self.update(status, dict(values))
            return self.read_snapshot(task_id) or {}
        return self.service._checkpoint(task_id, status, dict(values), attempt_id=attempt_id)
    def heartbeat(self, task_id, attempt_id): self.service._mutate_state(task_id, lambda state: self.service._touch_owned_state(state, attempt_id))
    def set_child_process_group(self, task_id, attempt_id, pgid): self.service._set_child_pgid(task_id, attempt_id, pgid)


class _Contract:
    def __init__(self, service): self.service = service
    def build_contract(self, request): return self.service.build_contract(request)
    def prompt(self, contract): return self.service._prompt(contract)
    def deadline(self, contract, submitted_at): return _task_deadline(contract, submitted_at)
    def fast_lane_eligible(self, contract, request): return check_fast_lane_eligible(contract, request)
    def provider_order(self, contract): return tuple(contract.provider_order or [contract.preferred_provider])
    def provider_binding(self, request, state): return validate_workforce_dispatch_binding(request, require_binding=_tracked_dispatch_required(request, state))
    def revalidate_provider_boundary(self, contract, request, task_id, binding, active_provider): self.service._revalidate_provider_boundary(contract, request, task_id, binding, active_provider=active_provider)
    def receipt_from_state(self, value): return self.service._receipt_from_state(value)
    def validate_static_contract(self, contract, target_worktree):
        validator = getattr(_service_module.CandidateVerifier, "validate_static_contract", None)
        if validator is not None: validator(contract, target_worktree)
    def with_provider_call_budget(self, contract, remaining_calls):
        return contract.model_copy(update={"maximum_provider_calls": remaining_calls}) if hasattr(contract, "model_copy") else contract


class _Worker:
    def __init__(self, service): self.service = service
    def preflight(self, provider): return self.service.worker_registry.preflight(provider)
    def invoke(self, provider, contract, lease, **kwargs): return self.service.worker_registry.invoke(provider, contract, lease, **kwargs)


class _Target:
    def __init__(self, service): self.service = service
    def initial_lease(self, contract, state):
        manager = _service_module.WorktreeManager(root_dir=contract.target_worktree_root)
        controller = _service_module.SelfHostedDevelopmentController(worktree_manager=manager)
        prepare = controller.prepare_task
        if "task_states" in inspect.signature(prepare).parameters:
            return prepare(contract, task_states=self.service._workspace_task_states())
        return prepare(contract)
    def lease_from_state(self, state): return self.service._lease_from_state(state)
    def replace_failed_lease(self, contract, lease, state):
        manager = _service_module.WorktreeManager(root_dir=contract.target_worktree_root)
        controller = _service_module.SelfHostedDevelopmentController(worktree_manager=manager)
        return self.service._replace_failed_target(manager, controller, contract, lease, task_states=self.service._workspace_task_states())


class _Processes:
    def create_thread(self, target, args): return threading.Thread(target=target, args=args, daemon=True)
    def start_thread(self, thread): thread.start()
    def start_process(self, command, *, cwd, env):
        process = subprocess.Popen(command, cwd=cwd, env=dict(env), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        process.pgid = os.getpgid(process.pid)
        return process
    def wait_for_owner(self, task_id, attempt_id, pid): return self.service._wait_for_owner(task_id, attempt_id, pid)
    def terminate_owned_processes(self, task_id, exclude_pid): return self.service._terminate_owned_processes(task_id, exclude_pid=exclude_pid)
    def pid_alive(self, pid): return self.service._pid_alive(pid)
    def utc_now(self): return _utc_now()


class _Finalization:
    def __init__(self, service, update=None): self.service, self.update = service, update
    def _update(self, status, values):
        if self.update is not None: self.update(status, values)
        else: self.service._checkpoint(self.task_id, status, values, attempt_id=self.attempt_id)
    def finalize_completed(self, contract, request, lease, state, attempts):
        service = self.service
        task_id = contract.task_id
        manager = _service_module.WorktreeManager(root_dir=contract.target_worktree_root)
        controller = _service_module.SelfHostedDevelopmentController(worktree_manager=manager)
        candidate = controller.collect_candidate(contract, lease)
        self._update("CANDIDATE_CAPTURED", {"candidate": candidate})
        verified = _service_module.CandidateVerifier(manager).verify(contract, lease, candidate, protected_paths=request.get("protected_paths") or {})
        resolution = resolve_attempt(attempts[-1], candidate, verified)
        self._update("VERIFIED", {"verified_receipt": verified, "attempt_resolution": resolution})
        if resolution.verdict != "PROVEN":
            reasons = ", ".join(resolution.failure_reasons) or f"verdict is {resolution.verdict}"
            raise RuntimeError(f"candidate verification failed: {reasons}")
        authority_error = service._promotion_authority_error(contract=contract, request=request)
        if authority_error:
            cleanup = manager.cleanup_terminal_target(contract, lease)
            terminal = "REHEARSAL_VERIFIED" if service.ephemeral and cleanup.decision in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"} else "FINAL_BLOCK"
            values = {"error": authority_error, "candidate_status": terminal, "promotion_status": "NOT_CREATED", "verification_verdict": "PROVEN" if terminal == "REHEARSAL_VERIFIED" else "FAILED", "verified_receipt": verified, "attempt_resolution": resolution, "cleanup_decision": cleanup.decision, "cleanup_blocker": cleanup.blocker, "cleanup_performed": cleanup.performed, "terminal_status": terminal, "state_retention_status": "TERMINAL", "archive_eligible": False}
            self._update(terminal, values)
            return values
        packet = _service_module.CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
        values = {"execution": attempts[-1], "candidate": candidate, "verified_receipt": verified, "attempt_resolution": resolution, "promotion_packet": packet, "promotion_status": packet.promotion_status, "candidate_commit_created": packet.candidate_commit_created, "public_claim_allowed": packet.public_claim_allowed, "production_ready": packet.production_ready, "merge_performed": packet.merge_performed, "push_performed": packet.push_performed}
        self._update("CANDIDATE_COMMITTED", values)
        candidate_ref = manager.protect_candidate(contract, lease, packet.candidate_commit_sha)
        self._update("CANDIDATE_REF_PROTECTED", {"candidate_ref": candidate_ref})
        cleanup = manager.cleanup_terminal_target(contract, lease, candidate_commit=packet.candidate_commit_sha, candidate_ref=candidate_ref)
        if cleanup.decision != "REMOVED": raise RuntimeError(f"candidate Target cleanup failed: {cleanup.decision}")
        self._update("TARGET_CLEANED", {"cleanup_eligible": cleanup.eligible, "cleanup_decision": cleanup.decision, "cleanup_blocker": cleanup.blocker, "cleanup_performed": cleanup.performed, "candidate_ref": candidate_ref})
        return {**values, "candidate_ref": candidate_ref, "candidate_status": "PENDING_HUMAN_APPROVAL", "cleanup_decision": cleanup.decision, "cleanup_performed": cleanup.performed, "terminal_status": "PENDING_HUMAN_APPROVAL", "state_retention_status": "ACTIVE", "archive_eligible": False}
    def finalize_failure(self, task_id, attempt_id, error): self.service._record_direct_failure(task_id, "WORKER_EXECUTION_FAILED", str(error))


class RuntimeCoordinationBridge:
    def __init__(self, service):
        self.service = service
        self._processes = _Processes()
        self._processes.service = service
        self._finalization = None

    def run_owned_attempt(self, task_id, attempt_id, custom_runner=None):
        return self.coordinator.run_owned_attempt(task_id, attempt_id, custom_runner)

    def launch(self, task_id, attempt_id, *, custom_runner, state_dir, source_root):
        return self.coordinator.launch(task_id, attempt_id, state_dir=state_dir, custom_runner=custom_runner, source_root=source_root)

    def execute(self, task_id, attempt_id, *, contract=None, request=None, update=None):
        state = _State(self.service, request=request, update=update)
        self._finalization = _Finalization(self.service, update=update)
        self._finalization.task_id, self._finalization.attempt_id = task_id, attempt_id
        self.coordinator = ExecutionCoordinator(state, _Contract(self.service), _Worker(self.service), _Target(self.service), self._processes, self._finalization)
        return self.coordinator.execute_attempt(task_id, attempt_id)
