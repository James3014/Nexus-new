"""Donor adapters for the independent runtime execution coordinator."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
import threading
from typing import Mapping

from nexus_runtime.execution_coordination import ExecutionCoordinator

from . import self_hosted_task_service as _service_module
from .self_hosted_task_service import (
    _task_deadline,
    _tracked_dispatch_required,
    _utc_now,
    check_fast_lane_eligible,
    validate_workforce_dispatch_binding,
)


class _State:
    def __init__(self, service, request=None, update=None):
        self.service, self.request, self.update = service, request, update

    def read_snapshot(self, task_id):
        state = self.service._read_state(task_id)
        if (
            state is not None
            and self.request is not None
            and not isinstance(state.get("request"), Mapping)
        ):
            state = {**state, "request": self.request}
        return state

    def checkpoint(self, task_id, status, values, attempt_id):
        if self.update is not None:
            self.update(status, dict(values))
            return self.read_snapshot(task_id) or {}
        return self.service._checkpoint(task_id, status, dict(values), attempt_id=attempt_id)

    def mutate_metadata(self, task_id, values):
        return self.service._mutate_state(task_id, lambda state: state.update(values))

    def heartbeat(self, task_id, attempt_id):
        self.service._mutate_state(
            task_id, lambda state: self.service._touch_owned_state(state, attempt_id)
        )

    def set_child_process_group(self, task_id, attempt_id, pgid):
        self.service._set_child_pgid(task_id, attempt_id, pgid)


class _Contract:
    def __init__(self, service):
        self.service = service

    def assert_persisted_dispatch(self, *args, **kwargs):
        return self.service._assert_persisted_workforce_dispatch(*args, **kwargs)

    def revalidate_task_card(self, *args, **kwargs):
        return self.service._revalidate_tracked_dispatch_task_card(*args, **kwargs)

    def build_contract(self, request):
        return self.service.build_contract(request)

    def prompt(self, contract):
        return self.service._prompt(contract)

    def deadline(self, contract, submitted_at):
        return _task_deadline(contract, submitted_at)

    def fast_lane_eligible(self, contract, request):
        return check_fast_lane_eligible(contract, request)

    def escalation_order(self, contract):
        return tuple(
            contract.provider_order or (contract.preferred_provider, contract.fallback_provider)
        )

    def provider_order(self, contract):
        return tuple(contract.provider_order or [contract.preferred_provider])

    def provider_binding(self, request, state):
        return validate_workforce_dispatch_binding(
            request, require_binding=_tracked_dispatch_required(request, state)
        )

    def revalidate_provider_boundary(self, contract, request, task_id, binding, active_provider):
        self.service._revalidate_provider_boundary(
            contract, request, task_id, binding, active_provider=active_provider
        )

    def receipt_from_state(self, value):
        return self.service._receipt_from_state(value)

    def validate_static_contract(self, contract, target_worktree):
        validator = getattr(_service_module.CandidateVerifier, "validate_static_contract", None)
        if validator is not None:
            validator(contract, target_worktree)

    def with_provider_call_budget(self, contract, remaining_calls):
        return (
            contract.model_copy(update={"maximum_provider_calls": remaining_calls})
            if hasattr(contract, "model_copy")
            else contract
        )

    def materialize_worker_context(self, **kwargs):
        return self.service._worker_context_materialization(**kwargs)


class _Worker:
    def __init__(self, service):
        self.service = service

    def preflight(self, provider):
        return self.service.worker_registry.preflight(provider)

    def invoke(self, provider, contract, lease, **kwargs):
        return self.service.worker_registry.invoke(provider, contract, lease, **kwargs)


class _Target:
    def __init__(self, service):
        self.service = service

    def initial_lease(self, contract, state):
        manager = _service_module.WorktreeManager(root_dir=contract.target_worktree_root)
        controller = _service_module.SelfHostedDevelopmentController(worktree_manager=manager)
        prepare = controller.prepare_task
        if "task_states" in inspect.signature(prepare).parameters:
            return prepare(contract, task_states=self.service._workspace_task_states())
        return prepare(contract)

    def lease_from_state(self, state):
        return self.service._lease_from_state(state)

    def replace_failed_lease(self, contract, lease, state):
        manager = _service_module.WorktreeManager(root_dir=contract.target_worktree_root)
        controller = _service_module.SelfHostedDevelopmentController(worktree_manager=manager)
        return self.service._replace_failed_target(
            manager, controller, contract, lease, task_states=self.service._workspace_task_states()
        )


class _Processes:
    def worker_command(self, state_dir, task_id, attempt_id):
        return [
            sys.executable,
            "-m",
            "nexus.orchestrator.self_hosted_task_worker",
            "--state-dir",
            state_dir,
            "--task-id",
            task_id,
            "--attempt-id",
            attempt_id,
        ]

    def register_thread(self, task_id, thread):
        self.service._threads[task_id] = thread

    def create_thread(self, target, args):
        return threading.Thread(target=target, args=args, daemon=True)

    def start_thread(self, thread):
        thread.start()

    def start_process(self, command, *, cwd, env):
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        process.pgid = os.getpgid(process.pid)
        return process

    def wait_for_owner(self, task_id, attempt_id, pid):
        return self.service._wait_for_owner(task_id, attempt_id, pid)

    def terminate_owned_processes(self, task_id, exclude_pid):
        return self.service._terminate_owned_processes(task_id, exclude_pid=exclude_pid)

    def pid_alive(self, pid):
        return self.service._pid_alive(pid)

    def utc_now(self):
        return _utc_now()


class _Finalization:
    def __init__(self, service, update=None):
        self.service, self.update = service, update
        self.terminal_statuses = _service_module.TERMINAL_STATUSES

    def bound_custom_runner_values(self, values):
        return self.service._bound_custom_runner_values(values)

    def finalize_completed(self, contract, request, lease, state, attempts, *, execution, status):
        update = self.update or (
            lambda status, values: self.service._checkpoint(
                self.task_id, status, values, attempt_id=self.attempt_id
            )
        )
        return self.service._finalize_runtime_candidate(
            contract, request, lease, state, attempts, update, execution=execution, status=status
        )

    def finalize_failure(self, task_id, attempt_id, error):
        self.service._finalize_runtime_failure(task_id, attempt_id, error)


class RuntimeCoordinationBridge:
    def __init__(self, service):
        self.service = service

    def _coordinator(self, task_id, attempt_id, *, request=None, update=None):
        processes = _Processes()
        processes.service = self.service
        finalization = _Finalization(self.service, update=update)
        finalization.task_id, finalization.attempt_id = task_id, attempt_id
        return ExecutionCoordinator(
            _State(self.service, request=request, update=update),
            _Contract(self.service),
            _Worker(self.service),
            _Target(self.service),
            processes,
            finalization,
        )

    def run_owned_attempt(self, task_id, attempt_id, custom_runner=None):
        return self._coordinator(task_id, attempt_id).run_owned_attempt(
            task_id, attempt_id, custom_runner
        )

    def launch(self, task_id, attempt_id, *, custom_runner, state_dir, source_root):
        return self._coordinator(task_id, attempt_id).launch(
            task_id,
            attempt_id,
            state_dir=state_dir,
            custom_runner=custom_runner,
            source_root=source_root,
        )

    def execute(self, task_id, attempt_id, *, contract=None, request=None, update=None):
        return self._coordinator(
            task_id, attempt_id, request=request, update=update
        ).execute_attempt(task_id, attempt_id, contract=contract, request=request)
