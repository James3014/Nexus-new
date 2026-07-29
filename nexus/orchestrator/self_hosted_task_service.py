"""Durable, restartable service facade for the self-hosted MCP surface."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence
from uuid import uuid4

from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    AttemptResolutionVerdict,
    WorkerExecutionReceipt,
    WorkerOutcome,
    resolve_attempt,
)
from nexus.executors.worker_registry import WorkerRegistry
from nexus.orchestrator.candidate_commit import CandidateCommitter
from nexus.orchestrator.candidate_verifier import CandidateVerifier
from nexus.orchestrator.governed_integration import ControlledIntegrationManager
from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
from nexus.orchestrator.task_contract import (
    AcceptanceProfile,
    ArchitectTaskContract,
    ArchitectureDecision,
    DevelopmentGoal,
    HumanApprovalPolicy,
    MutationMode,
)
from nexus.orchestrator.worker_escalation import WorkerEscalationPolicy
from nexus.orchestrator.worktree_manager import TargetWorktreeLease, WorktreeManager

Runner = Callable[[ArchitectTaskContract, Mapping[str, Any], Callable[[str, dict[str, Any]], None]], dict[str, Any]]
TERMINAL_STATUSES = frozenset({
    "FINAL_BLOCK", "RETAINED_FOR_REVIEW", "REJECTED", "SUPERSEDED",
    "INTEGRATED", "INTEGRATION_FAILED", "CANCELLED",
})
PENDING_CANDIDATE_STATUSES = frozenset({
    "PENDING_HUMAN_APPROVAL", "APPROVED", "APPROVAL_INVALIDATED", "INTEGRATING",
})
RESUMABLE_STATUSES = frozenset({
    "WORKER_COMPLETED",
    "WORKER_ESCALATING",
    "CANDIDATE_CAPTURED",
    "VERIFIED",
})


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


class SelfHostedTaskService:
    @staticmethod
    def canonical_state_dir() -> Path:
        configured = os.getenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        source_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=source_root, capture_output=True, text=True,
        )
        if result.returncode == 0:
            repository_root = Path(result.stdout.strip()).resolve().parent
            return repository_root.parent / f"{repository_root.name}-self-hosted-state"
        return (source_root / ".nexus/self_hosted_tasks").resolve()

    def __init__(
        self,
        state_dir: str | Path | None = None,
        runner: Optional[Runner] = None,
        *,
        stale_after_seconds: float = 30.0,
        auto_reconcile: bool = True,
        worker_registry: Optional[WorkerRegistry] = None,
        ephemeral: bool = False,
    ):
        canonical = self.canonical_state_dir()
        self.state_dir = Path(state_dir).expanduser().resolve() if state_dir is not None else canonical
        temporary_roots = (Path("/tmp"), Path("/private/tmp"), Path("/private/var/folders"))
        is_temporary = any(root == self.state_dir or root in self.state_dir.parents for root in temporary_roots)
        if self.state_dir != canonical and not ephemeral and not is_temporary:
            raise ValueError(f"production tasks must use canonical state root: {canonical}")
        self.ephemeral = ephemeral or is_temporary
        self._custom_runner = runner
        self.runner = runner or self._run_default
        self.stale_after_seconds = stale_after_seconds
        self.worker_registry = worker_registry or WorkerRegistry.default()
        self._threads: dict[str, threading.Thread] = {}
        if auto_reconcile:
            self.reconcile_tasks()

    def _state_path(self, task_id: str) -> Path:
        return self.state_dir / f"{task_id}.json"

    def _archive_root(self) -> Path:
        return self.state_dir.parent / "nexus-state-archive"

    def _archive_state_path(self, task_id: str) -> Path:
        return self._archive_root() / f"{task_id}.json"

    def _archive_state_candidates(self, task_id: str) -> list[Path]:
        root = self._archive_root()
        candidates = [self._archive_state_path(task_id)]
        candidates.extend(sorted(root.glob(f"{task_id}--attempt-*.json")) if root.exists() else [])
        return [path for path in candidates if path.exists()]

    @staticmethod
    def _candidate_commit(state: Mapping[str, Any]) -> Optional[str]:
        packet = state.get("promotion_packet") or {}
        return state.get("candidate_commit_sha") or packet.get("candidate_commit_sha")

    def _require_integrated_replacement(self, task_id: str, superseded_by: str) -> None:
        replacement = self._read_state(superseded_by)
        if (
            replacement is None
            or replacement.get("task_id", superseded_by) == task_id
            or replacement.get("status") != "INTEGRATED"
            or replacement.get("promotion_status") != "INTEGRATED"
            or not str(replacement.get("integration_result_sha") or "").strip()
        ):
            raise RuntimeError(
                "superseded_by must name an existing INTEGRATED self-hosted task "
                "with promotion_status=INTEGRATED and integration_result_sha"
            )

    @classmethod
    def _task_action_envelope(cls, state: Mapping[str, Any]) -> dict[str, Any]:
        status = str(state.get("status") or "UNKNOWN")
        promotion_status = str(state.get("promotion_status") or "")
        candidate_commit = cls._candidate_commit(state)

        if status == "INTEGRATING":
            action_state = "IN_PROGRESS"
            attention_required = False
            next_action = "wait_for_task"
            recommended_tool = "nexus_self_hosted_wait_task"
        elif status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"}:
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "inspect_blocker_and_retry_or_dispose"
            recommended_tool = "nexus_self_hosted_get_receipt"
        elif status in (PENDING_CANDIDATE_STATUSES - {"INTEGRATING"}) or promotion_status in {"PENDING_HUMAN_APPROVAL", "APPROVED", "APPROVAL_INVALIDATED"}:
            action_state = "ACTION_REQUIRED"
            attention_required = True
            if promotion_status == "APPROVED" or status == "APPROVED":
                next_action = "integrate_approved_candidate"
                recommended_tool = "nexus_self_hosted_integrate_approved"
            elif promotion_status == "APPROVAL_INVALIDATED" or status == "APPROVAL_INVALIDATED":
                next_action = "resubmit_exact_approval_binding"
                recommended_tool = "nexus_self_hosted_approve_promotion"
            else:
                next_action = "approve_candidate"
                recommended_tool = "nexus_self_hosted_approve_promotion"
        elif status in TERMINAL_STATUSES:
            action_state = "TERMINAL"
            attention_required = False
            next_action = "none"
            recommended_tool = None
        else:
            action_state = "IN_PROGRESS"
            attention_required = False
            next_action = "wait_for_task"
            recommended_tool = "nexus_self_hosted_wait_task"

        packet = state.get("promotion_packet") or {}
        return {
            "schema": "nexus.self_hosted_task_action.v1",
            "task_id": state.get("task_id"),
            "task_status": status,
            "promotion_status": promotion_status or None,
            "action_state": action_state,
            "attention_required": attention_required,
            "next_action": next_action,
            "recommended_tool": recommended_tool,
            "candidate_commit_sha": candidate_commit,
            "candidate_ref": state.get("candidate_ref"),
            "candidate": {
                "candidate_commit_sha": candidate_commit,
                "candidate_tree_sha": state.get("candidate_tree_sha") or packet.get("candidate_tree_sha"),
                "candidate_state_hash": state.get("candidate_state_hash") or packet.get("candidate_state_hash"),
                "verified_receipt_hash": state.get("verified_receipt_hash") or packet.get("verified_receipt_hash"),
            },
            "cleanup_status": {
                "cleanup_eligible": state.get("cleanup_eligible", False),
                "cleanup_decision": state.get("cleanup_decision"),
                "cleanup_blocker": state.get("cleanup_blocker"),
                "cleanup_performed": state.get("cleanup_performed", False),
                "cleanup_performed_at": state.get("cleanup_performed_at"),
                "state_retention_status": state.get("state_retention_status"),
                "archive_eligible": state.get("archive_eligible", False),
            },
        }

    @classmethod
    def _with_task_action(cls, state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        state["task_action"] = cls._task_action_envelope(state)
        return state

    def _latest_archived_state(self, task_id: str) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
        latest_path: Optional[Path] = None
        latest_state: Optional[dict[str, Any]] = None
        latest_key: tuple[str, int] = ("", -1)
        for path in self._archive_state_candidates(task_id):
            state = json.loads(path.read_text(encoding="utf-8"))
            key = (str(state.get("updated_at") or ""), path.stat().st_mtime_ns)
            if latest_state is None or key > latest_key:
                latest_path, latest_state, latest_key = path, self._with_task_action(state), key
        return latest_path, latest_state

    def _lock_path(self) -> Path:
        return self.state_dir / ".state.lock"

    @contextmanager
    def _state_lock(self) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self._lock_path().open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write_state_locked(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        normalized = _jsonable(state)
        normalized["task_action"] = self._task_action_envelope(normalized)
        destination = self._state_path(task_id)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.state_dir,
            prefix=f".{task_id}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(normalized, handle, sort_keys=True, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(destination)
        return normalized

    def _write_state(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock():
            return self._write_state_locked(task_id, state)

    def _create_state(self, task_id: str, state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self._state_lock():
            destination = self._state_path(task_id)
            if destination.exists():
                return self._with_task_action(json.loads(destination.read_text(encoding="utf-8"))), False
            _, archived = self._latest_archived_state(task_id)
            if archived is not None:
                return self._with_task_action(archived), False
            return self._write_state_locked(task_id, state), True

    def _read_state(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._state_path(task_id)
        if not path.exists():
            _, archived = self._latest_archived_state(task_id)
            return archived
        with self._state_lock():
            if not path.exists():
                return None
            return self._with_task_action(json.loads(path.read_text(encoding="utf-8")))

    def _reactivate_archived_state(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock():
            path = self._state_path(task_id)
            if path.exists():
                return self._with_task_action(json.loads(path.read_text(encoding="utf-8")))
            if not self._archive_state_candidates(task_id):
                raise RuntimeError("archived task receipt disappeared before retry")
            return self._write_state_locked(task_id, state)

    def _mutate_state(self, task_id: str, mutator: Callable[[dict[str, Any]], None]) -> Optional[dict[str, Any]]:
        with self._state_lock():
            path = self._state_path(task_id)
            if not path.exists():
                return None
            state = json.loads(path.read_text(encoding="utf-8"))
            mutator(state)
            return self._write_state_locked(task_id, state)

    def _checkpoint(
        self,
        task_id: str,
        status: str,
        values: Optional[Mapping[str, Any]] = None,
        *,
        attempt_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        now = _utc_now()

        def mutate(state: dict[str, Any]) -> None:
            if attempt_id is not None and state.get("attempt_id") != attempt_id:
                raise RuntimeError("task attempt ownership changed")
            previous = state.get("status")
            state["status"] = status
            if values:
                updates = _jsonable(dict(values))
                updates.pop("submitted_at", None)
                state.update(updates)
            state["updated_at"] = now
            state["heartbeat_at"] = now
            history = list(state.get("status_history", []))
            if previous != status:
                history.append({"status": status, "at": now})
            state["status_history"] = history
            if status in TERMINAL_STATUSES:
                state["worker_finished_at"] = now
                state["worker_child_pgid"] = None
            for attempt in state.get("attempts", []):
                if attempt.get("attempt_id") == state.get("attempt_id"):
                    attempt["last_status"] = status
                    attempt["updated_at"] = now
                    if status in TERMINAL_STATUSES or status == "PENDING_HUMAN_APPROVAL":
                        attempt["finished_at"] = now
            lease = state.get("lease") or {}
            if lease:
                state.update({
                    "controller_worktree": (state.get("contract") or {}).get("controller_repo_root"),
                    "controller_status_sha256": lease.get("controller_status_sha256"),
                    "target_worktree": lease.get("target_worktree"),
                    "target_initial_revision": lease.get("initial_head"),
                    "target_branch": lease.get("target_branch"),
                    "target_created_at": state.get("target_created_at") or now,
                })
            execution = state.get("execution") or {}
            if execution:
                state["execution_outcome"] = execution.get("outcome")
            resolution = state.get("attempt_resolution") or {}
            if resolution:
                state["verification_verdict"] = resolution.get("verdict")
            packet = state.get("promotion_packet") or {}
            if packet:
                for field in (
                    "candidate_commit_sha", "candidate_tree_sha",
                    "candidate_state_hash", "verified_receipt_hash",
                ):
                    state[field] = packet.get(field)

        return self._mutate_state(task_id, mutate)

    def _heartbeat(self, task_id: str, attempt_id: str, stop: threading.Event) -> None:
        while not stop.wait(1.0):
            try:
                self._mutate_state(
                    task_id,
                    lambda state: self._touch_owned_state(state, attempt_id),
                )
            except (RuntimeError, OSError, json.JSONDecodeError):
                return

    @staticmethod
    def _touch_owned_state(state: dict[str, Any], attempt_id: str) -> None:
        if state.get("attempt_id") != attempt_id or state.get("status") in TERMINAL_STATUSES:
            raise RuntimeError("task is no longer owned by this attempt")
        now = _utc_now()
        state["heartbeat_at"] = now
        state["updated_at"] = now

    def build_contract(self, request: Mapping[str, Any]) -> ArchitectTaskContract:
        if "prompt" in request:
            raise ValueError("prompt is not accepted; submit WHAT and WHY")
        worker = str(request.get("worker", "codex")).strip().lower()
        requested_worker = worker
        if worker not in SUPPORTED_WORKER_PROVIDERS:
            if worker != "auto":
                raise ValueError(
                    "worker must be one of: auto, " + ", ".join(SUPPORTED_WORKER_PROVIDERS)
                )
        provider_order = request.get("worker_order")
        if provider_order is None:
            provider_order = (
                list(SUPPORTED_WORKER_PROVIDERS)
                if requested_worker == "auto"
                else [worker]
            )
        provider_order = [str(provider).strip().lower() for provider in provider_order]
        if worker == "auto" and not provider_order:
            raise ValueError("worker_order must be non-empty for auto selection")
        if worker == "auto" and (set(provider_order) - set(SUPPORTED_WORKER_PROVIDERS) or len(set(provider_order)) != len(provider_order)):
            raise ValueError("worker_order contains an unknown or duplicate provider")
        if worker == "auto":
            worker = provider_order[0]
        fallback_worker = request.get("fallback_worker", request.get("fallback_provider"))
        if fallback_worker is not None:
            fallback_worker = str(fallback_worker).strip().lower()
            if fallback_worker not in SUPPORTED_WORKER_PROVIDERS:
                raise ValueError(
                    "fallback_worker must be one of: " + ", ".join(SUPPORTED_WORKER_PROVIDERS)
                )
            if fallback_worker == worker:
                raise ValueError("fallback_worker must differ from worker")
            if fallback_worker not in provider_order:
                provider_order.append(fallback_worker)
        what = str(request.get("what", "")).strip()
        why = str(request.get("why", "")).strip()
        if not what or not why:
            raise ValueError("what and why are required")
        task_id = str(request.get("task_id") or f"mcp-{uuid4().hex[:12]}")
        decisions = request.get("architecture_decisions") or [
            {
                "decision_id": "target-boundary",
                "selected_option": "Target-only mutation",
                "rationale": "Preserve Controller immutability during worker execution",
                "rejected_alternatives": ["Controller mutation"],
            }
        ]
        decision_models = [
            item if isinstance(item, ArchitectureDecision) else ArchitectureDecision(**item)
            for item in decisions
        ]
        verifier_commands = [str(item) for item in request.get("verifier_commands", [])]
        protected_contracts = [str(item) for item in request.get("protected_contracts", [])]
        return ArchitectTaskContract(
            task_id=task_id,
            objective=what,
            goal=DevelopmentGoal(what=what, why=why),
            architecture_decisions=decision_models,
            acceptance_profile=AcceptanceProfile(
                verifier_commands=verifier_commands,
                protected_contracts=protected_contracts,
                required_evidence=["candidate_state_hash", "controller_unchanged", "verified_candidate_receipt"],
            ),
            human_approval_policy=HumanApprovalPolicy(
                approver_roles=list(request.get("approver_roles", ["James"])),
            ),
            controller_revision=str(request["controller_revision"]),
            target_base_revision=str(request["target_base_revision"]),
            controller_repo_root=str(request["controller_repo_root"]),
            target_repo_root=str(request["target_repo_root"]),
            target_worktree_root=str(request["target_worktree_root"]),
            allowed_files=list(request["allowed_files"]),
            forbidden_files=list(request.get("forbidden_files", [])),
            verifier_commands=verifier_commands,
            protected_contracts=protected_contracts,
            preferred_provider=worker,
            fallback_provider=fallback_worker or (provider_order[1] if len(provider_order) > 1 else None),
            provider_order=provider_order,
            maximum_provider_calls=len(provider_order) if requested_worker == "auto" else (2 if fallback_worker else 1),
            maximum_replans=0,
            mutation_mode=MutationMode.WORKING_TREE_ONLY,
            human_approval_required=True,
        )

    @staticmethod
    def _terminal_retry_revision_refresh_allowed(
        existing: Mapping[str, Any],
        request: Mapping[str, Any],
        contract: ArchitectTaskContract,
    ) -> bool:
        previous_request = dict(existing.get("request") or {})
        next_request = _jsonable(dict(request))
        for field in ("controller_revision", "target_base_revision"):
            previous_request.pop(field, None)
            next_request.pop(field, None)
        if previous_request != next_request:
            return False

        previous_contract = existing.get("contract") or {}
        previous_controller = str(previous_contract.get("controller_revision") or "")
        previous_target = str(previous_contract.get("target_base_revision") or "")
        revisions = (
            (previous_controller, contract.controller_revision),
            (previous_target, contract.target_base_revision),
        )
        if not all(old and new for old, new in revisions):
            return False
        if all(old == new for old, new in revisions):
            return False

        controller_root = Path(contract.controller_repo_root).expanduser().resolve()
        return all(
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", old, new],
                cwd=controller_root,
                capture_output=True,
                text=True,
            ).returncode == 0
            for old, new in revisions
        )

    def _contract_from_state(self, state: Mapping[str, Any]) -> ArchitectTaskContract:
        request = state.get("request")
        if isinstance(request, Mapping):
            return self.build_contract(request)
        contract = state.get("contract")
        if not isinstance(contract, Mapping):
            raise RuntimeError("task state is missing its contract")
        return ArchitectTaskContract.model_validate(contract)

    @staticmethod
    def _prompt(contract: ArchitectTaskContract) -> str:
        allowed = ", ".join(contract.allowed_files)
        verifiers = "\n".join(f"- {command}" for command in contract.verifier_commands)
        return (
            f"WHAT: {contract.goal.what}\n"
            f"WHY: {contract.goal.why}\n"
            f"Allowed files: {allowed}\n"
            "Work only in the isolated Target. Do not edit, delete, stage, commit, merge, push, or reset "
            "outside the allowed scope. Run every verifier command below after making the change; if any "
            "verifier fails, diagnose and repair within the allowed files before returning.\n"
            f"Required verifier commands:\n{verifiers}\n"
            "Return a concise summary only after all required verifiers pass."
        )

    def _set_child_pgid(self, task_id: str, attempt_id: str, pgid: Optional[int]) -> None:
        def mutate(state: dict[str, Any]) -> None:
            if state.get("attempt_id") == attempt_id and state.get("status") not in TERMINAL_STATUSES:
                state["worker_child_pgid"] = pgid
                state["updated_at"] = _utc_now()

        self._mutate_state(task_id, mutate)

    def _lease_from_state(self, state: Mapping[str, Any]) -> TargetWorktreeLease:
        raw = state.get("lease")
        if not isinstance(raw, Mapping):
            raise RuntimeError("durable lease evidence is missing")
        return TargetWorktreeLease(**dict(raw))

    def _capture_resumed_candidate(
        self,
        contract: ArchitectTaskContract,
        controller: SelfHostedDevelopmentController,
        lease: TargetWorktreeLease,
        state: Mapping[str, Any],
    ):
        candidate = controller.collect_candidate(contract, lease)
        stored = state.get("candidate") or {}
        if stored.get("candidate_state_hash") and stored["candidate_state_hash"] != candidate.candidate_state_hash:
            raise RuntimeError("candidate state changed during recovery")
        return candidate

    @staticmethod
    def _receipt_from_state(value: Any) -> Optional[WorkerExecutionReceipt]:
        if isinstance(value, WorkerExecutionReceipt):
            return value
        if not isinstance(value, Mapping) or "outcome" not in value:
            return None
        try:
            payload = dict(value)
            payload["argv"] = tuple(payload.get("argv", ()))
            return WorkerExecutionReceipt(**payload)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _escalation_policy(contract: ArchitectTaskContract) -> Optional[WorkerEscalationPolicy]:
        if not contract.preferred_provider or not contract.fallback_provider:
            return None
        return WorkerEscalationPolicy(
            cheap_provider=contract.preferred_provider,
            strong_provider=contract.fallback_provider,
            provider_order=tuple(contract.provider_order or (contract.preferred_provider, contract.fallback_provider)),
        )

    def _select_initial_provider(
        self,
        contract: ArchitectTaskContract,
    ) -> tuple[str, Any]:
        providers = list(contract.provider_order or [str(contract.preferred_provider or "codex")])
        failures: list[str] = []
        for provider in providers:
            preflight = self.worker_registry.preflight(provider)
            if preflight.ready:
                return provider, preflight
            failures.append(f"{provider}: {preflight.reason}")
        raise RuntimeError("worker preflight failed: " + "; ".join(failures))

    def _next_ready_provider(
        self,
        policy: WorkerEscalationPolicy,
        attempts: Sequence[WorkerExecutionReceipt],
    ) -> Optional[str]:
        attempted = {attempt.provider for attempt in attempts}
        for provider in policy.provider_order or (policy.strong_provider,):
            if provider in attempted:
                continue
            if self.worker_registry.preflight(provider).ready:
                return provider
        return None

    @staticmethod
    def _replace_failed_target(
        manager: WorktreeManager,
        controller: SelfHostedDevelopmentController,
        contract: ArchitectTaskContract,
        lease: TargetWorktreeLease,
    ) -> TargetWorktreeLease:
        manager.verify_controller_unchanged(
            contract,
            expected_status_sha256=lease.controller_status_sha256,
        )
        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=lease.target_worktree)
        if target_head != lease.initial_head:
            raise RuntimeError("failed worker changed Target HEAD; escalation is blocked")
        manager.cleanup(contract.task_id, force=True)
        return controller.prepare_task(contract)

    def _run_default_resumable(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        update: Callable[[str, dict[str, Any]], None],
        *,
        task_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        controller = SelfHostedDevelopmentController(worktree_manager=manager)
        state = self._read_state(task_id) or {}
        status = str(state.get("status"))
        policy = self._escalation_policy(contract)
        attempts = [
            receipt
            for raw in state.get("executions", [])
            if (receipt := self._receipt_from_state(raw)) is not None
        ]
        if status == "SUBMITTED":
            provider, preflight = self._select_initial_provider(contract)
            lease = controller.prepare_task(contract)
            update(
                "TARGET_LEASED",
                {
                    "lease": lease,
                    "worker_preflight": preflight,
                    "active_provider": provider,
                },
            )
            update("WORKER_RUNNING", {"active_provider": provider})
            state = self._read_state(task_id) or {}
            status = "WORKER_RUNNING"
        elif status == "WORKER_ESCALATING":
            lease = self._lease_from_state(state)
            provider = str(state.get("next_provider") or "")
            if not provider:
                raise RuntimeError("escalation state is missing next_provider")
            lease = self._replace_failed_target(manager, controller, contract, lease)
            preflight = self.worker_registry.preflight(provider)
            if not preflight.ready:
                raise RuntimeError(f"worker preflight failed: {preflight.reason}")
            update(
                "TARGET_LEASED",
                {
                    "lease": lease,
                    "worker_preflight": preflight,
                    "active_provider": provider,
                    "next_provider": None,
                },
            )
            update("WORKER_RUNNING", {"active_provider": provider})
            state = self._read_state(task_id) or {}
            status = "WORKER_RUNNING"
        elif status == "TARGET_LEASED":
            raise RuntimeError("worker lost before execution receipt; recovery is fail-closed")
        else:
            lease = self._lease_from_state(state)

        execution = state.get("execution")
        while status in {"WORKER_RUNNING", "WORKER_COMPLETED"}:
            if status == "WORKER_RUNNING":
                def on_process_group(pgid: Optional[int]) -> None:
                    self._set_child_pgid(task_id, attempt_id, pgid)

                provider = str(
                    state.get("active_provider")
                    or contract.preferred_provider
                    or "codex"
                )
                execution_receipt = self.worker_registry.invoke(
                    provider,
                    contract,
                    lease,
                    prompt=self._prompt(contract),
                    timeout_seconds=float(request.get("timeout_seconds", 900.0)),
                    on_process_group=on_process_group,
                )
                attempts.append(execution_receipt)
                execution = execution_receipt
                update(
                    "WORKER_COMPLETED",
                    {
                        "execution": execution_receipt,
                        "executions": attempts,
                        "active_provider": provider,
                    },
                )
                state = self._read_state(task_id) or {}
                status = "WORKER_COMPLETED"
                continue

            latest = attempts[-1] if attempts else self._receipt_from_state(execution)
            if latest is None:
                raise RuntimeError("worker execution receipt is missing common outcome evidence")
            if latest.outcome == WorkerOutcome.EXECUTION_COMPLETED.value and latest.evidence_complete:
                break
            decision = policy.decide(attempts) if policy else None
            if decision is not None and decision.action in ("VERIFY", "ACCEPT"):
                break
            if decision is None or decision.action != "ESCALATE" or not decision.next_provider:
                raise RuntimeError(
                    latest.failure_reason or f"worker execution did not complete: {latest.outcome}"
                )
            next_provider = self._next_ready_provider(policy, attempts)
            if not next_provider:
                raise RuntimeError("no unattempted ready provider remains for escalation")
            update(
                "WORKER_ESCALATING",
                {
                    "executions": attempts,
                    "next_provider": next_provider,
                    "escalation_reason": decision.reason,
                },
            )
            lease = self._replace_failed_target(manager, controller, contract, lease)
            preflight = self.worker_registry.preflight(next_provider)
            if not preflight.ready:
                raise RuntimeError(f"worker preflight failed: {preflight.reason}")
            update(
                "TARGET_LEASED",
                {
                    "lease": lease,
                    "worker_preflight": preflight,
                    "active_provider": next_provider,
                    "next_provider": None,
                },
            )
            update("WORKER_RUNNING", {"active_provider": next_provider})
            state = self._read_state(task_id) or {}
            status = "WORKER_RUNNING"

        if status == "WORKER_COMPLETED":
            candidate = self._capture_resumed_candidate(contract, controller, lease, state)
            update("CANDIDATE_CAPTURED", {"candidate": candidate})
            state = self._read_state(task_id) or {}
            status = "CANDIDATE_CAPTURED"
        else:
            candidate = self._capture_resumed_candidate(contract, controller, lease, state)

        verified = CandidateVerifier(manager).verify(
            contract,
            lease,
            candidate,
            protected_paths=request.get("protected_paths") or {},
        )
        latest_execution = attempts[-1] if attempts else self._receipt_from_state(execution)
        if latest_execution is None:
            raise RuntimeError("worker execution receipt is missing for attempt resolution")
        resolution = resolve_attempt(latest_execution, candidate, verified)

        update("VERIFIED", {
            "verified_receipt": verified,
            "attempt_resolution": resolution,
        })

        if resolution.verdict != AttemptResolutionVerdict.PROVEN.value:
            reasons = ", ".join(resolution.failure_reasons) or f"verdict is {resolution.verdict}"
            raise RuntimeError(f"candidate verification failed: {reasons}")

        packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
        candidate_values = {
            "execution": execution,
            "candidate": candidate,
            "verified_receipt": verified,
            "attempt_resolution": resolution,
            "promotion_packet": packet,
            "promotion_status": packet.promotion_status,
            "candidate_commit_created": packet.candidate_commit_created,
            "public_claim_allowed": packet.public_claim_allowed,
            "production_ready": packet.production_ready,
            "merge_performed": packet.merge_performed,
            "push_performed": packet.push_performed,
        }
        update("CANDIDATE_COMMITTED", candidate_values)
        candidate_ref = manager.protect_candidate(contract, lease, packet.candidate_commit_sha)
        update("CANDIDATE_REF_PROTECTED", {"candidate_ref": candidate_ref})
        cleanup = manager.cleanup_terminal_target(
            contract,
            lease,
            candidate_commit=packet.candidate_commit_sha,
            candidate_ref=candidate_ref,
        )
        if cleanup.decision != "REMOVED":
            raise RuntimeError(f"candidate Target cleanup failed: {cleanup.decision}")
        update("TARGET_CLEANED", {
            "cleanup_eligible": cleanup.eligible,
            "cleanup_decision": cleanup.decision,
            "cleanup_blocker": cleanup.blocker,
            "cleanup_performed": cleanup.performed,
            "cleanup_performed_at": _utc_now(),
        })
        result = {
            **candidate_values,
            "candidate_ref": candidate_ref,
            "candidate_status": "PENDING_HUMAN_APPROVAL",
            "cleanup_decision": cleanup.decision,
            "cleanup_blocker": cleanup.blocker,
            "cleanup_performed": cleanup.performed,
            "cleanup_performed_at": _utc_now(),
            "terminal_status": "PENDING_HUMAN_APPROVAL",
            "cleanup_eligible": cleanup.eligible,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
        }
        return result

    def _run_default(self, contract, request, update):
        return self._run_default_resumable(
            contract,
            request,
            update,
            task_id=contract.task_id,
            attempt_id=str((self._read_state(contract.task_id) or {}).get("attempt_id", "")),
        )

    def _run_owned_task(self, task_id: str, attempt_id: str) -> None:
        state = self._read_state(task_id)
        if state is None or state.get("attempt_id") != attempt_id:
            return
        owner_pid = os.getpid()
        if state.get("worker_pid") not in (None, owner_pid):
            return
        stop = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(task_id, attempt_id, stop), daemon=True)
        heartbeat.start()

        def update(status: str, values: dict[str, Any]) -> None:
            self._checkpoint(task_id, status, values, attempt_id=attempt_id)

        try:
            contract = self.build_contract(state["request"])
            if self._custom_runner is None:
                result = self._run_default_resumable(
                    contract,
                    state["request"],
                    update,
                    task_id=task_id,
                    attempt_id=attempt_id,
                )
            else:
                result = self.runner(contract, state["request"], update)
            current = self._read_state(task_id) or {}
            if current.get("status") not in TERMINAL_STATUSES:
                final_status = "PENDING_HUMAN_APPROVAL" if result.get("promotion_status") == "PENDING_HUMAN_APPROVAL" else "CANDIDATE_COMMITTED"
                self._checkpoint(task_id, final_status, result, attempt_id=attempt_id)
        except Exception as exc:
            self._terminate_owned_processes(task_id, exclude_pid=owner_pid)
            current = self._read_state(task_id) or {}
            cleanup_values: dict[str, Any] = {
                "cleanup_decision": "ALREADY_REMOVED",
                "cleanup_blocker": None,
                "cleanup_performed": False,
                "terminal_status": "FINAL_BLOCK",
                "state_retention_status": "TERMINAL",
            }
            if current.get("lease"):
                try:
                    contract = self.build_contract(current["request"])
                    lease = self._lease_from_state(current)
                    cleanup = WorktreeManager(root_dir=contract.target_worktree_root).cleanup_terminal_target(contract, lease)
                    cleanup_values.update({
                        "cleanup_decision": cleanup.decision,
                        "cleanup_blocker": cleanup.blocker,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                    })
                    cleanup_values["cleanup_eligible"] = cleanup.eligible
                    if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES":
                        cleanup_values["terminal_status"] = "RETAINED_FOR_REVIEW"
                except Exception as cleanup_exc:
                    cleanup_values.update({
                        "cleanup_decision": "CLEANUP_BLOCKED",
                        "cleanup_blocker": str(cleanup_exc),
                    })
            self._checkpoint(
                task_id,
                str(cleanup_values["terminal_status"]),
                {"error": str(exc), "promotion_status": "NOT_CREATED", **cleanup_values},
                attempt_id=attempt_id,
            )
        finally:
            stop.set()
            heartbeat.join(timeout=2.0)

    def _wait_for_owner(self, task_id: str, attempt_id: str, pid: int) -> bool:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            state = self._read_state(task_id)
            if state is None or state.get("attempt_id") != attempt_id:
                return False
            if state.get("worker_pid") == pid:
                return True
            time.sleep(0.05)
        return False

    def _launch_worker(self, task_id: str, attempt_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None or state.get("attempt_id") != attempt_id:
            return state
        if state.get("worker_pid") and self._pid_alive(int(state["worker_pid"])):
            return state
        if self._custom_runner is not None:
            thread = threading.Thread(target=self._run_owned_task, args=(task_id, attempt_id), daemon=True)
            self._threads[task_id] = thread
            self._mutate_state(
                task_id,
                lambda current: current.update({
                    "worker_pid": os.getpid(),
                    "worker_pgid": os.getpgrp(),
                    "worker_mode": "thread",
                    "worker_started_at": _utc_now(),
                    "heartbeat_at": _utc_now(),
                }),
            )
            thread.start()
            return self._read_state(task_id)
        command = [
            sys.executable,
            "-m",
            "nexus.orchestrator.self_hosted_task_worker",
            "--state-dir",
            str(self.state_dir),
            "--task-id",
            task_id,
            "--attempt-id",
            attempt_id,
        ]
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
        process = subprocess.Popen(
            command,
            cwd=source_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pgid = os.getpgid(process.pid)
        return self._mutate_state(
            task_id,
            lambda current: current.update({
                "worker_pid": process.pid,
                "worker_pgid": pgid,
                "worker_mode": "process",
                "worker_started_at": _utc_now(),
                "heartbeat_at": _utc_now(),
            }),
        )

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except PermissionError:
            return True
        except (OSError, ProcessLookupError):
            return False
        return True

    def _terminate_owned_processes(self, task_id: str, *, exclude_pid: Optional[int] = None) -> None:
        state = self._read_state(task_id) or {}
        current_pgid = os.getpgrp()
        for raw_pgid in (state.get("worker_child_pgid"), state.get("worker_pgid")):
            if not raw_pgid:
                continue
            pgid = int(raw_pgid)
            if pgid in {current_pgid, exclude_pid}:
                continue
            try:
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.05)
                os.killpg(pgid, signal.SIGKILL)
            except (PermissionError, ProcessLookupError):
                continue

    def reconcile_task(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None or state.get("status") in TERMINAL_STATUSES:
            return state
        if state.get("status") in PENDING_CANDIDATE_STATUSES:
            return state
        if state.get("status") in {"CANDIDATE_COMMITTED", "CANDIDATE_REF_PROTECTED", "TARGET_CLEANED"}:
            owner_pid = state.get("worker_pid")
            owner_heartbeat = _parse_time(state.get("heartbeat_at"))
            owner_fresh = owner_heartbeat is not None and time.time() - owner_heartbeat <= self.stale_after_seconds
            if owner_pid and self._pid_alive(int(owner_pid)) and owner_fresh:
                return state
            if owner_pid and self._pid_alive(int(owner_pid)):
                self._terminate_owned_processes(task_id)
            packet = state.get("promotion_packet") or {}
            candidate_commit = packet.get("candidate_commit_sha")
            if not candidate_commit:
                return self._checkpoint(
                    task_id, "FINAL_BLOCK",
                    {
                        "error": "candidate checkpoint is missing its promotion packet",
                        "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                        "cleanup_blocker": "candidate commit is missing",
                        "cleanup_performed": False,
                        "terminal_status": "FINAL_BLOCK",
                    },
                    attempt_id=state.get("attempt_id"),
                )
            if state.get("status") != "TARGET_CLEANED":
                contract = self._contract_from_state(state)
                lease = self._lease_from_state(state)
                manager = WorktreeManager(root_dir=contract.target_worktree_root)
                candidate_ref = state.get("candidate_ref")
                if not candidate_ref:
                    candidate_ref = manager.protect_candidate(contract, lease, candidate_commit)
                    state = self._checkpoint(
                        task_id, "CANDIDATE_REF_PROTECTED",
                        {"candidate_ref": candidate_ref},
                        attempt_id=state.get("attempt_id"),
                    ) or state
                cleanup = manager.cleanup_terminal_target(
                    contract, lease,
                    candidate_commit=candidate_commit,
                    candidate_ref=str(candidate_ref),
                )
                if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                    terminal = "RETAINED_FOR_REVIEW" if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES" else "FINAL_BLOCK"
                    return self._checkpoint(task_id, terminal, {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_blocker": cleanup.blocker,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_eligible": cleanup.eligible,
                        "terminal_status": terminal,
                    }, attempt_id=state.get("attempt_id"))
                state = self._checkpoint(task_id, "TARGET_CLEANED", {
                    "cleanup_decision": cleanup.decision,
                    "cleanup_blocker": cleanup.blocker,
                    "cleanup_performed": cleanup.performed,
                    "cleanup_eligible": cleanup.eligible,
                    "cleanup_performed_at": _utc_now() if cleanup.performed else state.get("cleanup_performed_at"),
                }, attempt_id=state.get("attempt_id")) or state
            return self._checkpoint(task_id, "PENDING_HUMAN_APPROVAL", {
                "promotion_status": "PENDING_HUMAN_APPROVAL",
                "candidate_status": "PENDING_HUMAN_APPROVAL",
                "terminal_status": "PENDING_HUMAN_APPROVAL",
                "state_retention_status": "ACTIVE",
                "archive_eligible": False,
            }, attempt_id=state.get("attempt_id"))
        pid = state.get("worker_pid")
        heartbeat_at = _parse_time(state.get("heartbeat_at"))
        stale = heartbeat_at is not None and time.time() - heartbeat_at > self.stale_after_seconds
        if pid and self._pid_alive(int(pid)) and not stale:
            return state
        if pid and self._pid_alive(int(pid)) and stale:
            self._terminate_owned_processes(task_id)
            return self._checkpoint(
                task_id,
                "FINAL_BLOCK",
                {"error": "stale task heartbeat; owned process group terminated", "promotion_status": "NOT_CREATED"},
                attempt_id=state.get("attempt_id"),
            )
        if state.get("status") == "TARGET_LEASED":
            contract = state.get("contract") or {}
            target = Path(str(contract.get("target_repo_root", ""))).expanduser().resolve()
            controller = Path(str(contract.get("controller_repo_root", ""))).expanduser().resolve()
            target_exists = target.is_dir()
            manager = WorktreeManager(root_dir=str(contract.get("target_worktree_root") or target.parent))
            entry = manager._worktree_entry(controller, target) if target_exists and controller.is_dir() else None
            head = manager._run_git(["rev-parse", "HEAD"], cwd=target) if entry else None
            dirty = bool(manager._status_bytes(target)) if entry else None
            evidence = {
                "worker_alive": False,
                "heartbeat_fresh": False,
                "target_exists": target_exists,
                "target_registered": entry is not None,
                "target_clean": not dirty if dirty is not None else None,
                "target_head": head,
                "candidate_exists": bool(head and head != contract.get("target_base_revision")),
            }
            if entry and dirty:
                return self._checkpoint(task_id, "RETAINED_FOR_REVIEW", {
                    **evidence,
                    "reconcile_decision": "RETAINED_FOR_REVIEW",
                    "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                    "cleanup_blocker": "dirty target has no durable snapshot",
                    "cleanup_performed": False,
                    "terminal_status": "RETAINED_FOR_REVIEW",
                    "state_retention_status": "TERMINAL",
                }, attempt_id=state.get("attempt_id"))
            if entry and head != contract.get("target_base_revision"):
                if state.get("candidate") and state.get("execution"):
                    resumed = self._checkpoint(
                        task_id, "CANDIDATE_CAPTURED",
                        {**evidence, "reconcile_decision": "RESUME_CANDIDATE_VERIFICATION"},
                        attempt_id=state.get("attempt_id"),
                    )
                    return self._launch_worker(task_id, str(state.get("attempt_id"))) or resumed
                return self._checkpoint(task_id, "RETAINED_FOR_REVIEW", {
                    **evidence,
                    "reconcile_decision": "RETAINED_FOR_REVIEW",
                    "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                    "cleanup_blocker": "candidate HEAD lacks recoverable receipt evidence",
                    "cleanup_performed": False,
                    "terminal_status": "RETAINED_FOR_REVIEW",
                    "state_retention_status": "TERMINAL",
                }, attempt_id=state.get("attempt_id"))
            cleanup_decision = "ALREADY_REMOVED"
            cleanup_performed = entry is None
            cleanup_blocker = None
            cleanup_eligible = True
            if entry:
                lease_data = state.get("lease") or {
                    "schema": "nexus.target_worktree_lease.v1",
                    "lease_id": manager._lease_id(
                        self._contract_from_state(state),
                        target,
                        f"nexus/task/{task_id}",
                    ),
                    "task_id": task_id,
                    "controller_revision": contract.get("controller_revision"),
                    "target_base_revision": contract.get("target_base_revision"),
                    "target_worktree": str(target),
                    "target_branch": f"nexus/task/{task_id}",
                    "initial_head": contract.get("target_base_revision"),
                    "initial_status_sha256": hashlib.sha256(b"").hexdigest(),
                    "controller_status_sha256": hashlib.sha256(b"").hexdigest(),
                    "created_from_exact_revision": True,
                    "commit_created": False,
                    "merge_performed": False,
                }
                cleanup = manager.cleanup_terminal_target(
                    self._contract_from_state(state),
                    TargetWorktreeLease(**lease_data),
                )
                cleanup_decision = cleanup.decision
                cleanup_performed = cleanup.performed
                cleanup_blocker = cleanup.blocker
                cleanup_eligible = cleanup.eligible
            return self._checkpoint(task_id, "FINAL_BLOCK", {
                **evidence,
                "reconcile_decision": cleanup_decision,
                "cleanup_decision": cleanup_decision,
                "cleanup_blocker": cleanup_blocker,
                "cleanup_eligible": cleanup_eligible,
                "cleanup_performed": cleanup_performed,
                "cleanup_performed_at": _utc_now() if cleanup_performed else None,
                "terminal_status": "FINAL_BLOCK",
                "state_retention_status": "TERMINAL",
                "archive_eligible": True,
            }, attempt_id=state.get("attempt_id"))
        if state.get("status") == "SUBMITTED" or state.get("status") in RESUMABLE_STATUSES:
            return self._launch_worker(task_id, str(state.get("attempt_id")))
        self._terminate_owned_processes(task_id)
        return self._checkpoint(
            task_id,
            "FINAL_BLOCK",
            {"error": "worker lost before recoverable execution evidence", "promotion_status": "NOT_CREATED"},
            attempt_id=state.get("attempt_id"),
        )

    def recover_retained_candidate(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") != "RETAINED_FOR_REVIEW":
            raise RuntimeError("only a retained candidate can enter recovery")
        packet = state.get("promotion_packet") or {}
        verified = state.get("verified_receipt") or {}
        candidate_commit = str(packet.get("candidate_commit_sha") or "")
        candidate_tree = str(packet.get("candidate_tree_sha") or "")
        if not candidate_commit or not candidate_tree or not verified:
            raise RuntimeError("retained candidate lacks verified durable recovery evidence")
        contract = self._contract_from_state(state)
        lease = self._lease_from_state(state)
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        target = Path(lease.target_worktree).resolve()
        controller = Path(contract.controller_repo_root).resolve()
        if manager._worktree_entry(controller, target) is None:
            raise RuntimeError("retained candidate Target is not a registered worktree")
        if manager.process_checker(target):
            raise RuntimeError("active process uses retained candidate Target")
        if manager._status_bytes(target):
            raise RuntimeError("retained candidate Target has unsaved working-tree changes")
        if manager._run_git(["rev-parse", "HEAD"], cwd=target) != candidate_commit:
            raise RuntimeError("retained candidate HEAD does not match promotion packet")
        if manager._run_git(["rev-parse", "HEAD^{tree}"], cwd=target) != candidate_tree:
            raise RuntimeError("retained candidate tree does not match promotion packet")
        self._checkpoint(task_id, "CANDIDATE_COMMITTED", {
            "error": None,
            "promotion_status": str(packet.get("promotion_status") or "PENDING_HUMAN_APPROVAL"),
            "cleanup_decision": None,
            "cleanup_blocker": None,
            "cleanup_performed": False,
            "terminal_status": None,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
        }, attempt_id=state.get("attempt_id"))
        recovered = self.reconcile_task(task_id)
        if recovered is None:
            raise RuntimeError("retained candidate recovery lost task state")
        return recovered

    def reconcile_tasks(self) -> list[dict[str, Any]]:
        if not self.state_dir.exists():
            return []
        states = []
        for path in sorted(self.state_dir.glob("*.json")):
            state = self.reconcile_task(path.stem)
            if state is not None:
                states.append(state)
        return states

    def resume_task(self, task_id: str) -> Optional[dict[str, Any]]:
        return self.reconcile_task(task_id)

    def wait_task(
        self,
        task_id: str,
        *,
        timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.25,
    ) -> Optional[dict[str, Any]]:
        timeout_seconds = float(timeout_seconds)
        poll_interval_seconds = float(poll_interval_seconds)
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if timeout_seconds > 60.0:
            raise ValueError("timeout_seconds must be <= 60")

        deadline = time.monotonic() + timeout_seconds
        while True:
            state = self.get_task(task_id)
            if state is None:
                return None
            envelope = state.get("task_action") or self._task_action_envelope(state)
            if envelope.get("action_state") != "IN_PROGRESS":
                return {
                    **state,
                    "wait": {
                        "timed_out": False,
                        "timeout_seconds": timeout_seconds,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                }
            if time.monotonic() >= deadline:
                envelope = {**envelope, "wait_timed_out": True}
                return {
                    **state,
                    "task_action": envelope,
                    "wait": {
                        "timed_out": True,
                        "timeout_seconds": timeout_seconds,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                }
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    def list_actionable_tasks(self) -> dict[str, Any]:
        tasks = []
        for path in sorted(self.state_dir.glob("*.json")) if self.state_dir.exists() else []:
            state = self.get_task(path.stem)
            if state is None:
                continue
            action = state.get("task_action") or self._task_action_envelope(state)
            if action.get("attention_required") is True:
                tasks.append(state)
        return {
            "schema": "nexus.self_hosted_actionable_tasks.v1",
            "actionable_count": len(tasks),
            "tasks": tasks,
        }

    def submit_task(self, request: Mapping[str, Any]) -> dict[str, Any]:
        contract = self.build_contract(request)
        existing_states = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.state_dir.glob("*.json"))
        ] if self.state_dir.exists() else []
        for current in existing_states:
            if current.get("status") in TERMINAL_STATUSES:
                continue
            current_controller = (current.get("contract") or {}).get("controller_repo_root")
            if current_controller and Path(current_controller).resolve() != Path(contract.controller_repo_root).resolve():
                raise RuntimeError("active Controller lease belongs to a different controller worktree")
            if (
                current.get("task_id") != contract.task_id
                and current.get("status") in {"TARGET_LEASED", "WORKER_RUNNING", "WORKER_COMPLETED", "CANDIDATE_CAPTURED", "VERIFIED"}
                and not request.get("competition_id")
            ):
                raise RuntimeError("serial Target budget exceeded: another task owns the active Target")
        attempt_id = uuid4().hex
        now = _utc_now()
        state: dict[str, Any] = {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": contract.task_id,
            "status": "SUBMITTED",
            "submitted_at": now,
            "status_history": [{"status": "SUBMITTED", "at": now}],
            "request": _jsonable(dict(request)),
            "contract": contract.model_dump(mode="json"),
            "contract_hash": contract.contract_hash,
            "controller_worktree": contract.controller_repo_root,
            "controller_revision": contract.controller_revision,
            "controller_status_sha256": None,
            "target_worktree": contract.target_repo_root,
            "target_initial_revision": contract.target_base_revision,
            "target_branch": f"nexus/task/{contract.task_id}",
            "target_created_at": None,
            "worker_provider": contract.preferred_provider,
            "worker_selection_mode": str(
                request.get(
                    "worker_selection_mode",
                    "auto" if str(request.get("worker", "codex")).strip().lower() == "auto" else "explicit",
                )
            ),
            "attempt_id": attempt_id,
            "attempts": [{"attempt_id": attempt_id, "started_at": now}],
            "worker_pid": None,
            "worker_pgid": None,
            "worker_child_pgid": None,
            "worker_started_at": None,
            "worker_finished_at": None,
            "heartbeat_at": now,
            "updated_at": now,
            "promotion_status": "NOT_CREATED",
            "execution_outcome": None,
            "verification_verdict": None,
            "candidate_commit_sha": None,
            "candidate_tree_sha": None,
            "candidate_ref": None,
            "candidate_state_hash": None,
            "verified_receipt_hash": None,
            "salvage_commit_sha": None,
            "salvage_ref": None,
            "salvage_only": False,
            "promotion_eligible": False,
            "approved_binding": None,
            "integration_branch": None,
            "integration_base_sha": None,
            "integration_result_sha": None,
            "terminal_status": None,
            "cleanup_eligible": False,
            "cleanup_decision": None,
            "cleanup_blocker": None,
            "cleanup_performed": False,
            "cleanup_performed_at": None,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
            "archive_location": None,
            "merge_performed": False,
            "push_performed": False,
        }
        existing, created = self._create_state(contract.task_id, state)
        if not created:
            terminal_retry = existing.get("status") in {
                "FINAL_BLOCK", "REJECTED", "SUPERSEDED", "CANCELLED",
                "INTEGRATION_FAILED", "INTEGRATED",
            }
            contract_refreshed = existing.get("contract_hash") != contract.contract_hash
            if contract_refreshed and not (
                terminal_retry
                and existing.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
                and self._terminal_retry_revision_refresh_allowed(existing, request, contract)
            ):
                raise ValueError("task_id already exists with a different contract")
            if existing.get("status") in PENDING_CANDIDATE_STATUSES or existing.get("promotion_status") in {"PENDING_HUMAN_APPROVAL", "APPROVED"}:
                return existing
            if terminal_retry:
                if existing.get("cleanup_decision") not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}:
                    raise RuntimeError("terminal retry blocked until previous Target disposition")
                existing = self._reactivate_archived_state(contract.task_id, existing)
                attempt_id = uuid4().hex
                def retry(current: dict[str, Any]) -> None:
                    packet = current.get("promotion_packet") or {}
                    if packet.get("candidate_commit_sha") or current.get("candidate_ref"):
                        current.setdefault("candidate_history", []).append({
                            "candidate_commit": packet.get("candidate_commit_sha"),
                            "candidate_ref": current.get("candidate_ref"),
                            "candidate_state_hash": packet.get("candidate_state_hash"),
                            "verified_receipt_hash": packet.get("verified_receipt_hash"),
                            "approval_binding": current.get("approved_binding"),
                            "integration_branch": current.get("integration_branch"),
                            "integration_commit": current.get("integration_result_sha"),
                            "final_disposition": current.get("final_disposition") or current.get("status"),
                        })
                    if contract_refreshed:
                        previous_contract = current.get("contract") or {}
                        current.setdefault("contract_history", []).append({
                            "attempt_id": current.get("attempt_id"),
                            "contract_hash": current.get("contract_hash"),
                            "controller_revision": previous_contract.get("controller_revision"),
                            "target_base_revision": previous_contract.get("target_base_revision"),
                            "final_disposition": current.get("final_disposition") or current.get("status"),
                        })
                        current.update({
                            "request": _jsonable(dict(request)),
                            "contract": contract.model_dump(mode="json"),
                            "contract_hash": contract.contract_hash,
                            "controller_worktree": contract.controller_repo_root,
                            "controller_revision": contract.controller_revision,
                            "controller_status_sha256": None,
                            "target_worktree": contract.target_repo_root,
                            "target_initial_revision": contract.target_base_revision,
                            "target_branch": f"nexus/task/{contract.task_id}",
                            "target_created_at": None,
                            "worker_provider": contract.preferred_provider,
                        })
                    current["attempt_id"] = attempt_id
                    current.setdefault("attempts", []).append({"attempt_id": attempt_id, "started_at": now})
                    current["status"] = "SUBMITTED"
                    current.setdefault("status_history", []).append({"status": "ATTEMPT_INCREMENTED", "at": now})
                    current["lease"] = None
                    current["worker_pid"] = None
                    current["worker_pgid"] = None
                    current["worker_child_pgid"] = None
                    current["worker_started_at"] = None
                    current["worker_finished_at"] = None
                    current["worker_preflight"] = None
                    current["heartbeat_at"] = now
                    current["error"] = None
                    current["active_provider"] = None
                    current["execution"] = None
                    current["executions"] = []
                    current["execution_outcome"] = None
                    current["attempt_resolution"] = None
                    current["verification_verdict"] = None
                    current["promotion_status"] = "NOT_CREATED"
                    current["candidate_status"] = None
                    current["candidate"] = None
                    current["candidate_commit_sha"] = None
                    current["candidate_tree_sha"] = None
                    current["candidate_ref"] = None
                    current["candidate_state_hash"] = None
                    current["verified_receipt_hash"] = None
                    current["salvage_commit_sha"] = None
                    current["salvage_ref"] = None
                    current["salvage_only"] = False
                    current["promotion_eligible"] = False
                    current["verified_receipt"] = None
                    current["promotion_packet"] = None
                    current["approved_binding"] = None
                    current["integration_branch"] = None
                    current["integration_base_sha"] = None
                    current["integration_result_sha"] = None
                    current["integration_receipt"] = None
                    current["final_disposition"] = None
                    current["terminal_status"] = None
                    current["cleanup_eligible"] = False
                    current["cleanup_decision"] = None
                    current["cleanup_blocker"] = None
                    current["cleanup_performed"] = False
                    current["cleanup_performed_at"] = None
                    current["state_retention_status"] = "ACTIVE"
                    current["archive_eligible"] = False
                    current["archive_location"] = None
                    current["merge_performed"] = False
                    current["push_performed"] = False
                self._mutate_state(contract.task_id, retry)
                return self._launch_worker(contract.task_id, attempt_id) or self._with_task_action(existing)
            return self.reconcile_task(contract.task_id) or existing
        return self._launch_worker(contract.task_id, attempt_id) or self._with_task_action(state)

    def dispose_candidate(
        self,
        task_id: str,
        *,
        disposition: str,
        superseded_by: Optional[str] = None,
    ) -> dict[str, Any]:
        disposition = disposition.upper()
        if disposition not in {"REJECTED", "SUPERSEDED"}:
            raise ValueError("candidate disposition must be REJECTED or SUPERSEDED")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("promotion_status") not in {"PENDING_HUMAN_APPROVAL", "APPROVED"}:
            raise RuntimeError("candidate is not pending disposition")
        candidate_record = {
            "candidate_commit": (state.get("promotion_packet") or {}).get("candidate_commit_sha"),
            "candidate_ref": state.get("candidate_ref"),
            "candidate_state_hash": (state.get("promotion_packet") or {}).get("candidate_state_hash"),
            "verified_receipt_hash": (state.get("promotion_packet") or {}).get("verified_receipt_hash"),
            "approval_binding": state.get("approved_binding"),
            "final_disposition": disposition,
            "supersedes": state.get("supersedes"),
            "superseded_by": superseded_by if disposition == "SUPERSEDED" else None,
        }
        return self._checkpoint(task_id, disposition, {
            "promotion_status": disposition,
            "candidate_status": disposition,
            "final_disposition": disposition,
            "superseded_by": superseded_by if disposition == "SUPERSEDED" else None,
            "candidate_history": [*state.get("candidate_history", []), candidate_record],
            "terminal_status": disposition,
            "cleanup_decision": state.get("cleanup_decision", "REMOVED"),
            "cleanup_performed": state.get("cleanup_performed", True),
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
        }, attempt_id=state.get("attempt_id")) or state

    def close_task_without_candidate(
        self,
        task_id: str,
        *,
        superseded_by: str,
    ) -> dict[str, Any]:
        if not superseded_by or not str(superseded_by).strip():
            raise ValueError("superseded_by evidence identifier is required and non-empty")
        superseded_by = str(superseded_by).strip()

        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")

        if state.get("status") not in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
            raise RuntimeError(f"task {task_id} is not in RETAINED_FOR_REVIEW or FINAL_BLOCK status")

        if state.get("promotion_status") != "NOT_CREATED":
            raise RuntimeError("promotion_status must be NOT_CREATED")

        packet = state.get("promotion_packet") or {}
        candidate_commit = packet.get("candidate_commit_sha") or state.get("candidate_commit_sha")
        candidate_ref = state.get("candidate_ref")
        candidate_dict = state.get("candidate") or {}
        candidate_created = (
            state.get("candidate_commit_created")
            or packet.get("candidate_commit_created")
            or candidate_dict.get("commit_created")
        )
        if (
            packet
            or candidate_commit
            or candidate_ref
            or candidate_created
        ):
            raise RuntimeError("task has candidate evidence present")

        worker_pid = state.get("worker_pid")
        if worker_pid and self._pid_alive(int(worker_pid)):
            raise RuntimeError("active worker process is running for task")

        child_pgid = state.get("worker_child_pgid")
        if child_pgid and self._pid_alive(int(child_pgid)):
            raise RuntimeError("active worker child process is running for task")

        contract = state.get("contract") or {}
        lease = state.get("lease") or {}
        target_raw = state.get("target_worktree") or lease.get("target_worktree") or contract.get("target_repo_root")
        cleanup_values: dict[str, Any] = {
            "cleanup_decision": state.get("cleanup_decision") or "ALREADY_REMOVED",
            "cleanup_eligible": state.get("cleanup_eligible", True),
            "cleanup_performed": state.get("cleanup_performed", False),
            "cleanup_performed_at": state.get("cleanup_performed_at"),
        }
        if target_raw:
            target_path = Path(str(target_raw)).expanduser().resolve()
            controller_raw = state.get("controller_worktree") or contract.get("controller_repo_root")
            lease_object = TargetWorktreeLease(**dict(lease)) if lease else None
            if target_path.exists() and (not controller_raw or not lease_object):
                raise RuntimeError(f"recorded Target path exists: {target_path}")
            if target_path.exists() and controller_raw and lease_object:
                controller_path = Path(str(controller_raw)).expanduser().resolve()
                if not controller_path.is_dir():
                    raise RuntimeError(f"recorded Target path exists: {target_path}")
                manager = WorktreeManager(
                    root_dir=str(contract.get("target_worktree_root") or target_path.parent)
                )
                entry = manager._worktree_entry(controller_path, target_path)
                if entry is not None:
                    if state.get("status") != "RETAINED_FOR_REVIEW":
                        raise RuntimeError(f"recorded Target path exists: {target_path}")
                    has_recorded_salvage = bool(
                        state.get("salvage_commit_sha") and state.get("salvage_ref")
                    )
                    if not manager._status_bytes(target_path) and not has_recorded_salvage:
                        raise RuntimeError(f"recorded Target path exists: {target_path}")
                    self._require_integrated_replacement(task_id, superseded_by)
                    salvage = {
                        "salvage_commit_sha": state.get("salvage_commit_sha"),
                        "salvage_ref": state.get("salvage_ref"),
                        "salvage_only": state.get("salvage_only"),
                        "promotion_eligible": state.get("promotion_eligible"),
                    }
                    try:
                        if not salvage["salvage_commit_sha"] or not salvage["salvage_ref"]:
                            salvage = manager.create_salvage_snapshot(
                                self._contract_from_state(state),
                                lease_object,
                                str(state.get("attempt_id") or ""),
                            )
                        elif salvage["salvage_only"] is not True or salvage["promotion_eligible"] is not False:
                            raise RuntimeError("recorded salvage metadata is invalid")
                        self._checkpoint(
                            task_id,
                            "RETAINED_FOR_REVIEW",
                            {
                                **salvage,
                                "promotion_status": "NOT_CREATED",
                                "superseded_by": superseded_by,
                                "cleanup_decision": "SALVAGED",
                                "cleanup_blocker": None,
                                "cleanup_performed": False,
                                "cleanup_eligible": False,
                                "state_retention_status": "TERMINAL",
                            },
                            attempt_id=state.get("attempt_id"),
                        )
                        cleanup = manager.cleanup_terminal_target(
                            self._contract_from_state(state),
                            lease_object,
                            salvage_commit=str(salvage["salvage_commit_sha"]),
                            salvage_ref=str(salvage["salvage_ref"]),
                        )
                    except Exception as exc:
                        retained = self._checkpoint(
                            task_id,
                            "RETAINED_FOR_REVIEW",
                            {
                                **salvage,
                                "promotion_status": "NOT_CREATED",
                                "superseded_by": superseded_by,
                                "cleanup_decision": "CLEANUP_BLOCKED",
                                "cleanup_blocker": str(exc),
                                "cleanup_performed": False,
                                "cleanup_eligible": False,
                                "state_retention_status": "TERMINAL",
                            },
                            attempt_id=state.get("attempt_id"),
                        ) or state
                        return retained
                    if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                        return self._checkpoint(
                            task_id,
                            "RETAINED_FOR_REVIEW",
                            {
                                **salvage,
                                "promotion_status": "NOT_CREATED",
                                "superseded_by": superseded_by,
                                "cleanup_decision": cleanup.decision,
                                "cleanup_blocker": cleanup.blocker,
                                "cleanup_performed": cleanup.performed,
                                "cleanup_eligible": cleanup.eligible,
                                "state_retention_status": "TERMINAL",
                            },
                            attempt_id=state.get("attempt_id"),
                        ) or state
                    cleanup_values = {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                        **salvage,
                    }
                else:
                    cleanup = manager.cleanup_terminal_target(
                        self._contract_from_state(state),
                        lease_object,
                    )
                    if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                        raise RuntimeError(f"recorded Target path exists: {target_path}")
                    cleanup_values = {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                    }

        return self._checkpoint(
            task_id,
            "SUPERSEDED",
            {
                "promotion_status": "NOT_CREATED",
                "final_disposition": "SUPERSEDED",
                "superseded_by": superseded_by,
                "terminal_status": "SUPERSEDED",
                "state_retention_status": "TERMINAL",
                "archive_eligible": True,
                "merge_performed": False,
                "push_performed": False,
                **cleanup_values,
            },
            attempt_id=state.get("attempt_id"),
        ) or state

    close_without_candidate = close_task_without_candidate

    def close_retained_without_candidate(
        self,
        task_id: str,
        *,
        superseded_by: str,
    ) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")

        if state.get("status") != "RETAINED_FOR_REVIEW":
            raise RuntimeError(f"task {task_id} is not in RETAINED_FOR_REVIEW status")

        return self.close_task_without_candidate(task_id, superseded_by=superseded_by)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") in TERMINAL_STATUSES:
            return state
        pid = state.get("worker_pid")
        if pid and self._pid_alive(int(pid)):
            raise RuntimeError("active process must stop before cancellation cleanup")
        cancelled = self._checkpoint(task_id, "CANCELLED", {
            "promotion_status": "CANCELLED",
            "terminal_status": "CANCELLED",
            "final_disposition": "CANCELLED",
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
            "push_performed": False,
        }, attempt_id=state.get("attempt_id")) or state
        result = self.cleanup_tasks(task_id=task_id, dry_run=False)
        return self._read_state(task_id) or {**cancelled, "cleanup": result}

    def lifecycle_status(self) -> dict[str, Any]:
        states = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.state_dir.glob("*.json"))] if self.state_dir.exists() else []
        return {
            "canonical_state_root": str(self.state_dir),
            "tasks": len(states),
            "active_tasks": sum(state.get("status") not in TERMINAL_STATUSES for state in states),
            "active_targets": sum(bool((state.get("lease") or {}).get("target_worktree")) and state.get("status") not in TERMINAL_STATUSES for state in states),
        }

    def cleanup_tasks(self, *, task_id: Optional[str] = None, dry_run: bool = True) -> dict[str, Any]:
        ids = [task_id] if task_id else [path.stem for path in sorted(self.state_dir.glob("*.json"))]
        decisions = []
        for item in ids:
            state = self._read_state(item) or {}
            if not state:
                decisions.append({"task_id": item, "cleanup_decision": "ALREADY_REMOVED", "cleanup_blocker": "task state not found", "cleanup_performed": False})
                continue
            if state.get("status") == "RETAINED_FOR_REVIEW":
                decision = {
                    "task_id": item, "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                    "cleanup_blocker": state.get("cleanup_blocker") or "RETAINED_FOR_REVIEW",
                    "cleanup_performed": False, "cleanup_eligible": False,
                }
                decisions.append(decision)
                if not dry_run:
                    self._checkpoint(item, "RETAINED_FOR_REVIEW", decision, attempt_id=state.get("attempt_id"))
                continue
            if state.get("status") not in TERMINAL_STATUSES and state.get("status") not in {"CANDIDATE_COMMITTED", "TARGET_CLEANED", "PENDING_HUMAN_APPROVAL"}:
                decisions.append({"task_id": item, "status": state.get("status"), "cleanup_decision": "BLOCKED_BY_PROCESS", "cleanup_blocker": "task is active", "cleanup_performed": False})
                continue
            if not state.get("lease"):
                decision = {"task_id": item, "status": state.get("status"), "cleanup_decision": "ALREADY_REMOVED", "cleanup_blocker": None, "cleanup_performed": False, "cleanup_eligible": True}
                decisions.append(decision)
                if not dry_run:
                    self._checkpoint(item, str(state.get("status")), decision, attempt_id=state.get("attempt_id"))
                continue
            contract = self.build_contract(state["request"])
            lease = TargetWorktreeLease(**state["lease"])
            packet = state.get("promotion_packet") or {}
            binding = state.get("approved_binding") or {}
            if state.get("promotion_status") in {"APPROVED", "INTEGRATED"} and any(
                binding.get(field) != packet.get(field)
                for field in (
                    "candidate_commit_sha", "candidate_tree_sha",
                    "candidate_state_hash", "verified_receipt_hash",
                )
            ):
                decisions.append({
                    "task_id": item, "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                    "cleanup_blocker": "approval binding mismatch",
                    "cleanup_performed": False, "cleanup_eligible": False,
                })
                continue
            cleanup = WorktreeManager(root_dir=contract.target_worktree_root).cleanup_terminal_target(
                contract,
                lease,
                candidate_commit=packet.get("candidate_commit_sha"),
                candidate_ref=state.get("candidate_ref"),
                dry_run=dry_run,
            )
            decision = {
                "task_id": item,
                "status": state.get("status"),
                "cleanup_decision": cleanup.decision,
                "cleanup_blocker": cleanup.blocker,
                "cleanup_performed": cleanup.performed,
                "cleanup_eligible": cleanup.eligible,
                "cleanup_performed_at": _utc_now() if cleanup.performed else None,
            }
            decisions.append(decision)
            if not dry_run:
                terminal = "RETAINED_FOR_REVIEW" if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES" else str(state.get("status"))
                self._checkpoint(item, terminal, decision, attempt_id=state.get("attempt_id"))
        return {"dry_run": dry_run, "decisions": decisions}

    def archive_states(self, *, dry_run: bool = True) -> dict[str, Any]:
        archive_root = self._archive_root()
        entries = []
        for path in sorted(self.state_dir.glob("*.json")) if self.state_dir.exists() else []:
            payload = path.read_bytes()
            state = json.loads(payload)
            if state.get("status") not in {"FINAL_BLOCK", "INTEGRATED", "REJECTED", "SUPERSEDED", "CANCELLED"}:
                continue
            digest = hashlib.sha256(payload).hexdigest()
            destination = archive_root / path.name
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                attempt_id = str(state.get("attempt_id") or "unknown")
                destination = archive_root / f"{path.stem}--attempt-{attempt_id}.json"
            entries.append({
                "task_id": path.stem,
                "terminal_status": state.get("terminal_status") or state.get("status"),
                "candidate_commit": (state.get("promotion_packet") or {}).get("candidate_commit_sha"),
                "source": str(path),
                "archive_location": str(destination),
                "receipt_hash": digest,
                "archive_time": state.get("updated_at"),
            })
        manifest_bytes = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = archive_root / f"manifest-{manifest_hash}.json"
        if not dry_run and entries:
            archive_root.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                source = Path(entry["source"])
                destination = Path(entry["archive_location"])
                if destination.exists():
                    if hashlib.sha256(destination.read_bytes()).hexdigest() != entry["receipt_hash"]:
                        raise RuntimeError(f"archive receipt hash mismatch: {destination}")
                    source.unlink(missing_ok=True)
                else:
                    source.replace(destination)
                if hashlib.sha256(destination.read_bytes()).hexdigest() != entry["receipt_hash"]:
                    raise RuntimeError(f"archive receipt verification failed: {destination}")
            manifest_payload = {
                "schema": "nexus.self_hosted_state_archive_manifest.v1",
                "manifest_hash": manifest_hash,
                "entries": entries,
            }
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=archive_root,
                prefix=".manifest.", suffix=".tmp", delete=False,
            ) as handle:
                json.dump(manifest_payload, handle, sort_keys=True, indent=2)
                handle.write("\n")
                temporary = Path(handle.name)
            temporary.replace(manifest_path)
        return {"dry_run": dry_run, "entries": entries, "manifest_hash": manifest_hash, "manifest_path": str(manifest_path)}

    def integrate_approved(self, task_id: str, *, integration_branch: str = "nexus/integration") -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("promotion_status") == "INTEGRATED":
            return state
        if state.get("promotion_status") not in {"APPROVED", "INTEGRATION_FAILED"}:
            raise RuntimeError("exact approved binding is required before integration")
        if state.get("promotion_status") == "INTEGRATION_FAILED" and state.get("merge_performed"):
            raise RuntimeError("cannot retry an integration that already performed a merge")
        root = Path((state.get("contract") or {})["target_worktree_root"]).resolve() / "integrations"
        self._checkpoint(task_id, "INTEGRATING", {
            "integration_branch": integration_branch,
            "push_performed": False,
        }, attempt_id=state.get("attempt_id"))
        integrating = self._read_state(task_id) or state
        try:
            receipt = ControlledIntegrationManager(integration_root=root).integrate_task_state(integrating, integration_branch=integration_branch)
        except Exception as exc:
            self._checkpoint(task_id, "INTEGRATION_FAILED", {
                "promotion_status": "INTEGRATION_FAILED",
                "integration_branch": integration_branch,
                "integration_error": str(exc),
                "terminal_status": "INTEGRATION_FAILED",
                "final_disposition": "INTEGRATION_FAILED",
                "state_retention_status": "TERMINAL",
                "archive_eligible": True,
                "merge_performed": False,
                "push_performed": False,
            }, attempt_id=state.get("attempt_id"))
            raise
        return self._checkpoint(task_id, "INTEGRATED", {
            "promotion_status": "INTEGRATED",
            "integration_branch": receipt.integration_branch,
            "integration_result_sha": receipt.integration_commit_sha,
            "integration_base_sha": getattr(receipt, "integration_base_sha", None),
            "integration_receipt": receipt,
            "terminal_status": "INTEGRATED",
            "candidate_status": "INTEGRATED",
            "final_disposition": "INTEGRATED",
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
            "merge_performed": True,
            "push_performed": False,
        }, attempt_id=state.get("attempt_id")) or state

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        return self.reconcile_task(task_id)

    def get_receipt(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self.get_task(task_id)
        if state is None:
            return None
        contract = state.get("contract") or {}
        lease = state.get("lease") or {}
        packet = state.get("promotion_packet") or {}
        archived_path, _ = self._latest_archived_state(task_id)
        return {
            "task_id": task_id,
            "attempt_id": state.get("attempt_id"),
            "status": state.get("status"),
            "submitted_at": state.get("submitted_at"),
            "contract_hash": state.get("contract_hash"),
            "controller_worktree": state.get("controller_worktree") or contract.get("controller_repo_root"),
            "controller_revision": state.get("controller_revision") or contract.get("controller_revision"),
            "controller_status_sha256": state.get("controller_status_sha256") or lease.get("controller_status_sha256"),
            "target_worktree": state.get("target_worktree") or lease.get("target_worktree") or contract.get("target_repo_root"),
            "target_initial_revision": state.get("target_initial_revision") or lease.get("initial_head") or contract.get("target_base_revision"),
            "target_branch": state.get("target_branch") or lease.get("target_branch"),
            "target_created_at": state.get("target_created_at"),
            "worker_provider": state.get("worker_provider"),
            "worker_pid": state.get("worker_pid"),
            "heartbeat_at": state.get("heartbeat_at"),
            "execution_outcome": state.get("execution_outcome"),
            "verification_verdict": state.get("verification_verdict"),
            "candidate_commit_sha": state.get("candidate_commit_sha") or packet.get("candidate_commit_sha"),
            "candidate_tree_sha": state.get("candidate_tree_sha") or packet.get("candidate_tree_sha"),
            "candidate_ref": state.get("candidate_ref"),
            "candidate_state_hash": state.get("candidate_state_hash") or packet.get("candidate_state_hash"),
            "verified_receipt_hash": state.get("verified_receipt_hash") or packet.get("verified_receipt_hash"),
            "salvage_commit_sha": state.get("salvage_commit_sha"),
            "salvage_ref": state.get("salvage_ref"),
            "salvage_only": state.get("salvage_only", False),
            "promotion_eligible": state.get("promotion_eligible", False),
            "promotion_status": state.get("promotion_status"),
            "approved_binding": state.get("approved_binding"),
            "integration_branch": state.get("integration_branch"),
            "integration_base_sha": state.get("integration_base_sha"),
            "integration_result_sha": state.get("integration_result_sha"),
            "terminal_status": state.get("terminal_status"),
            "superseded_by": state.get("superseded_by"),
            "cleanup_eligible": state.get("cleanup_eligible"),
            "cleanup_decision": state.get("cleanup_decision"),
            "cleanup_blocker": state.get("cleanup_blocker"),
            "cleanup_performed": state.get("cleanup_performed"),
            "cleanup_performed_at": state.get("cleanup_performed_at"),
            "state_retention_status": "ARCHIVED" if archived_path is not None else state.get("state_retention_status"),
            "archive_eligible": state.get("archive_eligible"),
            "archive_location": str(archived_path) if archived_path is not None else state.get("archive_location"),
            "execution": state.get("execution"),
            "candidate": state.get("candidate"),
            "verified_receipt": state.get("verified_receipt"),
            "error": state.get("error"),
        }

    def get_promotion_packet(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self.get_task(task_id)
        if state is None:
            return None
        return {
            "task_id": task_id,
            "promotion_status": state.get("promotion_status"),
            "promotion_packet": state.get("promotion_packet"),
            "candidate_commit_created": state.get("candidate_commit_created", False),
            "public_claim_allowed": state.get("public_claim_allowed", False),
            "production_ready": state.get("production_ready", False),
            "merge_performed": state.get("merge_performed", False),
            "push_performed": state.get("push_performed", False),
        }

    def approve_promotion(
        self,
        task_id: str,
        *,
        candidate_commit_sha: str,
        candidate_tree_sha: str,
        candidate_state_hash: str,
        verified_receipt_hash: str,
    ) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        packet = state.get("promotion_packet") or {}
        expected = {
            "candidate_commit_sha": candidate_commit_sha,
            "candidate_tree_sha": candidate_tree_sha,
            "candidate_state_hash": candidate_state_hash,
            "verified_receipt_hash": verified_receipt_hash,
        }

        valid = bool(packet) and not any(packet.get(k) != v for k, v in expected.items())
        status = "APPROVED" if valid else "APPROVAL_INVALIDATED"
        return self._checkpoint(task_id, status, {
            "promotion_status": status,
            "candidate_status": status,
            "approved_binding": expected if valid else None,
            "approval_error": None if valid else "promotion binding does not match candidate packet",
            "merge_performed": False,
            "push_performed": False,
        }, attempt_id=state.get("attempt_id")) or state
