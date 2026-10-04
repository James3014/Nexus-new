"""Donor adapters for the independent runtime execution coordinator."""

from __future__ import annotations

import hashlib
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

    def host_preparation_required(self, contract, request):
        return self.service._ambient_core_required(contract, request)


class _Preparation:
    def __init__(self, service):
        self.service = service

    def prepare_before_worker(self, contract, request, lease, state, *, task_id, attempt_id):
        self.service._bridge_validate_claim(task_id, attempt_id, operation="HOST_PREPARATION")
        prep = self.service._prepare_ambient_core(
            contract,
            request,
            lease,
            state,
            task_id=task_id,
            attempt_id=attempt_id,
        )
        self.service._mutate_state(task_id, lambda s: s.update({"host_preparation": prep}))
        return prep

    def revalidate_before_worker(
        self,
        preparation,
        contract,
        request,
        lease,
        state,
        *,
        task_id,
        attempt_id,
        active_provider,
    ):
        return self.service._revalidate_ambient_core(
            preparation,
            contract,
            request,
            lease,
            state,
            task_id=task_id,
            attempt_id=attempt_id,
            active_provider=active_provider,
        )


class _Worker:
    def __init__(self, service):
        self.service = service

    def preflight(self, provider):
        return self.service.worker_registry.preflight(provider)

    def invoke(self, provider, contract, lease, **kwargs):
        task_id = getattr(contract, "task_id", None)
        state = {}
        attempt_id = ""
        trajectory_root = None
        trajectory_ref = None
        if task_id:
            state = self.service._read_state(task_id) or {}
            attempt_id = str(state.get("attempt_id") or "")
            self.service._bridge_validate_claim(task_id, attempt_id, operation="PROVIDER_INVOKE")
            request = state.get("request") or {}
            if self.service._ambient_core_required(contract, request) and not state.get(
                "host_preparation"
            ):
                prep = self.service._prepare_ambient_core(
                    contract, request, lease, state, task_id=task_id, attempt_id=attempt_id
                )
                self.service._mutate_state(task_id, lambda s: s.update({"host_preparation": prep}))

            # Passive Track-1 trajectory capture for the already-selected worker.
            # Correlation is derived from task/attempt/provider, so this sidecar
            # never mutates lifecycle state. Any telemetry failure is fail-open.
            try:
                from nexus.research.clm_system_one.research_evidence_root import (
                    explicit_research_evidence_root_configured,
                )

                if not explicit_research_evidence_root_configured():
                    raise RuntimeError("shared Track-1 evidence root is not configured")

                from nexus.research.clm_system_one.trajectory_continuity import (
                    bind_trajectory_step_result,
                    resolve_research_evidence_root,
                    seal_trajectory_step,
                    self_hosted_worker_trajectory_id,
                )

                repo_root = str(
                    getattr(contract, "controller_repo_root", "")
                    or getattr(contract, "target_repo_root", "")
                )
                source_revision = str(
                    getattr(contract, "target_base_revision", "")
                    or getattr(contract, "controller_revision", "")
                )
                trajectory_root = resolve_research_evidence_root(repo_root)
                prompt = str(kwargs.get("prompt") or "")
                envelope = state.get("canonical_dispatch_envelope")
                envelope = envelope if isinstance(envelope, Mapping) else {}
                selected_model = str(
                    kwargs.get("model")
                    or state.get("selected_model")
                    or envelope.get("model")
                    or ""
                )
                trajectory_id = self_hosted_worker_trajectory_id(
                    task_id=str(task_id),
                    attempt_id=attempt_id,
                    provider=str(provider),
                )
                trajectory_ref = seal_trajectory_step(
                    evidence_root=trajectory_root,
                    task_id=str(task_id),
                    trajectory_id=trajectory_id,
                    attempt_id=attempt_id,
                    candidate_id=None,
                    step_index=0,
                    source_revision=source_revision,
                    base_source_revision=source_revision,
                    pre_action_state={
                        "task_objective": str(getattr(contract, "objective", "") or ""),
                        "target_base_revision": source_revision,
                        "allowed_files": list(getattr(contract, "allowed_files", ()) or ()),
                        "verifier_command_sha256": [
                            hashlib.sha256(str(command).encode("utf-8")).hexdigest()
                            for command in (getattr(contract, "verifier_commands", ()) or ())
                        ],
                        "provider": str(provider),
                        "model": selected_model,
                    },
                    action_type="self_hosted_worker_invoke",
                    action_payload={
                        "provider": str(provider),
                        "model": selected_model,
                        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                        "prompt_chars": len(prompt),
                        "target_worktree_sha256": hashlib.sha256(
                            str(getattr(lease, "target_worktree", "")).encode("utf-8")
                        ).hexdigest(),
                    },
                )
            except Exception:
                trajectory_root = None
                trajectory_ref = None

        try:
            receipt = self.service.worker_registry.invoke(provider, contract, lease, **kwargs)
        except Exception as exc:
            if trajectory_root is not None and trajectory_ref is not None:
                try:
                    bind_trajectory_step_result(
                        evidence_root=trajectory_root,
                        step_ref=trajectory_ref,
                        action_result={
                            "response_type": "Exception",
                            "exception_type": type(exc).__name__,
                            "provider": str(provider),
                        },
                    )
                except Exception:
                    pass
            raise

        if trajectory_root is not None and trajectory_ref is not None:
            try:
                bind_trajectory_step_result(
                    evidence_root=trajectory_root,
                    step_ref=trajectory_ref,
                    action_result={
                        "provider": str(getattr(receipt, "provider", provider) or provider),
                        "worker_status": str(getattr(receipt, "worker_status", "") or ""),
                        "outcome": str(getattr(receipt, "outcome", "") or ""),
                        "exit_code": getattr(receipt, "exit_code", None),
                        "stdout_sha256": str(getattr(receipt, "stdout_sha256", "") or ""),
                        "stderr_sha256": str(getattr(receipt, "stderr_sha256", "") or ""),
                        "wall_time_ms": int(getattr(receipt, "wall_time_ms", 0) or 0),
                        "provider_calls": int(getattr(receipt, "provider_calls", 0) or 0),
                        "provider_attempt_count": int(
                            getattr(receipt, "provider_attempt_count", 0) or 0
                        ),
                        "evidence_complete": bool(getattr(receipt, "evidence_complete", False)),
                    },
                )
            except Exception:
                pass
        return receipt


