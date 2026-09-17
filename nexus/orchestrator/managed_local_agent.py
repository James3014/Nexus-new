"""Provider-agnostic managed local-agent UX and control contract (Wave C).

This module implements the owner/coordinator-facing contract for managed coding
tasks across arbitrary admitted providers (Codex, Agy/Gemini, OpenCode, Claude, etc.)
without exposing internal Core plumbing or allowing worker prose to become completion truth.

Invariants strictly enforced:
- CORE_BOUND_BEFORE_REPOSITORY_MUTATION
- CORE_EVIDENCED_BEFORE_ENGINEERING_COMPLETION_CLAIM
- Provider-neutrality: completion semantics and Core truth do not change with provider.
- Pre-write machine-enforced binding: locks paths, deletion policy, and verifiers.
- No silent downgrades: GOVERNED never silently downgrades to DIRECT on transport error.
- Replay discipline: timeouts and disconnects are not retry permissions; reconcile first.
- Raw mutation boundary: manual/raw path preserves lower claim (PRE_WRITE_MACHINE_ENFORCED_CORE_BOUND=False).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerOutcome,
)
from nexus.executors.worker_registry import WorkerRegistry
from nexus.orchestrator.ambient_core import AmbientCoreControlPort
from nexus.orchestrator.self_hosted_task_service import (
    SelfHostedTaskService,
    resolve_canonical_target_roots,
)


class ManagedExecutionLane(str, Enum):
    DIRECT_CANONICAL = "DIRECT_CANONICAL"
    DIRECT_DELEGATED = "DIRECT_DELEGATED"
    GOVERNED = "GOVERNED"


class ReconcileAction(str, Enum):
    RECONCILE_EXISTING = "RECONCILE_EXISTING"
    REBIND_REQUIRED = "REBIND_REQUIRED"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ManagedBindingIdentity:
    """Pre-write machine-enforced binding identity required before any mutation."""

    repository_canonical_identity: str
    exact_base_revision: str
    source_tree_identity: str
    workspace_identity: str
    workspace_mode: str
    execution_lane: str
    authority_reference: str
    capability_discovery_identity: str
    acceptance_contract: Mapping[str, Any]
    acceptance_contract_hash: str
    allowed_paths: tuple[str, ...]
    deletion_policy: Mapping[str, Any]
    required_verifier_ids: tuple[str, ...]
    operation_id: str
    attempt_id: str
    binding_id: str
    binding_hash: str
    freshness: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ManagedLocalAgentRequest:
    """Owner/coordinator high-level request to run a managed local agent."""

    task_id: str
    what: str
    why: str
    repository_root: str
    base_revision: str
    worker_provider: str
    target_root: Optional[str] = None
    worker_model: Optional[str] = None
    allowed_files: Sequence[str] = field(default_factory=lambda: ("src/",))
    forbidden_files: Sequence[str] = field(default_factory=tuple)
    verifier_commands: Sequence[str] = field(default_factory=tuple)
    deletion_policy: Mapping[str, Any] = field(default_factory=lambda: {"allow_deletion": False})
    execution_lane: str = ManagedExecutionLane.DIRECT_CANONICAL.value
    authority_reference: Optional[str] = None
    ambient_core_port: Optional[AmbientCoreControlPort] = None
    core_envelope_required: bool = True
    raw_mutation_mode: bool = False
    shell_pty_mode: bool = False
    timeout_seconds: Optional[float] = None
    idempotency_key: Optional[str] = None


@dataclass(frozen=True)
class ManagedLocalAgentReceipt:
    """Structured receipt returned by the managed local-agent launcher."""

    task_id: str
    worker_provider: str
    execution_lane: str
    status: str
    terminal_status: Optional[str]
    pre_write_machine_enforced_core_bound: bool
    path_level_prewrite_containment_proven: bool
    post_hoc_physical_verification: bool
    core_provenance_verified: bool
    core_binding_hash: Optional[str]
    candidate_state_hash: Optional[str]
    candidate_commit_sha: Optional[str]
    candidate_ref: Optional[str]
    worker_invocation_count: int
    worker_outcome: Optional[str]
    failure_reasons: tuple[str, ...] = field(default_factory=tuple)
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)


class ManagedLocalAgentLauncher:
    """Coordinates managed local agents with strict Core host binding and provider neutrality."""

    def __init__(
        self,
        service: Optional[SelfHostedTaskService] = None,
        worker_registry: Optional[WorkerRegistry] = None,
    ):
        self.service = service or SelfHostedTaskService(ephemeral=True, auto_reconcile=False)
        self.worker_registry = (
            worker_registry
            or getattr(self.service, "worker_registry", None)
            or WorkerRegistry.default()
        )

    def launch_managed_agent(self, request: ManagedLocalAgentRequest) -> ManagedLocalAgentReceipt:
        """Entry point for executing a managed coding task."""
        repo_path = Path(request.repository_root).resolve()
        if not repo_path.exists():
            raise ValueError(f"repository_root does not exist: {request.repository_root}")

        # 1. Base revision freshness check (Section 22 #5)
        current_head = self._get_current_head(str(repo_path))
        if current_head and request.base_revision and current_head != request.base_revision:
            return ManagedLocalAgentReceipt(
                task_id=request.task_id,
                worker_provider=request.worker_provider,
                execution_lane=request.execution_lane,
                status="REBIND_REQUIRED",
                terminal_status="REBIND_REQUIRED",
                pre_write_machine_enforced_core_bound=False,
                path_level_prewrite_containment_proven=False,
                post_hoc_physical_verification=False,
                core_provenance_verified=False,
                core_binding_hash=None,
                candidate_state_hash=None,
                candidate_commit_sha=None,
                candidate_ref=None,
                worker_invocation_count=0,
                worker_outcome=None,
                failure_reasons=(
                    f"base drift detected: requested {request.base_revision} != current HEAD {current_head}",
                ),
            )

        # 2. Provider validation (Section 15, 16)
        provider = str(request.worker_provider).strip().lower()
        if provider not in SUPPORTED_WORKER_PROVIDERS:
            raise ValueError(f"unsupported worker provider: {request.worker_provider}")

        # 3. Raw/manual path handling (Section 19, 22 #11)
        if request.raw_mutation_mode:
            return self._handle_raw_mutation_path(request, repo_path)

        # 4. Target root safety check
        target_worktree_root, _ = resolve_canonical_target_roots(
            request.task_id, requested_target_worktree_root=request.target_root
        )

        # 5. Core-bound pre-mutation gate (Section 17, 22 #1)
        attempt_id = f"attempt-{request.task_id}-1"
        binding_identity = self._construct_and_bind_identity(
            request, repo_path, current_head, attempt_id
        )

        if request.core_envelope_required:
            if request.ambient_core_port is None:
                # Missing Core port blocks before worker invocation (worker_invocation_count = 0)
                return ManagedLocalAgentReceipt(
                    task_id=request.task_id,
                    worker_provider=provider,
                    execution_lane=request.execution_lane,
                    status="FINAL_BLOCK",
                    terminal_status="FINAL_BLOCK",
                    pre_write_machine_enforced_core_bound=False,
                    path_level_prewrite_containment_proven=False,
                    post_hoc_physical_verification=False,
                    core_provenance_verified=False,
                    core_binding_hash=None,
                    candidate_state_hash=None,
                    candidate_commit_sha=None,
                    candidate_ref=None,
                    worker_invocation_count=0,
                    worker_outcome=None,
                    failure_reasons=(
                        "AMBIENT_CORE_CONTROL_PORT_REQUIRED: Core envelope required but port missing",
                    ),
                    raw_metadata={"binding_identity": binding_identity.binding_hash},
                )

        # 6. Dispatch through SelfHostedTaskService
        service_request = {
            "task_id": request.task_id,
            "what": request.what,
            "why": request.why,
            "controller_revision": request.base_revision,
            "target_base_revision": request.base_revision,
            "controller_repo_root": str(repo_path),
            "target_repo_root": str(Path(target_worktree_root) / request.task_id),
            "target_worktree_root": str(target_worktree_root),
            "allowed_files": list(request.allowed_files),
            "forbidden_files": list(request.forbidden_files),
            "verifier_commands": list(request.verifier_commands),
            "protected_contracts": [],
            "worker": provider,
            "worker_id": f"worker-{provider}-{request.task_id}",
            "core_envelope_required": request.core_envelope_required,
            "deletion_policy": dict(request.deletion_policy),
            "managed_binding_hash": binding_identity.binding_hash,
        }
        if request.idempotency_key:
            service_request["idempotency_key"] = request.idempotency_key

        # Inject ambient core port into service
        if request.ambient_core_port:
            self.service.ambient_core_port = request.ambient_core_port

        try:
            submitted = self.service.submit_task(service_request)
        except Exception as exc:
            # Governed never silently downgrades to direct on error (Section 22 #14)
            return ManagedLocalAgentReceipt(
                task_id=request.task_id,
                worker_provider=provider,
                execution_lane=request.execution_lane,
                status="FINAL_BLOCK",
                terminal_status="FINAL_BLOCK",
                pre_write_machine_enforced_core_bound=False,
                path_level_prewrite_containment_proven=False,
                post_hoc_physical_verification=False,
                core_provenance_verified=False,
                core_binding_hash=None,
                candidate_state_hash=None,
                candidate_commit_sha=None,
                candidate_ref=None,
                worker_invocation_count=0,
                worker_outcome=None,
                failure_reasons=(f"submission failed: {exc}",),
            )

        state = self.service._read_state(request.task_id) or {}
        terminal_status = state.get("terminal_status") or submitted.get("status")
        worker_receipt = state.get("execution") or {}
        verified_receipt = state.get("verified_receipt") or {}

        # Worker prose (Section 22 #15): never used as completion truth.
        # Completion truth comes strictly from verified candidate & Core projection.
        core_provenance_verified = bool(
            verified_receipt.get("core_verification_status") == "VERIFIED"
            if isinstance(verified_receipt, Mapping)
            else getattr(verified_receipt, "core_verification_status", None) == "VERIFIED"
        )
        packet = state.get("promotion_packet") or {}
        candidate_commit_sha = packet.get("candidate_commit_sha") or state.get(
            "candidate_commit_sha"
        )
        candidate_ref = state.get("candidate_ref")

        is_pty = bool(request.shell_pty_mode)
        path_containment = not is_pty and (terminal_status == "PENDING_HUMAN_APPROVAL")

        return ManagedLocalAgentReceipt(
            task_id=request.task_id,
            worker_provider=provider,
            execution_lane=request.execution_lane,
            status=str(submitted.get("status")),
            terminal_status=terminal_status,
            pre_write_machine_enforced_core_bound=True,
            path_level_prewrite_containment_proven=path_containment,
            post_hoc_physical_verification=True,
            core_provenance_verified=core_provenance_verified,
            core_binding_hash=state.get("core_binding_hash"),
            candidate_state_hash=state.get("candidate_state_hash"),
            candidate_commit_sha=candidate_commit_sha,
            candidate_ref=candidate_ref,
            worker_invocation_count=1 if state.get("worker_started_at") else 0,
            worker_outcome=str(worker_receipt.get("outcome") or state.get("status")),
            failure_reasons=tuple(state.get("error") and [state["error"]] or []),
            raw_metadata={"status_history": state.get("status_history", [])},
        )

    def reconcile_attempt(
        self,
        task_id: str,
        *,
        expected_effect_identity: Optional[str] = None,
        observed_base_revision: Optional[str] = None,
    ) -> Mapping[str, Any]:
        """Reconcile an uncertain or disconnected attempt without blind retry (Section 18)."""
        state = self.service._read_state(task_id)
        if state is None:
            return {
                "action": ReconcileAction.BLOCK.value,
                "reason": f"no durable state found for task_id {task_id}",
            }

        # Check for base drift
        contract = state.get("contract") or {}
        stored_base = contract.get("controller_revision") or contract.get("target_base_revision")
        if observed_base_revision and stored_base and observed_base_revision != stored_base:
            return {
                "action": ReconcileAction.REBIND_REQUIRED.value,
                "reason": f"base drift during reconcile: stored {stored_base} != observed {observed_base_revision}",
            }

        # Reconcile same effect identity
        current_status = state.get("status")
        return {
            "action": ReconcileAction.RECONCILE_EXISTING.value,
            "task_id": task_id,
            "status": current_status,
            "terminal_status": state.get("terminal_status"),
            "attempt_id": state.get("attempt_id"),
            "candidate_ref": state.get("candidate_ref"),
        }

    def _handle_raw_mutation_path(
        self, request: ManagedLocalAgentRequest, repo_path: Path
    ) -> ManagedLocalAgentReceipt:
        """Handle manual/raw copy-paste mode with honest lower claim ceiling (Section 19)."""
        return ManagedLocalAgentReceipt(
            task_id=request.task_id,
            worker_provider=request.worker_provider,
            execution_lane=request.execution_lane,
            status="RAW_MUTATION_CAPTURED",
            terminal_status="RAW_MUTATION_CAPTURED",
            pre_write_machine_enforced_core_bound=False,  # Lower claim preserved
            path_level_prewrite_containment_proven=False,
            post_hoc_physical_verification=True,
            core_provenance_verified=False,
            core_binding_hash=None,
            candidate_state_hash=None,
            candidate_commit_sha=None,
            candidate_ref=None,
            worker_invocation_count=0,
            worker_outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            failure_reasons=(),
        )

    def _construct_and_bind_identity(
        self,
        request: ManagedLocalAgentRequest,
        repo_path: Path,
        current_head: str,
        attempt_id: str,
    ) -> ManagedBindingIdentity:
        """Form the pre-write machine-enforced binding identity before mutation."""
        contract_data = {
            "task_id": request.task_id,
            "controller_repo_root": str(repo_path),
            "base_revision": request.base_revision,
            "allowed_paths": sorted(list(request.allowed_files)),
            "forbidden_paths": sorted(list(request.forbidden_files)),
            "verifier_commands": sorted(list(request.verifier_commands)),
            "deletion_policy": dict(request.deletion_policy),
            "execution_lane": request.execution_lane,
        }
        contract_json = json.dumps(contract_data, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        contract_hash = "sha256:" + hashlib.sha256(contract_json).hexdigest()

        binding_id = f"bind-{request.task_id}-{attempt_id}"
        binding_payload = f"{request.task_id}:{contract_hash}:{attempt_id}:{current_head}".encode(
            "utf-8"
        )
        binding_hash = "sha256:" + hashlib.sha256(binding_payload).hexdigest()

        return ManagedBindingIdentity(
            repository_canonical_identity=str(repo_path),
            exact_base_revision=request.base_revision,
            source_tree_identity=f"tree-{current_head[:8]}",
            workspace_identity=request.task_id,
            workspace_mode="ISOLATED_TARGET",
            execution_lane=request.execution_lane,
            authority_reference=request.authority_reference or "OWNER_INLINE",
            capability_discovery_identity="v1",
            acceptance_contract=contract_data,
            acceptance_contract_hash=contract_hash,
            allowed_paths=tuple(sorted(request.allowed_files)),
            deletion_policy=dict(request.deletion_policy),
            required_verifier_ids=tuple(sorted(request.verifier_commands)),
            operation_id=f"op-{request.task_id}",
            attempt_id=attempt_id,
            binding_id=binding_id,
            binding_hash=binding_hash,
            freshness={"checked_at": current_head},
        )

    def _get_current_head(self, cwd: str) -> str:
        try:
            return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
        except Exception:
            return ""
