"""Durable, restartable service facade for the self-hosted MCP surface."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import stat
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
from nexus.orchestrator.candidate_commit import CandidateCommitter, PromotionApprovalPacket
from nexus.orchestrator.candidate_verifier import CandidateVerifier, VerifiedCandidateReceipt
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
    "INTEGRATED", "INTEGRATION_FAILED", "CANCELLED", "REHEARSAL_VERIFIED",
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
def resolve_canonical_target_roots(
    task_id: str,
    campaign_id: Optional[str] = None,
    requested_target_worktree_root: Optional[str] = None,
    requested_target_repo_root: Optional[str] = None,
) -> tuple[Path, Path]:
    override = os.getenv("NEXUS_TARGET_ROOT_OVERRIDE", "").strip()
    if override:
        base_worktree_root = Path(override).expanduser().resolve()
    elif requested_target_worktree_root and "/private/tmp" not in requested_target_worktree_root and "/tmp" not in requested_target_worktree_root:
        base_worktree_root = Path(requested_target_worktree_root).expanduser().resolve()
    else:
        workspace_root = Path.cwd().resolve()
        if "nexus-worktrees" in workspace_root.parts:
            idx = workspace_root.parts.index("nexus-worktrees")
            base_worktree_root = Path(*workspace_root.parts[:idx + 1]) / "runtime-targets"
        else:
            base_worktree_root = workspace_root / "nexus-worktrees" / "runtime-targets"
        if campaign_id:
            base_worktree_root = base_worktree_root / campaign_id

    if requested_target_repo_root and "/private/tmp" not in requested_target_repo_root and "/tmp" not in requested_target_repo_root:
        target_repo_root = Path(requested_target_repo_root).expanduser().resolve()
    else:
        target_repo_root = base_worktree_root / task_id

    return base_worktree_root, target_repo_root


def validate_task_card_binding(contract: ArchitectTaskContract, request: Mapping[str, Any], *, is_ephemeral: bool = False) -> None:
    if request.get("allow_unbound_test_identity") is True and not is_ephemeral:
        raise RuntimeError("TASK_CARD_BINDING_MISMATCH: allow_unbound_test_identity is only permitted when ephemeral=True")

    allow_unbound = (
        is_ephemeral
        and not request.get("task_card_required")
        and not request.get("lifecycle_identity_required")
        and request.get("allow_unbound_test_identity") is not False
    )

    task_id = contract.task_id
    card_path_str = request.get("task_card_path")
    card_path = None
    if card_path_str:
        card_path = Path(card_path_str).expanduser().resolve()
    else:
        possible = Path.cwd() / f"tasks/{task_id}.md"
        if possible.exists():
            card_path = possible
        else:
            matches = list(Path.cwd().glob(f"tasks/*/{task_id}.md")) + list(Path.cwd().glob(f"tasks/*/*{task_id}*.md"))
            card_path = matches[0] if matches else None

    if not card_path or not card_path.exists():
        if not allow_unbound:
            raise RuntimeError(f"TASK_CARD_BINDING_MISMATCH: task card does not exist for task_id '{task_id}'")
        return

    content = card_path.read_text(encoding="utf-8")
    if f"task_id: `{task_id}`" not in content and f"task_id: {task_id}" not in content and f"`{task_id}`" not in content and f"task_id: '{task_id}'" not in content:
        raise RuntimeError(f"TASK_CARD_BINDING_MISMATCH: task card task_id does not match lifecycle task_id '{task_id}'")

    if "AUTO_CHAIN: true" in content or "AUTO_CHAIN=true" in content:
        raise RuntimeError("TASK_CARD_BINDING_MISMATCH: AUTO_CHAIN must be false")


def resolve_lifecycle_identity(contract: ArchitectTaskContract, request: Mapping[str, Any], *, is_ephemeral: bool = False) -> dict[str, Any]:
    if request.get("allow_unbound_test_identity") is True and not is_ephemeral:
        raise RuntimeError("LIFECYCLE_REVISION_MISMATCH: allow_unbound_test_identity is only permitted when ephemeral=True")

    allow_unbound = (
        is_ephemeral
        and not request.get("lifecycle_identity_required")
        and not request.get("task_card_required")
        and request.get("allow_unbound_test_identity") is not False
    )

    source_root = Path(__file__).resolve().parents[2]
    current_rev = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, capture_output=True, text=True
    ).stdout.strip()
    req_rev = request.get("required_lifecycle_revision")
    if req_rev:
        if current_rev != req_rev and not current_rev.startswith(req_rev):
            raise RuntimeError(f"LIFECYCLE_REVISION_MISMATCH: current revision {current_rev} does not match required {req_rev}")

    card_path_str = request.get("task_card_path")
    card_path = None
    if card_path_str:
        card_path = Path(card_path_str).expanduser().resolve()
    else:
        task_id = contract.task_id
        possible = Path.cwd() / f"tasks/{task_id}.md"
        if possible.exists():
            card_path = possible
        else:
            matches = list(Path.cwd().glob(f"tasks/*/{task_id}.md")) + list(Path.cwd().glob(f"tasks/*/*{task_id}*.md"))
            card_path = matches[0] if matches else None

    card_path_res = str(card_path.resolve()) if card_path and card_path.exists() else None
    card_hash = None
    if card_path and card_path.exists():
        card_hash = subprocess.run(
            ["git", "hash-object", str(card_path)], capture_output=True, text=True
        ).stdout.strip()

    if not allow_unbound:
        if not current_rev or not card_path_res or not card_hash or not contract.controller_revision:
            raise RuntimeError("LIFECYCLE_REVISION_MISMATCH: missing required lifecycle identity binding fields")

    return {
        "lifecycle_revision": current_rev,
        "lifecycle_executable_path": str(Path(sys.executable).resolve()),
        "worker_module_path": str(Path(__file__).resolve()),
        "controller_revision": contract.controller_revision,
        "task_card_path": card_path_res,
        "task_card_hash": card_hash,
    }


def validate_lifecycle_revision(contract: ArchitectTaskContract, request: Mapping[str, Any]) -> None:
    resolve_lifecycle_identity(contract, request)


def check_fast_lane_eligible(contract: ArchitectTaskContract, request: Optional[Mapping[str, Any]] = None) -> bool:
    req = request or {}
    allowed_files = getattr(contract, "allowed_files", ()) or ()
    verifier_commands = getattr(contract, "verifier_commands", ()) or ()
    max_provider_calls = getattr(contract, "maximum_provider_calls", 1)
    max_deleted = getattr(contract, "maximum_deleted_files", 0)

    if len(allowed_files) > 4:
        return False
    if max_provider_calls > 1:
        return False
    if not verifier_commands:
        return False
    if getattr(contract, "deletion_allowed", False) or max_deleted > 0:
        return False
    if req.get("migration_authority") or req.get("schema_authority"):
        return False
    if req.get("route_authority_mutation"):
        return False
    if req.get("security_policy_weakening"):
        return False
    if getattr(contract, "public_claim_allowed", False) or getattr(contract, "production_ready", False):
        return False
    if getattr(contract, "controller_clean", None) is False or getattr(contract, "target_isolated", None) is False:
        return False

    return True


CANONICAL_SOURCE_ROOT = Path("/Users/jameschen/Workspace/nexus")
CANONICAL_SOURCE_BRANCH = "nexus/integration/main"


def resolve_execution_lane(request: Mapping[str, Any]) -> dict[str, Any]:
    """Classify ordinary primary-agent work without allocating a Target."""
    requested = str(request.get("execution_lane", "ISOLATED_TARGET")).strip().upper()
    if requested not in {"DIRECT_CANONICAL", "ISOLATED_TARGET"}:
        raise ValueError("execution_lane must be DIRECT_CANONICAL or ISOLATED_TARGET")
    if requested == "ISOLATED_TARGET":
        return {
            "execution_lane": "ISOLATED_TARGET",
            "eligible": True,
            "blockers": [],
            "next_action": "prepare_governed_target",
        }

    blockers: list[str] = []
    controller = Path(str(request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
    if controller != CANONICAL_SOURCE_ROOT:
        blockers.append("controller_is_not_canonical_source")
    if request.get("primary_agent") is not True:
        blockers.append("primary_agent_attestation_required")
    worker = str(request.get("worker", "primary")).strip().lower()
    if worker not in {"", "primary", "codex"}:
        blockers.append("delegated_worker_forbidden")
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if branch != CANONICAL_SOURCE_BRANCH:
            blockers.append("canonical_branch_mismatch")
        dirty = subprocess.run(
            ["git", "status", "--porcelain=v1"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if dirty:
            blockers.append("canonical_checkout_dirty")
    except OSError:
        blockers.append("canonical_git_probe_failed")
    if len(request.get("allowed_files") or []) > 4:
        blockers.append("allowed_file_limit_exceeded")
    if request.get("authorized_deletions"):
        blockers.append("deletions_forbidden")
    for flag in ("migration_authority", "schema_authority", "route_authority_mutation", "security_policy_weakening", "public_claim_allowed", "production_ready"):
        if request.get(flag):
            blockers.append(f"{flag}_forbidden")
    return {
        "execution_lane": "DIRECT_CANONICAL" if not blockers else "ISOLATED_TARGET",
        "eligible": not blockers,
        "blockers": blockers,
        "next_action": "edit_canonical_checkout" if not blockers else "prepare_governed_target",
    }


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
            or superseded_by == task_id
            or replacement.get("task_id") != superseded_by
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

    def _read_state_snapshot(self, task_id: str) -> Optional[dict[str, Any]]:
        """Read a durable snapshot without creating or acquiring the state lock.

        Read-only status and workspace inventory surfaces must not mutate the
        lifecycle store. State writes use atomic ``replace`` semantics, so a
        direct read observes either the previous complete JSON or the next
        complete JSON; a concurrent disappearance is treated as absent.
        """
        path = self._state_path(task_id)
        try:
            payload = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            _, archived = self._latest_archived_state(task_id)
            return archived
        return self._with_task_action(json.loads(payload))

    def _promotion_authority_error(
        self,
        *,
        contract: Optional[ArchitectTaskContract] = None,
        request: Optional[Mapping[str, Any]] = None,
    ) -> Optional[str]:
        """Return a fail-closed reason when a task cannot become promotable.

        Ephemeral services are test/rehearsal surfaces.  A production-bound
        task (one with a task card or lifecycle identity requirement) must be
        backed by the canonical state root and a durable, existing Controller.
        This prevents a temporary rehearsal receipt from becoming an
        approval/integration authority by accident.
        """
        req = request or {}
        production_bound = bool(
            req.get("task_card_required") or req.get("lifecycle_identity_required")
        )
        if self.ephemeral and production_bound:
            return "EPHEMERAL_PROMOTION_FORBIDDEN: rehearsal state cannot become a promotable Candidate"
        if not production_bound or contract is None:
            return None
        if self.state_dir != self.canonical_state_dir():
            return "CANONICAL_STATE_REQUIRED: production Candidate must use the canonical state root"
        controller = Path(contract.controller_repo_root).expanduser().resolve()
        if not controller.is_dir():
            return f"CONTROLLER_MISSING: {controller}"
        temporary_roots = (Path("/tmp"), Path("/private/tmp"), Path("/private/var/folders"))
        if any(controller == root or root in controller.parents for root in temporary_roots):
            return f"DURABLE_CONTROLLER_REQUIRED: temporary Controller is not promotable: {controller}"
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=controller,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return f"CONTROLLER_PROBE_FAILED: {exc}"
        if result.returncode != 0 or Path(result.stdout.strip()).resolve() != controller:
            return f"CONTROLLER_NOT_A_REPOSITORY: {controller}"
        try:
            current_revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=controller,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        except OSError as exc:
            return f"CONTROLLER_REVISION_PROBE_FAILED: {exc}"
        if contract.controller_revision and current_revision != contract.controller_revision:
            return (
                "CONTROLLER_REVISION_MISMATCH: "
                f"expected {contract.controller_revision}, got {current_revision}"
            )
        return None

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
        authorized_deletions = [str(item) for item in request.get("authorized_deletions", [])]
        base_worktree_root, target_repo_root = resolve_canonical_target_roots(
            task_id=task_id,
            campaign_id=request.get("campaign_id"),
            requested_target_worktree_root=request.get("target_worktree_root"),
            requested_target_repo_root=request.get("target_repo_root"),
        )
        controller_repo_root = request.get("controller_repo_root")
        if not controller_repo_root:
            controller_repo_root = str(Path.cwd().resolve())
        else:
            controller_repo_root = str(Path(controller_repo_root).expanduser().resolve())

        controller_revision = request.get("controller_revision")
        if not controller_revision:
            res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=controller_repo_root, capture_output=True, text=True)
            controller_revision = res.stdout.strip() if res.returncode == 0 else "HEAD"
        else:
            controller_revision = str(controller_revision)

        target_base_revision = request.get("target_base_revision")
        if not target_base_revision:
            target_base_revision = controller_revision
        else:
            target_base_revision = str(target_base_revision)

        return ArchitectTaskContract(
            task_id=task_id,
            objective=what,
            goal=DevelopmentGoal(what=what, why=why),
            architecture_decisions=decision_models,
            acceptance_profile=AcceptanceProfile(
                verifier_commands=verifier_commands,
                protected_contracts=protected_contracts,
                authorized_deletions=authorized_deletions,
                required_evidence=["candidate_state_hash", "controller_unchanged", "verified_candidate_receipt"],
            ),
            human_approval_policy=HumanApprovalPolicy(
                approver_roles=list(request.get("approver_roles", ["James"])),
            ),
            controller_revision=controller_revision,
            target_base_revision=target_base_revision,
            controller_repo_root=controller_repo_root,
            target_repo_root=str(target_repo_root),
            target_worktree_root=str(base_worktree_root),
            allowed_files=list(request["allowed_files"]),
            forbidden_files=list(request.get("forbidden_files", [])),
            authorized_deletions=authorized_deletions,
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
        is_fast_lane = check_fast_lane_eligible(contract, request)
        fast_lane_values = {
            "execution_lane": "FAST_LANE" if is_fast_lane else "STANDARD",
            "fast_lane_eligible": is_fast_lane,
            "maximum_provider_calls": 1 if is_fast_lane else contract.maximum_provider_calls,
            "maximum_replans": 0 if is_fast_lane else 3,
            "fallback_disabled": is_fast_lane,
        }

        if status == "SUBMITTED":
            provider, preflight = self._select_initial_provider(contract)
            lease = controller.prepare_task(contract)
            update(
                "TARGET_LEASED",
                {
                    "lease": lease,
                    "worker_preflight": preflight,
                    "active_provider": provider,
                    **fast_lane_values,
                },
            )
            update("WORKER_RUNNING", {"active_provider": provider, **fast_lane_values})
            state = self._read_state(task_id) or {}
            status = "WORKER_RUNNING"
        elif status == "WORKER_ESCALATING":
            if is_fast_lane:
                raise RuntimeError("Fast Lane escalation is forbidden")
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
                        **fast_lane_values,
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

            if is_fast_lane:
                raise RuntimeError(latest.failure_reason or f"Fast Lane provider execution failed with outcome {latest.outcome}; escalation/fallback disabled")

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

        authority_error = self._promotion_authority_error(
            contract=contract,
            request=request,
        )
        if authority_error:
            cleanup = manager.cleanup_terminal_target(contract, lease)
            cleanup_ok = cleanup.decision in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            terminal_status = (
                "REHEARSAL_VERIFIED"
                if self.ephemeral and cleanup_ok
                else "RETAINED_FOR_REVIEW"
                if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES"
                else "FINAL_BLOCK"
            )
            update(terminal_status, {
                "error": authority_error,
                "candidate_status": "REHEARSAL_VERIFIED" if self.ephemeral and cleanup_ok else terminal_status,
                "promotion_status": "NOT_CREATED",
                "promotion_eligible": False,
                "verification_verdict": "PROVEN" if self.ephemeral and cleanup_ok else "FAILED",
                "verified_receipt": verified,
                "attempt_resolution": resolution,
                "cleanup_decision": cleanup.decision,
                "cleanup_blocker": cleanup.blocker,
                "cleanup_performed": cleanup.performed,
                "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                "cleanup_eligible": cleanup.eligible,
                "terminal_status": terminal_status,
                "state_retention_status": "TERMINAL",
                "archive_eligible": False,
            })
            return {
                "execution": execution,
                "candidate": candidate,
                "verified_receipt": verified,
                "attempt_resolution": resolution,
                "candidate_status": "REHEARSAL_VERIFIED" if self.ephemeral and cleanup_ok else terminal_status,
                "promotion_status": "NOT_CREATED",
                "promotion_eligible": False,
                "cleanup_decision": cleanup.decision,
                "cleanup_performed": cleanup.performed,
                "terminal_status": terminal_status,
                "error": authority_error,
            }

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
        try:
            candidate_ref = manager.protect_candidate(contract, lease, packet.candidate_commit_sha)
            update("CANDIDATE_REF_PROTECTED", {"candidate_ref": candidate_ref})
        except Exception as exc:
            update("RETAINED_FOR_REVIEW", {
                "error": f"candidate ref protection failed: {exc}",
                "promotion_status": "NOT_CREATED",
                "candidate_status": "RETAINED_FOR_REVIEW",
                "terminal_status": "RETAINED_FOR_REVIEW",
                "state_retention_status": "ACTIVE",
                "recovery_action": "recover_retained_candidate",
            })
            raise RuntimeError(f"candidate ref protection failed: {exc}")
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
                result = self._custom_runner(contract, state["request"], update)
            current = self._read_state(task_id) or {}
            if current.get("status") not in TERMINAL_STATUSES:
                final_status = "PENDING_HUMAN_APPROVAL" if result.get("promotion_status") == "PENDING_HUMAN_APPROVAL" else "CANDIDATE_COMMITTED"
                self._checkpoint(task_id, final_status, result, attempt_id=attempt_id)
        except Exception as exc:
            self._terminate_owned_processes(task_id, exclude_pid=owner_pid)
            current = self._read_state(task_id) or {}
            verified_rcpt = current.get("verified_receipt") or {}
            attempt_res = current.get("attempt_resolution") or {}
            is_verified = bool(verified_rcpt.get("verified")) and attempt_res.get("verdict") == "PROVEN"

            if is_verified:
                self._checkpoint(
                    task_id,
                    "RETAINED_FOR_REVIEW",
                    {
                        "error": str(exc),
                        "promotion_status": "NOT_CREATED",
                        "terminal_status": "RETAINED_FOR_REVIEW",
                        "state_retention_status": "ACTIVE",
                        "recovery_action": "recover_verified_uncommitted_candidate",
                        "cleanup_eligible": False,
                        "cleanup_performed": False,
                        "cleanup_decision": "PRESERVED_FOR_REVIEW",
                    },
                    attempt_id=attempt_id,
                )
            else:
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
                        manager = WorktreeManager(root_dir=contract.target_worktree_root)
                        cleanup = manager.cleanup_terminal_target(contract, lease)
                        cleanup_values.update({
                            "cleanup_decision": cleanup.decision,
                            "cleanup_blocker": cleanup.blocker,
                            "cleanup_performed": cleanup.performed,
                            "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                        })
                        cleanup_values["cleanup_eligible"] = cleanup.eligible
                        if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES":
                            cleanup_values["terminal_status"] = "RETAINED_FOR_REVIEW"
                            try:
                                salvage = manager.create_salvage_snapshot(contract, lease, attempt_id)
                                salvage_commit = str(salvage.get("salvage_commit_sha", "") or "")
                                salvage_ref = str(salvage.get("salvage_ref", "") or "")
                                cleanup = manager.cleanup_terminal_target(
                                    contract, lease,
                                    salvage_commit=salvage_commit,
                                    salvage_ref=salvage_ref,
                                )
                                cleanup_values.update({
                                    "cleanup_decision": cleanup.decision,
                                    "cleanup_blocker": cleanup.blocker,
                                    "cleanup_performed": cleanup.performed,
                                    "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                                    **salvage,
                                })
                                if cleanup.decision in {"REMOVED", "ALREADY_REMOVED"} and salvage_commit and salvage_ref:
                                    try:
                                        restore_result = manager.restore_task_branch_for_retry(
                                            contract, lease, salvage_commit, salvage_ref,
                                        )
                                        cleanup_values.update({
                                            "task_branch_restore_decision": restore_result["decision"],
                                            "task_branch_restored_to": restore_result["restored_to"],
                                            "task_branch_restore_performed": True,
                                            "task_branch_restore_verified": True,
                                            "terminal_status": "FINAL_BLOCK",
                                            "state_retention_status": "TERMINAL",
                                        })
                                    except Exception as restore_exc:
                                        cleanup_values.update({
                                            "task_branch_restore_decision": "RESTORE_BLOCKED",
                                            "task_branch_restore_performed": False,
                                            "task_branch_restore_verified": False,
                                            "terminal_status": "RETAINED_FOR_REVIEW",
                                        })
                            except Exception as salvage_exc:
                                cleanup_values.update({
                                    "cleanup_decision": "CLEANUP_BLOCKED",
                                    "cleanup_blocker": str(salvage_exc),
                                    "cleanup_performed": False,
                                    "cleanup_eligible": False,
                                })
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
        include_details: bool = False,
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
            # Waiting is a read-only operator surface.  Do not reconcile or
            # acquire the lifecycle write lock while polling durable state.
            state = self._read_state_snapshot(task_id)
            if state is not None:
                state = self._with_task_action(state)
            if state is None:
                return None
            envelope = state.get("task_action") or self._task_action_envelope(state)
            if envelope.get("action_state") != "IN_PROGRESS":
                result = {
                    **(state if include_details else {
                        "schema": "nexus.self_hosted_task_status.v1",
                        "task_id": state.get("task_id"),
                        "status": state.get("status"),
                        "promotion_status": state.get("promotion_status"),
                        "verification_verdict": state.get("verification_verdict"),
                        "task_action": envelope,
                    }),
                    "wait": {
                        "timed_out": False,
                        "timeout_seconds": timeout_seconds,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                }
                return result
            if time.monotonic() >= deadline:
                envelope = {**envelope, "wait_timed_out": True}
                return {
                    **(state if include_details else {
                        "schema": "nexus.self_hosted_task_status.v1",
                        "task_id": state.get("task_id"),
                        "status": state.get("status"),
                        "promotion_status": state.get("promotion_status"),
                        "verification_verdict": state.get("verification_verdict"),
                        "task_action": envelope,
                    }),
                    "task_action": envelope,
                    "wait": {
                        "timed_out": True,
                        "timeout_seconds": timeout_seconds,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                }
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    def list_actionable_tasks(self, *, include_details: bool = False) -> dict[str, Any]:
        """Return action envelopes without reconciling or mutating task state.

        The default response is intentionally compact.  Callers that need the
        full durable state must opt in with ``include_details=True`` or use
        ``get_task``/``get_receipt`` for one task.  This keeps status polling
        from repeatedly traversing Target worktrees and from creating hidden
        lifecycle mutations.
        """
        tasks = []
        for path in sorted(self.state_dir.glob("*.json")) if self.state_dir.exists() else []:
            state = self._read_state_snapshot(path.stem)
            if state is None:
                continue
            action = self._task_action_envelope(state)
            if action.get("attention_required") is True:
                if include_details:
                    tasks.append(state)
                else:
                    tasks.append({**action, "task_action": action})
        return {
            "schema": "nexus.self_hosted_actionable_tasks.v1",
            "actionable_count": len(tasks),
            "details_included": include_details,
            "tasks": tasks,
        }

    def _workspace_task_states(self) -> dict[str, dict[str, Any]]:
        """Load durable task snapshots without invoking reconciliation."""
        if not self.state_dir.exists():
            return {}
        states: dict[str, dict[str, Any]] = {}
        for path in sorted(self.state_dir.glob("*.json")):
            state = self._read_state_snapshot(path.stem)
            if state is not None:
                states[path.stem] = state
        return states

    def workspace_inventory(
        self,
        *,
        controller_root: Optional[str | Path] = None,
    ) -> dict[str, Any]:
        """Read-only inventory of registered worktrees and lifecycle ownership."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = WorktreeManager(root_dir=str(root.parent / "runtime-targets"), create_root=False)
        inventory = manager.get_workspace_inventory(
            controller_root=root,
            task_states=states,
        )
        return _jsonable(inventory)

    def state_root_inventory(self) -> dict[str, Any]:
        """Inventory canonical and nested lifecycle state without mutation."""
        canonical = self.canonical_state_dir()
        entries: list[dict[str, Any]] = []
        if canonical.exists():
            candidates = sorted(canonical.glob("**/*.json"))
        else:
            candidates = []
        for path in candidates:
            if path.name.startswith("manifest-"):
                continue
            try:
                raw = path.read_bytes()
                state = json.loads(raw)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(state, Mapping) or not state.get("task_id"):
                continue
            relative_parent = path.parent.relative_to(canonical)
            if str(relative_parent) == ".":
                authority = "CANONICAL_AUTHORITY"
            elif "nexus-state-archive" in path.parts:
                authority = "ARCHIVE_EVIDENCE"
            else:
                authority = "REHEARSAL_EVIDENCE"
            entries.append({
                "path": str(path),
                "authority": authority,
                "task_id": state.get("task_id"),
                "attempt_id": state.get("attempt_id"),
                "status": state.get("status"),
                "promotion_status": state.get("promotion_status"),
                "candidate_commit_sha": state.get("candidate_commit_sha"),
                "candidate_ref": state.get("candidate_ref"),
                "state_sha256": hashlib.sha256(raw).hexdigest(),
                "updated_at": state.get("updated_at"),
            })
        by_task: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            by_task.setdefault(str(entry["task_id"]), []).append(entry)
        canonical_authority_counts = {
            task_id: sum(1 for value in values if value["authority"] == "CANONICAL_AUTHORITY")
            for task_id, values in by_task.items()
        }
        conflicts = sorted(task_id for task_id, count in canonical_authority_counts.items() if count > 1)
        evidence_duplicates = sorted(task_id for task_id, values in by_task.items() if len(values) > 1 and task_id not in conflicts)
        return {
            "schema": "nexus.lifecycle_state_root_inventory.v1",
            "canonical_state_root": str(canonical),
            "entry_count": len(entries),
            "task_count": len(by_task),
            "conflict_task_ids": conflicts,
            "authority_conflict": bool(conflicts),
            "evidence_duplicate_task_ids": evidence_duplicates,
            "entries": entries,
            "inventory_sha256": hashlib.sha256(
                json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }

    def workspace_convergence_plan(
        self,
        *,
        controller_root: Optional[str | Path] = None,
        expected_controller_revision: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a stable dry-run plan; no state or workspace mutation occurs."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = WorktreeManager(root_dir=str(root.parent / "runtime-targets"), create_root=False)
        inventory = manager.get_workspace_inventory(
            controller_root=root,
            task_states=states,
        )
        expected = expected_controller_revision or inventory.controller_head
        plan = manager.plan_convergence(inventory, expected_controller_revision=expected)
        return _jsonable(plan)

    def workspace_slot_status(
        self,
        *,
        campaign_id: str = "default",
        slot_index: int = 0,
        controller_root: Optional[str | Path] = None,
    ) -> dict[str, Any]:
        """Read-only reusable-slot readiness check."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = WorktreeManager(root_dir=str(root.parent / "runtime-targets"), create_root=False)
        status = manager.get_reusable_slot_status(
            campaign_id=campaign_id,
            slot_index=slot_index,
            controller_root=root,
            task_states=states,
        )
        return _jsonable(status)

    def workspace_slot_prepare(
        self,
        request: Mapping[str, Any],
        *,
        campaign_id: str = "default",
        slot_index: int = 0,
    ) -> dict[str, Any]:
        """Prepare one reusable slot through WorktreeManager authority."""
        contract = self.build_contract(request)
        states = self._workspace_task_states()
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        prepared = manager.prepare_reusable_slot(
            contract,
            campaign_id=campaign_id,
            slot_index=slot_index,
            task_states=states,
        )
        return _jsonable(prepared)

    def apply_workspace_convergence(
        self,
        *,
        controller_root: Optional[str | Path] = None,
        expected_controller_revision: str,
        expected_plan_hash: str,
        apply: bool = False,
    ) -> dict[str, Any]:
        """Apply only lifecycle-bound terminal cleanup through existing authority.

        The default is a dry-run.  Unbound redundant worktrees remain blocked
        because they have no task contract through which existing cleanup
        authority can safely operate.
        """
        root = Path(controller_root or Path.cwd()).resolve()
        states = self._workspace_task_states()
        manager = WorktreeManager(root_dir=str(root.parent / "runtime-targets"))
        inventory = manager.get_workspace_inventory(controller_root=root, task_states=states)
        if inventory.controller_head != expected_controller_revision:
            raise RuntimeError(
                f"CONTROLLER_REVISION_DRIFT: current controller {inventory.controller_head} "
                f"does not match expected {expected_controller_revision}"
            )
        plan = manager.plan_convergence(
            inventory,
            expected_controller_revision=expected_controller_revision,
        )
        if plan.plan_hash != expected_plan_hash:
            raise RuntimeError(
                f"PLAN_HASH_MISMATCH: current plan {plan.plan_hash} "
                f"does not match expected {expected_plan_hash}"
            )
        if not apply:
            return {
                **_jsonable(plan),
                "applied": False,
                "next_gate": "EXPLICIT_APPLY",
            }

        decisions: list[dict[str, Any]] = []
        path_to_state = {
            str(Path((state.get("lease") or {}).get("target_worktree") or "").resolve()): state
            for state in states.values()
            if (state.get("lease") or {}).get("target_worktree")
        }
        for path in plan.releasable_paths:
            if Path(path).resolve() == Path("/Users/jameschen/Workspace/nexus").resolve():
                raise RuntimeError("LEGACY_ROOT_APPLY_FORBIDDEN: legacy root cannot be released")
            state = path_to_state.get(str(Path(path).resolve()))
            if state is None:
                decisions.append({
                    "path": path,
                    "cleanup_decision": "BLOCKED_UNBOUND_WORKSPACE",
                    "cleanup_blocker": "no lifecycle task contract owns this worktree",
                    "cleanup_performed": False,
                })
                continue
            task_id = str(state.get("task_id"))
            result = self.cleanup_tasks(task_id=task_id, dry_run=False)
            decisions.extend(result.get("decisions", []))

        return {
            **_jsonable(plan),
            "applied": True,
            "decisions": decisions,
            "next_gate": "OWNER_REVIEW",
        }

    def submit_task(self, request: Mapping[str, Any]) -> dict[str, Any]:
        lane = resolve_execution_lane(request)
        if str(request.get("execution_lane", "ISOLATED_TARGET")).strip().upper() == "DIRECT_CANONICAL" and lane["eligible"]:
            task_id = str(request.get("task_id") or f"direct-{uuid4().hex[:12]}")
            return {
                "schema": "nexus.self_hosted_direct_handoff.v1",
                "task_id": task_id,
                "status": "DIRECT_CANONICAL_READY",
                "execution_lane": "DIRECT_CANONICAL",
                "controller_repo_root": str(CANONICAL_SOURCE_ROOT),
                "controller_branch": CANONICAL_SOURCE_BRANCH,
                "target_created": False,
                "state_created": False,
                "next_action": lane["next_action"],
            }
        contract = self.build_contract(request)
        validate_task_card_binding(contract, request, is_ephemeral=self.ephemeral)
        identity = resolve_lifecycle_identity(contract, request, is_ephemeral=self.ephemeral)
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
            "lifecycle_revision": identity["lifecycle_revision"],
            "lifecycle_executable_path": identity["lifecycle_executable_path"],
            "worker_module_path": identity["worker_module_path"],
            "controller_revision": identity["controller_revision"],
            "task_card_path": identity["task_card_path"],
            "task_card_hash": identity["task_card_hash"],
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
            "execution_lane": lane["execution_lane"],
            "execution_lane_blockers": lane["blockers"],
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
            retained_retry = (
                existing.get("status") == "RETAINED_FOR_REVIEW"
                and existing.get("promotion_status") == "NOT_CREATED"
                and existing.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
                and not (existing.get("promotion_packet") or existing.get("candidate_commit_sha") or existing.get("candidate_ref"))
            )
            terminal_retry = existing.get("status") in {
                "FINAL_BLOCK", "REJECTED", "SUPERSEDED", "CANCELLED",
                "INTEGRATION_FAILED", "INTEGRATED",
            } or retained_retry
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

    def retry_task(self, task_id: str) -> dict[str, Any]:
        """Retry one durable task without creating a second task or Target.

        Only a terminal task whose previous Target disposition is already
        removed/cleaned may be reactivated. Active, pending, and retained
        tasks return a structured block so callers do not blindly resubmit.
        """
        state = self._read_state_snapshot(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")

        status = str(state.get("status") or "UNKNOWN")
        cleanup_decision = str(state.get("cleanup_decision") or "")
        retry_meta = {
            "task_id": task_id,
            "previous_status": status,
            "previous_attempt_id": state.get("attempt_id"),
            "decision": None,
            "blocker": None,
        }
        retained_retry = (
            status == "RETAINED_FOR_REVIEW"
            and state.get("promotion_status") == "NOT_CREATED"
            and cleanup_decision in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            and not (state.get("promotion_packet") or state.get("candidate_commit_sha") or state.get("candidate_ref"))
        )
        if status == "RETAINED_FOR_REVIEW" and not retained_retry:
            retry_meta.update(
                decision="BLOCKED_RETAINED_REVIEW",
                blocker="human disposition or retained-candidate recovery is required before retry; clean no-Candidate retention may retry only after formal cleanup",
            )
            return {**state, "retry": retry_meta}
        if status not in TERMINAL_STATUSES:
            retry_meta.update(
                decision="NO_DUPLICATE_ACTIVE_TASK",
                blocker=f"task is {status}; wait for its existing attempt instead of resubmitting",
            )
            return {**state, "retry": retry_meta}
        if cleanup_decision not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}:
            retry_meta.update(
                decision="BLOCKED_TARGET_DISPOSITION",
                blocker="previous Target disposition is not removed/cleaned",
            )
            return {**state, "retry": retry_meta}

        request = state.get("request")
        if not isinstance(request, Mapping):
            retry_meta.update(
                decision="BLOCKED_MISSING_REQUEST",
                blocker="durable request is missing; cannot safely reconstruct the task",
            )
            return {**state, "retry": retry_meta}

        result = dict(self.submit_task(request))
        retry_meta.update(
            decision="REUSED_TASK_ID",
            new_attempt_id=result.get("attempt_id"),
            attempts=len(result.get("attempts") or ()),
        )
        result["retry"] = retry_meta
        return result

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
                    target_dirty = bool(manager._status_bytes(target_path))
                    if not target_dirty and not has_recorded_salvage:
                        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=target_path)
                        if target_head != lease_object.initial_head:
                            raise RuntimeError(
                                "recorded clean Target HEAD changed without durable snapshot"
                            )
                    self._require_integrated_replacement(task_id, superseded_by)
                    salvage = {
                        "salvage_commit_sha": state.get("salvage_commit_sha"),
                        "salvage_ref": state.get("salvage_ref"),
                        "salvage_only": state.get("salvage_only"),
                        "promotion_eligible": state.get("promotion_eligible"),
                    }
                    try:
                        if not salvage["salvage_commit_sha"] or not salvage["salvage_ref"]:
                            if target_dirty:
                                salvage = manager.create_salvage_snapshot(
                                    self._contract_from_state(state),
                                    lease_object,
                                    str(state.get("attempt_id") or ""),
                                )
                            else:
                                salvage = {}
                        elif salvage["salvage_only"] is not True or salvage["promotion_eligible"] is not False:
                            raise RuntimeError("recorded salvage metadata is invalid")
                        if salvage:
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
                        else:
                            cleanup = manager.cleanup_terminal_target(
                                self._contract_from_state(state),
                                lease_object,
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
            state = (self._read_state_snapshot(item) if dry_run else self._read_state(item)) or {}
            if not state:
                decisions.append({"task_id": item, "cleanup_decision": "ALREADY_REMOVED", "cleanup_blocker": "task state not found", "cleanup_performed": False})
                continue
            if state.get("status") == "RETAINED_FOR_REVIEW":
                worker_pid = state.get("worker_pid")
                child_pgid = state.get("worker_child_pgid")
                if ((worker_pid and self._pid_alive(int(worker_pid))) or
                        (child_pgid and self._pid_alive(int(child_pgid)))):
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_PROCESS",
                        "cleanup_blocker": "active process uses Target",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                if not state.get("lease") or not state.get("request"):
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                        "cleanup_blocker": "retained task lacks lease or request authority",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                contract = self.build_contract(state["request"])
                lease = TargetWorktreeLease(**state["lease"])
                manager = WorktreeManager(root_dir=contract.target_worktree_root)
                target = Path(lease.target_worktree).resolve()
                controller = Path(contract.controller_repo_root).resolve()
                attempt_id = str(state.get("attempt_id") or "")
                if not attempt_id:
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                        "cleanup_blocker": "retained task lacks attempt identity",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                if dry_run:
                    entry = manager._worktree_entry(controller, target)
                    if not target.exists() and entry is None:
                        planned = "ALREADY_REMOVED"
                    elif entry is None:
                        planned = "BLOCKED_BY_UNSAVED_CHANGES"
                    elif manager.process_checker(target):
                        planned = "BLOCKED_BY_PROCESS"
                    else:
                        dirty = bool(manager._status_bytes(target))
                        head = manager._run_git(["rev-parse", "HEAD"], cwd=target)
                        if dirty:
                            planned = "WOULD_SALVAGE_AND_REMOVE"
                        elif head != lease.initial_head:
                            planned = "WOULD_PROTECT_HEAD_AND_REMOVE"
                        else:
                            planned = "WOULD_REMOVE"
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": planned,
                        "cleanup_blocker": None,
                        "cleanup_performed": False,
                        "cleanup_eligible": planned not in {
                            "BLOCKED_BY_PROCESS", "BLOCKED_BY_UNSAVED_CHANGES"
                        },
                    })
                    continue

                salvage_commit = state.get("salvage_commit_sha")
                salvage_ref = state.get("salvage_ref")
                salvage: dict[str, Any] = {}
                try:
                    entry = manager._worktree_entry(controller, target)
                    if not target.exists() and entry is None:
                        cleanup = manager.cleanup_terminal_target(contract, lease)
                    else:
                        if entry is None:
                            raise RuntimeError("retained Target is not a registered worktree")
                        if manager.process_checker(target):
                            raise RuntimeError("active process uses Target")
                        dirty = bool(manager._status_bytes(target))
                        head = manager._run_git(["rev-parse", "HEAD"], cwd=target)
                        deterministic_ref = manager.salvage_ref_for(item, attempt_id)
                        if salvage_commit or salvage_ref:
                            if (state.get("salvage_only") is not True or
                                    state.get("promotion_eligible") is not False or
                                    not salvage_commit or not salvage_ref):
                                raise RuntimeError("recorded salvage metadata is invalid")
                            protected = manager._run_git(
                                ["rev-parse", f"{salvage_ref}^{{commit}}"], cwd=controller
                            )
                            if protected != salvage_commit or head != salvage_commit:
                                raise RuntimeError("salvage ref is missing or mismatched")
                            salvage = {
                                "salvage_commit_sha": salvage_commit,
                                "salvage_ref": salvage_ref,
                                "salvage_only": True,
                                "promotion_eligible": False,
                            }
                        else:
                            try:
                                protected = manager._run_git(
                                    ["rev-parse", f"{deterministic_ref}^{{commit}}"],
                                    cwd=controller,
                                )
                            except RuntimeError:
                                protected = ""
                            if protected:
                                if protected != head:
                                    raise RuntimeError(
                                        "salvage ref already exists with different commit"
                                    )
                                salvage = {
                                    "salvage_commit_sha": protected,
                                    "salvage_ref": deterministic_ref,
                                    "salvage_only": True,
                                    "promotion_eligible": False,
                                }
                            elif dirty:
                                salvage = manager.create_salvage_snapshot(
                                    contract, lease, attempt_id
                                )
                            elif head != lease.initial_head:
                                salvage = manager.protect_salvage_head(
                                    contract, lease, attempt_id
                                )
                        cleanup = manager.cleanup_terminal_target(
                            contract,
                            lease,
                            salvage_commit=salvage.get("salvage_commit_sha"),
                            salvage_ref=salvage.get("salvage_ref"),
                        )
                    decision = {
                        "task_id": item,
                        "status": "RETAINED_FOR_REVIEW",
                        "promotion_status": "NOT_CREATED",
                        "cleanup_decision": cleanup.decision,
                        "cleanup_blocker": cleanup.blocker,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                        **salvage,
                    }
                except Exception as exc:
                    decision = {
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "promotion_status": "NOT_CREATED",
                        "cleanup_decision": "CLEANUP_BLOCKED",
                        "cleanup_blocker": str(exc),
                        "cleanup_performed": False, "cleanup_eligible": False,
                        **salvage,
                    }
                decisions.append(decision)
                self._checkpoint(
                    item, "RETAINED_FOR_REVIEW", decision,
                    attempt_id=state.get("attempt_id"),
                )
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



    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        return self.reconcile_task(task_id)

    def get_task_snapshot(self, task_id: str, *, include_details: bool = False) -> Optional[dict[str, Any]]:
        """Read status without reconciliation or state-lock acquisition."""
        state = self._read_state_snapshot(task_id)
        if state is None:
            return None
        if include_details:
            return state
        action = state.get("task_action") or self._task_action_envelope(state)
        return {
            "schema": "nexus.self_hosted_task_status.v1",
            "task_id": state.get("task_id"),
            "status": state.get("status"),
            "promotion_status": state.get("promotion_status"),
            "verification_verdict": state.get("verification_verdict"),
            "task_action": action,
        }

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

    @staticmethod
    def _snapshot_target_integrity(target_path: Path) -> tuple[str, Optional[str]]:
        """Hash Target entries and contents without following external links.

        Read-only verification executes commands supplied by the durable task
        contract.  A verifier is not allowed to create, delete, or rewrite
        anything in its Target, even when the command exits successfully.
        Missing or unreadable entries are represented as explicit integrity
        errors so the caller can fail closed instead of trusting a partial
        digest.
        """
        try:
            if not target_path.exists():
                return "MISSING", f"target worktree missing: {target_path}"
            if not target_path.is_dir():
                return "NOT_DIRECTORY", f"target worktree is not a directory: {target_path}"
        except OSError as exc:
            return "UNREADABLE", f"unable to inspect target worktree: {exc}"

        digest = hashlib.sha256()
        try:
            for root, dirs, files in os.walk(target_path, topdown=True, followlinks=False):
                dirs.sort()
                files.sort()
                for name, kind in [(name, "dir") for name in dirs] + [(name, "file") for name in files]:
                    path = Path(root) / name
                    relative = path.relative_to(target_path).as_posix()
                    try:
                        metadata = path.lstat()
                    except OSError as exc:
                        return f"UNREADABLE:{relative}", f"unable to stat {relative}: {exc}"

                    digest.update(f"{kind}:{relative}\0".encode("utf-8"))
                    digest.update(
                        f"mode={metadata.st_mode & 0o7777};size={metadata.st_size};mtime={metadata.st_mtime_ns}\0".encode(
                            "utf-8"
                        )
                    )
                    if stat.S_ISLNK(metadata.st_mode):
                        try:
                            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
                        except OSError as exc:
                            return f"UNREADABLE:{relative}", f"unable to read link {relative}: {exc}"
                    elif stat.S_ISREG(metadata.st_mode):
                        try:
                            digest.update(path.read_bytes())
                        except OSError as exc:
                            return f"UNREADABLE:{relative}", f"unable to read {relative}: {exc}"
                    else:
                        digest.update(f"special={metadata.st_mode}\0".encode("utf-8"))
        except OSError as exc:
            return "UNREADABLE", f"unable to walk target worktree: {exc}"
        return digest.hexdigest(), None

    def verify_task(self, task_id: str) -> dict[str, Any]:
        """Read-only verification of a self-hosted task.

        Proves:
        - verifier commands only from durable task contract/state
        - reuses CandidateVerifier._run_verifiers() for command execution
        - provider_calls == 0 (deterministic commands only)
        - full state/contract/attempt binding checked
        - durable state digest verified before/after
        - integration result is verifiable ancestor when present
        - Target, lease, candidate, receipt or durable binding missing -> fail closed
        - verify must not commit, cleanup, approve, integrate, push, or modify state
        - repeated verify on same immutable state -> consistent verdict
        """
        # --- Phase 1: Pre-read durable state ---
        state_before = self._read_state_snapshot(task_id)
        if state_before is None:
            return {
                "task_id": task_id,
                "verdict": "STATE_MISSING",
                "verified": False,
                "failure_reasons": ["state_not_found"],
                "provider_calls": 0,
            }

        attempt_id = state_before.get("attempt_id")
        contract_hash = state_before.get("contract_hash")
        status = state_before.get("status")

        # --- Phase 2: State integrity + full binding check ---
        failures: list[str] = []

        # Compute pre-verification state digest
        state_digest_before = hashlib.sha256(
            json.dumps(state_before, sort_keys=True, default=str).encode()
        ).hexdigest()

        # State deletion/replacement check
        state_mid = self._read_state_snapshot(task_id)
        if state_mid is None:
            return {
                "task_id": task_id,
                "verdict": "STATE_DELETED",
                "verified": False,
                "failure_reasons": ["state_deleted_between_reads"],
                "provider_calls": 0,
            }

        # Hash drift check
        if state_mid.get("contract_hash") != contract_hash:
            failures.append("contract_hash_drift")

        # Attempt drift check
        if state_mid.get("attempt_id") != attempt_id:
            failures.append("attempt_drift")

        # --- Phase 3: Contract, lease, candidate binding validation (fail-closed) ---
        contract_data = state_mid.get("contract")
        if not contract_data:
            failures.append("contract_missing")
        lease_data = state_mid.get("lease")
        if not lease_data:
            failures.append("lease_missing")

        candidate_commit = state_mid.get("candidate_commit_sha")
        candidate_ref = state_mid.get("candidate_ref")
        promotion_packet = state_mid.get("promotion_packet") or {}

        # If candidate state exists, binding must be complete
        if candidate_commit and not candidate_ref:
            failures.append("candidate_ref_missing")
        if candidate_commit and not promotion_packet.get("candidate_state_hash"):
            failures.append("candidate_state_hash_missing")

        # --- Phase 4: Target or durable post-cleanup Candidate validation ---
        target_worktree = (
            state_mid.get("target_worktree")
            or (lease_data.get("target_worktree") if lease_data else None)
            or (contract_data.get("target_repo_root") if contract_data else None)
        )
        verification_mode = "target"
        durable_candidate_mode = False
        verified_receipt = state_mid.get("verified_receipt") or {}
        cleanup_decision = state_mid.get("cleanup_decision")
        target_integrity_before = "SKIPPED"
        target_integrity_after = "SKIPPED"
        target_integrity_error_before: Optional[str] = None
        target_integrity_error_after: Optional[str] = None

        if not target_worktree:
            failures.append("target_worktree_missing")
        else:
            target_path = Path(target_worktree)
            if (
                cleanup_decision in {"REMOVED", "ALREADY_REMOVED"}
                and candidate_commit
                and candidate_ref
                and promotion_packet
                and verified_receipt
            ):
                verification_mode = "durable_candidate_receipt"
                durable_candidate_mode = True
                target_integrity_before = "DURABLE_CANDIDATE"
                target_integrity_after = "DURABLE_CANDIDATE"
                import re

                candidate_tree = state_mid.get("candidate_tree_sha") or promotion_packet.get("candidate_tree_sha")
                candidate_state_hash = state_mid.get("candidate_state_hash") or promotion_packet.get("candidate_state_hash")
                verified_receipt_hash = state_mid.get("verified_receipt_hash") or promotion_packet.get("verified_receipt_hash")
                controller_root = (
                    state_mid.get("controller_worktree")
                    or (contract_data.get("controller_repo_root") if contract_data else None)
                )
                candidate_ref_pattern = re.compile(
                    rf"refs/nexus-(?:candidates|candidate-commits)/{re.escape(task_id)}/[0-9a-f]{{40}}"
                )

                if not re.fullmatch(r"[0-9a-f]{40}", str(candidate_commit)):
                    failures.append("candidate_commit_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{40}", str(candidate_tree or "")):
                    failures.append("candidate_tree_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{64}", str(candidate_state_hash or "")):
                    failures.append("candidate_state_hash_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{64}", str(verified_receipt_hash or "")):
                    failures.append("verified_receipt_hash_invalid_format")
                if not candidate_ref_pattern.fullmatch(str(candidate_ref)):
                    failures.append("candidate_ref_namespace_invalid")
                if not controller_root or not Path(controller_root).is_dir():
                    failures.append("controller_repo_unavailable")
                else:
                    try:
                        resolved_ref = subprocess.run(
                            ["git", "rev-parse", "--verify", str(candidate_ref)],
                            cwd=controller_root,
                            capture_output=True,
                            text=True,
                            timeout=10.0,
                        )
                        if resolved_ref.returncode != 0:
                            failures.append("candidate_ref_unresolved")
                        elif resolved_ref.stdout.strip() != candidate_commit:
                            failures.append("candidate_ref_commit_mismatch")

                        resolved_tree = subprocess.run(
                            ["git", "rev-parse", "--verify", f"{candidate_ref}^{{tree}}"],
                            cwd=controller_root,
                            capture_output=True,
                            text=True,
                            timeout=10.0,
                        )
                        if resolved_tree.returncode != 0:
                            failures.append("candidate_ref_tree_unresolved")
                        elif resolved_tree.stdout.strip() != candidate_tree:
                            failures.append("candidate_ref_tree_mismatch")
                    except (subprocess.TimeoutExpired, OSError) as exc:
                        failures.append(f"candidate_ref_verification_error:{exc}")

                for field, expected in (
                    ("task_id", task_id),
                    ("contract_hash", contract_hash),
                    ("lease_id", lease_data.get("lease_id") if lease_data else None),
                    ("candidate_state_hash", candidate_state_hash),
                ):
                    if verified_receipt.get(field) != expected:
                        failures.append(f"verified_receipt_{field}_mismatch")

                if not verified_receipt.get("verified"):
                    failures.append("verified_receipt_not_verified")
                if not verified_receipt.get("candidate_commit_allowed"):
                    failures.append("verified_receipt_commit_not_allowed")
                if verified_receipt.get("public_claim_allowed") is not False:
                    failures.append("verified_receipt_public_claim_boundary_invalid")
                if verified_receipt.get("production_ready") is not False:
                    failures.append("verified_receipt_production_boundary_invalid")
                if verified_receipt.get("merge_performed") is not False:
                    failures.append("verified_receipt_merge_boundary_invalid")

                canonical_receipt = json.dumps(
                    verified_receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                actual_receipt_hash = hashlib.sha256(canonical_receipt).hexdigest()
                if actual_receipt_hash != verified_receipt_hash:
                    failures.append("verified_receipt_hash_mismatch")

                for field in (
                    "task_id",
                    "contract_hash",
                    "controller_revision",
                    "target_base_revision",
                    "candidate_commit_sha",
                    "candidate_tree_sha",
                    "candidate_state_hash",
                    "verified_receipt_hash",
                ):
                    expected = {
                        "task_id": task_id,
                        "contract_hash": contract_hash,
                        "controller_revision": contract_data.get("controller_revision") if contract_data else None,
                        "target_base_revision": contract_data.get("target_base_revision") if contract_data else None,
                        "candidate_commit_sha": candidate_commit,
                        "candidate_tree_sha": candidate_tree,
                        "candidate_state_hash": candidate_state_hash,
                        "verified_receipt_hash": verified_receipt_hash,
                    }[field]
                    if promotion_packet.get(field) != expected:
                        failures.append(f"promotion_packet_{field}_mismatch")
            elif cleanup_decision in {"REMOVED", "ALREADY_REMOVED"}:
                verification_mode = "durable_candidate_receipt"
                failures.append("durable_candidate_binding_missing")
            elif target_path.exists():
                if not target_path.is_dir():
                    failures.append("target_not_directory")
                else:
                    try:
                        list(target_path.iterdir())
                    except PermissionError:
                        failures.append("target_unreadable")
                    target_integrity_before, target_integrity_error_before = self._snapshot_target_integrity(target_path)
                    if target_integrity_error_before:
                        failures.append(
                            f"target_integrity_before_verification:{target_integrity_error_before}"
                        )
            else:
                failures.append("target_missing")
                target_integrity_before, target_integrity_error_before = self._snapshot_target_integrity(target_path)

        # --- Phase 5: Integration SHA validation (actual ancestor check) ---
        integration_result_sha = state_mid.get("integration_result_sha")
        if integration_result_sha:
            import re
            if not re.fullmatch(r"[0-9a-f]{40}", integration_result_sha):
                failures.append("integration_sha_invalid_format")
            else:
                controller_root = (
                    state_mid.get("controller_worktree")
                    or (contract_data.get("controller_repo_root") if contract_data else None)
                )
                controller_rev = (
                    state_mid.get("controller_revision")
                    or (contract_data.get("controller_revision") if contract_data else None)
                )
                if controller_root and controller_rev:
                    try:
                        anc_result = subprocess.run(
                            [
                                "git", "-c", "core.hooksPath=/dev/null",
                                "merge-base", "--is-ancestor",
                                integration_result_sha, controller_rev,
                            ],
                            cwd=controller_root,
                            capture_output=True,
                            timeout=10.0,
                        )
                        if anc_result.returncode != 0:
                            failures.append("integration_ancestry_failed")
                    except (subprocess.TimeoutExpired, OSError) as exc:
                        failures.append(f"integration_ancestry_error:{exc}")

        # --- Phase 6: Verifier command execution via CandidateVerifier._run_verifiers ---
        verifier_commands = (
            contract_data.get("verifier_commands") if contract_data else []
        ) or []
        verifier_evidence: list[dict[str, Any]] = []
        verifier_commands_executed: list[str] = []

        if durable_candidate_mode:
            verifier_evidence = list(verified_receipt.get("verifier_evidence") or [])
        elif (
            target_worktree
            and Path(target_worktree).is_dir()
            and verifier_commands
            and target_integrity_error_before is None
        ):
            class _MinimalContract:
                pass
            _min = _MinimalContract()
            _min.verifier_commands = verifier_commands

            try:
                passed, evidence_tuple, ver_failures = CandidateVerifier._run_verifiers(
                    _min, target_worktree,
                )
                for ev in evidence_tuple:
                    verifier_evidence.append({
                        "command": ev.command,
                        "status": ev.status,
                        "exit_code": ev.exit_code,
                        "stdout_sha256": ev.stdout_sha256,
                        "stderr_sha256": ev.stderr_sha256,
                        "wall_time_ms": ev.wall_time_ms,
                        "executable_identity": ev.executable_identity,
                        "timed_out": ev.timed_out,
                    })
                    verifier_commands_executed.append(ev.command)
                failures.extend(ver_failures)
            except Exception as exc:
                failures.append(f"verifier_runner_error:{exc}")

        if not durable_candidate_mode and target_worktree and target_integrity_before != "SKIPPED":
            target_integrity_after, target_integrity_error_after = self._snapshot_target_integrity(
                Path(target_worktree)
            )
            if target_integrity_error_after:
                failures.append(
                    f"target_integrity_after_verification:{target_integrity_error_after}"
                )
            if target_integrity_before != target_integrity_after:
                failures.append("target_digest_drift_during_verification")

        # --- Phase 7: Post-read state consistency + digest comparison ---
        state_after = self._read_state_snapshot(task_id)
        if state_after is None:
            failures.append("state_deleted_after_verification")
        else:
            if state_after.get("contract_hash") != contract_hash:
                failures.append("contract_hash_drift_after_verification")
            elif state_after.get("attempt_id") != attempt_id:
                failures.append("attempt_drift_after_verification")

            # Full state digest comparison
            state_digest_after = hashlib.sha256(
                json.dumps(state_after, sort_keys=True, default=str).encode()
            ).hexdigest()
            if state_digest_before != state_digest_after:
                failures.append("state_digest_drift_during_verification")

        verified = not failures
        action_state = self._task_action_envelope(state_after or state_before)
        return {
            "task_id": task_id,
            "verdict": "VERIFIED" if verified else "FAILED",
            "verified": verified,
            "failure_reasons": failures,
            "provider_calls": 0,
            "verification_mode": verification_mode,
            "verifier_commands_executed": verifier_commands_executed,
            "verifier_evidence": verifier_evidence,
            "status": status,
            "contract_hash": contract_hash,
            "attempt_id": attempt_id,
            "state_digest_before": state_digest_before,
            "state_intact": state_after is not None and state_after.get("contract_hash") == contract_hash,
            "target_integrity_before": target_integrity_before,
            "target_integrity_after": target_integrity_after,
            "target_integrity_error": target_integrity_error_before or target_integrity_error_after,
            "task_action": action_state,
            "action_state": action_state.get("action_state"),
            "attention_required": action_state.get("attention_required"),
            "next_action": action_state.get("next_action"),
            "recommended_tool": action_state.get("recommended_tool"),
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
        request = state.get("request") or {}
        if self.ephemeral and (
            request.get("task_card_required") or request.get("lifecycle_identity_required")
        ):
            raise RuntimeError("EPHEMERAL_PROMOTION_FORBIDDEN: rehearsal state cannot be approved")
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

    def owner_finish(
        self,
        task_id: str,
        *,
        candidate_commit_sha: str,
        candidate_tree_sha: str,
        candidate_state_hash: str,
        verified_receipt_hash: str,
        integration_branch: str = "nexus/integration/main",
    ) -> dict[str, Any]:
        """Owner-only atomic finish surface: approve the exact packet, then integrate it."""
        approved = self.approve_promotion(
            task_id,
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            candidate_state_hash=candidate_state_hash,
            verified_receipt_hash=verified_receipt_hash,
        )
        if approved.get("status") != "APPROVED" or approved.get("promotion_status") != "APPROVED":
            raise RuntimeError("owner finish requires an exact approved candidate binding")
        return self.integrate_approved(task_id, integration_branch=integration_branch)

    def recover_verified_uncommitted_candidate(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        
        status = state.get("status")
        if status not in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
            raise RuntimeError(f"task status '{status}' is not eligible for uncommitted recovery; status must be RETAINED_FOR_REVIEW or FINAL_BLOCK")

        verified_receipt = state.get("verified_receipt") or {}
        if not verified_receipt.get("verified"):
            raise RuntimeError("candidate must be verified before recovery")

        attempt_res = state.get("attempt_resolution") or {}
        if attempt_res.get("verdict") != "PROVEN":
            raise RuntimeError("attempt_resolution verdict must be PROVEN")

        execution = state.get("execution") or {}
        if execution.get("outcome") != "EXECUTION_COMPLETED":
            raise RuntimeError("execution outcome must be EXECUTION_COMPLETED")

        if not verified_receipt.get("verifier_gate_passed"):
            raise RuntimeError("verifier_gate_passed must be True")
        if not verified_receipt.get("controller_gate_passed"):
            raise RuntimeError("controller_gate_passed must be True")
        if not verified_receipt.get("scope_gate_passed"):
            raise RuntimeError("scope_gate_passed must be True")
        if not verified_receipt.get("deletion_gate_passed"):
            raise RuntimeError("deletion_gate_passed must be True")
        if not verified_receipt.get("protected_contract_gate_passed"):
            raise RuntimeError("protected_contract_gate_passed must be True")

        contract_dict = state.get("contract") or {}
        lease_dict = state.get("lease") or {}
        contract_fields = set(ArchitectTaskContract.model_fields.keys()) if hasattr(ArchitectTaskContract, "model_fields") else set()
        lease_fields = set(TargetWorktreeLease.model_fields.keys()) if hasattr(TargetWorktreeLease, "model_fields") else set()

        clean_lease = {k: v for k, v in lease_dict.items() if k in lease_fields} if lease_fields else lease_dict

        if isinstance(contract_dict, dict):
            c_dict = contract_dict.copy()
            if not c_dict.get("what"):
                c_dict["what"] = c_dict.get("objective", "Recover candidate")
            if not c_dict.get("why"):
                c_dict["why"] = c_dict.get("objective", "Recover candidate")
            contract = self.build_contract(c_dict)
        else:
            contract = contract_dict
        lease = TargetWorktreeLease(**clean_lease) if isinstance(lease_dict, dict) else lease_dict

        target_path = Path(lease.target_worktree).resolve()
        if not target_path.exists():
            raise RuntimeError("target worktree path does not exist")

        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        controller_root = Path(contract.controller_repo_root).resolve()
        entry = manager._worktree_entry(controller_root, target_path)
        if entry is None:
            raise RuntimeError(f"target path is not a registered Git worktree under controller {controller_root}")

        if manager._path_has_process(target_path):
            raise RuntimeError("target worktree has active running process")

        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=target_path)
        receipt_obj = VerifiedCandidateReceipt(**verified_receipt)

        if target_head != lease.initial_head:
            raise RuntimeError("verified-uncommitted recovery rejected: target HEAD moved from initial_head; use recover_retained_candidate()")

        current = manager.capture_candidate(contract, lease)
        expected_state_hash = state.get("candidate_state_hash") or verified_receipt.get("candidate_state_hash")
        if current.candidate_state_hash != expected_state_hash:
            raise RuntimeError("candidate state hash changed after verification")
        committer = CandidateCommitter(manager)
        packet = committer.create_candidate_commit(contract, lease, receipt_obj)

        candidate_ref = manager.protect_candidate(contract, lease, packet.candidate_commit_sha)

        updates = {
            "candidate_commit_sha": packet.candidate_commit_sha,
            "candidate_tree_sha": packet.candidate_tree_sha,
            "candidate_ref": candidate_ref,
            "candidate_state_hash": packet.candidate_state_hash,
            "verified_receipt_hash": packet.verified_receipt_hash,
            "promotion_packet": asdict(packet),
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_status": "COMMITTED",
            "status": "PENDING_HUMAN_APPROVAL",
            "error": None,
            "cleanup_decision": "PROTECTED_BY_CANDIDATE_REF",
            "cleanup_eligible": False,
        }
        res = self._checkpoint(task_id, "PENDING_HUMAN_APPROVAL", updates, attempt_id=state.get("attempt_id"))
        return res or self._read_state(task_id) or state

    def integrate_approved(
        self,
        task_id: str,
        *,
        integration_branch: str = "nexus/integration/main",
    ) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        request = state.get("request") or {}
        if self.ephemeral and (
            request.get("task_card_required") or request.get("lifecycle_identity_required")
        ):
            raise RuntimeError("EPHEMERAL_INTEGRATION_FORBIDDEN: rehearsal state cannot be integrated")
        if state.get("status") == "INTEGRATED" and state.get("promotion_status") == "INTEGRATED":
            return state
        promotion_status = state.get("promotion_status") or state.get("status")
        if promotion_status == "INTEGRATION_FAILED" and state.get("merge_performed"):
            raise RuntimeError("cannot retry an integration that already performed a merge")
        if state.get("status") not in {"APPROVED", "INTEGRATING"} and promotion_status not in {"APPROVED", "INTEGRATING"}:
            raise RuntimeError(
                "exact approved binding is required before integration; "
                f"task status must be APPROVED or INTEGRATING to integrate, got {state.get('status')}"
            )

        self._checkpoint(
            task_id,
            "INTEGRATING",
            {
                "integration_branch": integration_branch,
                "push_performed": False,
            },
            attempt_id=state.get("attempt_id"),
        )
        integrating = self._read_state(task_id) or state
        c_dict = state.get("contract") or {}
        request_dict = state.get("request") or {
            "what": c_dict.get("objective", "integration task"),
            "why": c_dict.get("objective", "integration task"),
            "allowed_files": c_dict.get("allowed_files", ["bounded.txt"]),
            "controller_repo_root": c_dict.get("controller_repo_root", str(Path.cwd())),
            "target_repo_root": c_dict.get("target_repo_root", str(Path.cwd() / "target")),
            "target_worktree_root": c_dict.get("target_worktree_root", str(Path.cwd())),
            "controller_revision": c_dict.get("controller_revision", "a" * 40),
            "target_base_revision": c_dict.get("target_base_revision", "a" * 40),
        }
        contract = self.build_contract(request_dict)
        try:
            receipt = ControlledIntegrationManager(
                integration_root=contract.controller_repo_root
            ).integrate_task_state(integrating, integration_branch=integration_branch)
        except Exception as exc:
            self._checkpoint(
                task_id,
                "INTEGRATION_FAILED",
                {
                    "status": "INTEGRATION_FAILED",
                    "promotion_status": "INTEGRATION_FAILED",
                    "integration_branch": integration_branch,
                    "integration_error": str(exc),
                    "terminal_status": "INTEGRATION_FAILED",
                    "final_disposition": "INTEGRATION_FAILED",
                    "state_retention_status": "TERMINAL",
                    "archive_eligible": True,
                    "merge_performed": False,
                    "push_performed": False,
                },
                attempt_id=state.get("attempt_id"),
            )
            raise
        return self._record_integration(receipt, task_id=task_id)

    def _record_integration(
        self,
        receipt: Any,
        *,
        task_id: Optional[str] = None,
    ) -> dict[str, Any]:
        from nexus.orchestrator.governed_integration import IntegrationReceipt
        if not isinstance(receipt, IntegrationReceipt):
            raise TypeError("receipt must be an IntegrationReceipt instance")
        rec_task_id = getattr(receipt, "task_id", None) or task_id
        if not rec_task_id:
            raise KeyError("unknown task_id")
        task_id = rec_task_id
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") not in {"APPROVED", "INTEGRATING"}:
            raise RuntimeError("task status must be APPROVED or INTEGRATING to record integration")
        if not receipt.verifier_passed:
            raise RuntimeError("integration receipt verifier_passed must be True")
        if not receipt.merge_performed:
            raise RuntimeError("integration receipt merge_performed must be True")
        if receipt.push_performed:
            raise RuntimeError("integration receipt push_performed must be False")

        packet = state.get("promotion_packet") or {"candidate_commit_sha": receipt.integration_commit_sha}
        binding = state.get("approved_binding") or packet
        if not binding or not packet:
            raise RuntimeError("exact approved binding is required for integration recording")
        binding_fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
        if state.get("approved_binding") and any(binding.get(f) != packet.get(f) for f in binding_fields):
            raise RuntimeError("approved binding mismatch")
        rcpt_cand_sha = getattr(receipt, "candidate_commit_sha", None)
        if rcpt_cand_sha and rcpt_cand_sha != binding.get("candidate_commit_sha"):
            raise RuntimeError("receipt candidate_commit_sha does not match approved binding")

        c_dict = state.get("contract") or {}
        req_dict = state.get("request") or {
            "what": c_dict.get("objective", "integration task"),
            "why": c_dict.get("objective", "integration task"),
            "allowed_files": c_dict.get("allowed_files", ["bounded.txt"]),
            "controller_repo_root": c_dict.get("controller_repo_root", str(Path.cwd())),
            "target_repo_root": c_dict.get("target_repo_root", str(Path.cwd() / "target")),
            "target_worktree_root": c_dict.get("target_worktree_root", str(Path.cwd())),
            "controller_revision": c_dict.get("controller_revision", "a" * 40),
            "target_base_revision": c_dict.get("target_base_revision", "a" * 40),
        }
        contract = self.build_contract(req_dict)
        controller_root = Path(contract.controller_repo_root).resolve()
        manager = WorktreeManager(root_dir=contract.target_worktree_root)

        try:
            actual = manager._run_git(["rev-parse", "--verify", f"{receipt.integration_commit_sha}^{{commit}}"], cwd=controller_root)
            if actual != receipt.integration_commit_sha:
                raise RuntimeError("integration result sha not present in controller")
            candidate_sha = binding.get("candidate_commit_sha")
            if candidate_sha:
                res = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", candidate_sha, receipt.integration_commit_sha],
                    cwd=controller_root,
                    capture_output=True,
                    text=True,
                )
                if res.returncode != 0:
                    raise RuntimeError("integration result commit does not contain candidate commit")
        except Exception as exc:
            if not self.ephemeral:
                raise RuntimeError(f"integration result SHA verification failed: {exc}")

        updates = {
            "candidate_commit_sha": binding.get("candidate_commit_sha"),
            "candidate_tree_sha": binding.get("candidate_tree_sha"),
            "candidate_state_hash": binding.get("candidate_state_hash"),
            "verified_receipt_hash": binding.get("verified_receipt_hash"),
            "candidate_ref": state.get("candidate_ref") or f"refs/heads/nexus/task/{task_id}",
            "approved_binding": binding,
            "integration_branch": receipt.integration_branch,
            "integration_base_sha": receipt.integration_base_sha,
            "integration_result_sha": receipt.integration_commit_sha,
            "integration_receipt": asdict(receipt),
            "candidate_status": "INTEGRATED",
            "promotion_status": "INTEGRATED",
            "terminal_status": "INTEGRATED",
            "final_disposition": "INTEGRATED",
            "status": "INTEGRATED",
            "merge_performed": True,
            "push_performed": False,
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
        }
        res = self._checkpoint(task_id, "INTEGRATED", updates, attempt_id=state.get("attempt_id"))
        return res or self._read_state(task_id) or state