class _Target:
    def __init__(self, service):
        self.service = service

    def initial_lease(self, contract, state):
        task_id = getattr(contract, "task_id", None) or (
            state.get("task_id") if isinstance(state, Mapping) else None
        )
        attempt_id = state.get("attempt_id") if isinstance(state, Mapping) else None
        if task_id:
            self.service._bridge_validate_claim(task_id, attempt_id, operation="TARGET_LEASE")
        manager = _service_module.WorktreeManager(root_dir=contract.target_worktree_root)
        controller = _service_module.SelfHostedDevelopmentController(worktree_manager=manager)
        prepare = controller.prepare_task
        if "task_states" in inspect.signature(prepare).parameters:
            return prepare(contract, task_states=self.service._workspace_task_states())
        return prepare(contract)

    def lease_from_state(self, state):
        return self.service._lease_from_state(state)

    def replace_failed_lease(self, contract, lease, state):
        task_id = getattr(contract, "task_id", None) or (
            state.get("task_id") if isinstance(state, Mapping) else None
        )
        attempt_id = state.get("attempt_id") if isinstance(state, Mapping) else None
        if task_id:
            self.service._bridge_validate_claim(
                task_id, attempt_id, operation="TARGET_REPLACE_LEASE"
            )
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
    def __init__(self, service, update=None, task_id=None, attempt_id=None):
        self.service, self.update = service, update
        self.task_id, self.attempt_id = task_id, attempt_id
        self.terminal_statuses = _service_module.TERMINAL_STATUSES

    def bound_custom_runner_values(self, values):
        return self.service._bound_custom_runner_values(values)

    def finalize_completed(self, contract, request, lease, state, attempts, *, execution, status):
        task_id = (
            self.task_id
            or getattr(contract, "task_id", None)
            or (state.get("task_id") if isinstance(state, Mapping) else None)
        )
        attempt_id = self.attempt_id or (
            state.get("attempt_id") if isinstance(state, Mapping) else None
        )
        update = self.update or (
            lambda status, values: self.service._checkpoint(
                task_id, status, values, attempt_id=attempt_id
            )
        )
        if task_id:
            self.service._bridge_validate_claim(task_id, attempt_id, operation="FINALIZE_COMPLETED")
        if self.service._ambient_core_required(contract, request) and not (
            state.get("host_preparation") if isinstance(state, Mapping) else None
        ):
            prep = self.service._prepare_ambient_core(
                contract, request, lease, state, task_id=task_id, attempt_id=attempt_id
            )
            self.service._mutate_state(task_id, lambda s: s.update({"host_preparation": prep}))
            state = self.service._read_state(task_id) or state
        return self.service._finalize_runtime_candidate(
            contract, request, lease, state, attempts, update, execution=execution, status=status
        )

    def finalize_failure(self, task_id, attempt_id, error):
        self.service._finalize_runtime_failure(task_id, attempt_id, error)


class _WorkerInvocationModelCallGate:
    """Observation-only binding for an already-selected worker invocation.

    The bridge is downstream of CapabilityPlanner/worker selection.  It therefore
    has no authority to reinterpret routing, provider/model choice, or fabricate
    bounded candidates.  Its only truthful verdict at this seam is to preserve
    the existing model path.
    """

    resolver_id = "nexus-new.worker-invocation-model-path.v1"

    def resolve_model_call_need(self, structured_state, *, seam):
        del structured_state
        return {
            "resolution": "MODEL_NEEDED",
            "reason": "worker_invocation_path_already_selected",
            "resolver_id": self.resolver_id,
            "seam": str(seam),
        }


class RuntimeCoordinationBridge:
    def __init__(self, service):
        self.service = service

    def _coordinator(self, task_id, attempt_id, *, request=None, update=None):
        processes = _Processes()
        processes.service = self.service
        finalization = _Finalization(
            self.service, update=update, task_id=task_id, attempt_id=attempt_id
        )
        args = [
            _State(self.service, request=request, update=update),
            _Contract(self.service),
            _Worker(self.service),
            _Target(self.service),
            processes,
            finalization,
        ]
        sig = inspect.signature(ExecutionCoordinator.__init__)
        has_var_positional = any(
            p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
        )
        if "preparation" in sig.parameters or len(sig.parameters) > 7 or has_var_positional:
            args.append(_Preparation(self.service))
        if "model_call_gate" in sig.parameters:
            return ExecutionCoordinator(
                *args,
                model_call_gate=_WorkerInvocationModelCallGate(),
            )
        return ExecutionCoordinator(*args)

    def _ensure_preparation_compat(self, task_id, attempt_id, *, request=None):
        sig = inspect.signature(ExecutionCoordinator.__init__)
        has_var_positional = any(
            p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
        )
        if "preparation" in sig.parameters or len(sig.parameters) > 7 or has_var_positional:
            return
        state = self.service._read_state(task_id) or {}
        req = request or state.get("request") or {}
        if not state.get("lease"):
            return
        try:
            contract = self.service._contract_from_state(state)
        except Exception:
            return
        if not self.service._ambient_core_required(contract, req):
            return
        if not state.get("host_preparation"):
            lease = self.service._lease_from_state(state)
            prep = self.service._prepare_ambient_core(
                contract, req, lease, state, task_id=task_id, attempt_id=attempt_id
            )
            self.service._mutate_state(task_id, lambda s: s.update({"host_preparation": prep}))

    def run_owned_attempt(self, task_id, attempt_id, custom_runner=None):
        self.service._bridge_validate_claim(task_id, attempt_id, operation="RUN_OWNED_ATTEMPT")
        self._ensure_preparation_compat(task_id, attempt_id)
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
        self.service._bridge_validate_claim(task_id, attempt_id, operation="EXECUTE")
        self._ensure_preparation_compat(task_id, attempt_id, request=request)
        return self._coordinator(
            task_id, attempt_id, request=request, update=update
        ).execute_attempt(task_id, attempt_id, contract=contract, request=request)
