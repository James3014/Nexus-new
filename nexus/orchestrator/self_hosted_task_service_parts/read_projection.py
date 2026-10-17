"""Read/receipt projection cluster of ``SelfHostedTaskService``.

Big-file split S2 (Issue #2542). ``_ReadProjectionMixin`` holds the status and receipt
projections moved out of ``nexus/orchestrator/self_hosted_task_service.py``:
``wait_task``, ``list_actionable_tasks``, ``get_task``, ``get_task_snapshot``,
``get_receipt``, ``get_promotion_packet``, ``_snapshot_target_integrity``,
``evaluate_candidate_acceptance`` and ``project_candidate_acceptance_for_retry``.
Their source lines are verbatim, except that every facade-module name they load that the
facade defines or that tests patch on the facade (``time``,
``project_autonomy_submission``, ``reduce_candidate_acceptance``,
``project_candidate_acceptance_for_runtime_repair``) is resolved at call time through
``_service_module()``. ``CandidateAcceptanceRequest`` and ``IndependentReviewReceipt``
are imported from ``nexus.orchestrator.acceptance_loop`` (the same objects the facade
binds; nothing patches them), so ``isinstance`` narrowing keeps working for type checks.

Not all of it is lock-free: ``get_receipt`` reads through ``_read_state`` (state lock),
and ``project_candidate_acceptance_for_retry`` writes through ``_mutate_state`` for a
REPAIRABLE verdict. The state lock and state store stay in the facade class and are
reached through ``self``.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

from nexus.orchestrator.acceptance_loop import CandidateAcceptanceRequest, IndependentReviewReceipt

if TYPE_CHECKING:
    from nexus.orchestrator.acceptance_loop import CandidateAcceptanceResult


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _ReadProjectionMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService
        state_dir: Path

        def _read_state(self, task_id: str) -> Optional[dict[str, Any]]: ...

        def _read_state_snapshot(self, task_id: str) -> Optional[dict[str, Any]]: ...

        def _latest_archived_state(
            self, task_id: str
        ) -> tuple[Optional[Path], Optional[dict[str, Any]]]: ...

        @classmethod
        def _with_task_action(cls, state: dict[str, Any]) -> dict[str, Any]: ...

        @classmethod
        def _task_action_envelope(cls, state: Mapping[str, Any]) -> dict[str, Any]: ...

        @classmethod
        def _projected_blocker(cls, state: Mapping[str, Any]) -> Optional[dict[str, Any]]: ...

        @staticmethod
        def _approval_requirements(state: Mapping[str, Any]) -> dict[str, Any]: ...

    # fmt: off
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

        deadline = _service_module().time.monotonic() + timeout_seconds
        while True:
            # Waiting is a read-only operator surface.  Do not reconcile or
            # acquire the lifecycle write lock while polling durable state.
            state = self._read_state_snapshot(task_id)
            if state is not None:
                state = self._with_task_action(state)
            if state is None:
                return None
            envelope = state.get("task_action") or self._task_action_envelope(state)
            detailed_state = dict(state)
            detailed_state.pop("operator_outcome_receipt", None)
            detailed_state.pop("operator_outcome_receipts", None)
            if envelope.get("action_state") != "IN_PROGRESS":
                result = {
                    **(detailed_state if include_details else {
                        "schema": "nexus.self_hosted_task_status.v1",
                        "task_id": state.get("task_id"),
                        "status": state.get("status"),
                        "promotion_status": state.get("promotion_status"),
                        "verification_verdict": state.get("verification_verdict"),
                        "found": state.get("found", True),
                        "state_valid": state.get("state_valid", True),
                        "blocker": self._projected_blocker(state),
                        "retry_authorized": state.get("retry_authorized"),
                        "task_action": envelope,
                    }),
                    "wait": {
                        "timed_out": False,
                        "timeout_seconds": timeout_seconds,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                }
                return result
            if _service_module().time.monotonic() >= deadline:
                envelope = {**envelope, "wait_timed_out": True}
                return {
                    **(detailed_state if include_details else {
                        "schema": "nexus.self_hosted_task_status.v1",
                        "task_id": state.get("task_id"),
                        "status": state.get("status"),
                        "promotion_status": state.get("promotion_status"),
                        "verification_verdict": state.get("verification_verdict"),
                        "found": state.get("found", True),
                        "state_valid": state.get("state_valid", True),
                        "blocker": self._projected_blocker(state),
                        "retry_authorized": state.get("retry_authorized"),
                        "task_action": envelope,
                    }),
                    "task_action": envelope,
                    "wait": {
                        "timed_out": True,
                        "timeout_seconds": timeout_seconds,
                        "poll_interval_seconds": poll_interval_seconds,
                    },
                }
            _service_module().time.sleep(min(poll_interval_seconds, max(0.0, deadline - _service_module().time.monotonic())))

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

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        result = self.get_task_snapshot(task_id, include_details=True)
        if result is not None:
            result.pop("operator_outcome_receipt", None)
            result.pop("operator_outcome_receipts", None)
        return result

    def get_task_snapshot(
        self, task_id: str, *, include_details: bool = False
    ) -> Optional[dict[str, Any]]:
        """Read status without reconciliation or state-lock acquisition."""
        state = self._read_state_snapshot(task_id)
        if state is None:
            return None
        approval_requirements = self._approval_requirements(state)
        if include_details:
            details = {**state, "approval_requirements": approval_requirements}
            details.pop("operator_outcome_receipt", None)
            details.pop("operator_outcome_receipts", None)
            return details
        action = state.get("task_action") or self._task_action_envelope(state)
        return {
            "schema": "nexus.self_hosted_task_status.v1",
            "task_id": state.get("task_id"),
            "status": state.get("status"),
            "promotion_status": state.get("promotion_status"),
            "verification_verdict": state.get("verification_verdict"),
            "found": state.get("found", True),
            "state_valid": state.get("state_valid", True),
            "blocker": self._projected_blocker(state),
            "retry_authorized": state.get("retry_authorized"),
            "task_action": action,
            "autonomy": _service_module().project_autonomy_submission(state),
            "approval_requirements": approval_requirements,
        }

    def get_receipt(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None:
            return None
        contract = state.get("contract") or {}
        lease = state.get("lease") or {}
        packet = state.get("promotion_packet") or {}
        candidate = state.get("candidate") or {}
        verified_receipt = state.get("verified_receipt") or {}
        candidate_collaboration_provenance = (
            candidate.get("collaboration_provenance")
            or verified_receipt.get("collaboration_provenance")
            or packet.get("collaboration_provenance")
            or lease.get("collaboration_provenance")
        )
        collaboration_provenance = (
            candidate_collaboration_provenance
            or state.get("collaboration_provenance")
        )
        archived_path, _ = self._latest_archived_state(task_id)
        return {
            "task_id": task_id,
            "attempt_id": state.get("attempt_id"),
            "status": state.get("status"),
            "submitted_at": state.get("submitted_at"),
            "telemetry": state.get("telemetry") or {"wall_time_ms": 0, "overhead_ms": 0},
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
            "execution_authority": state.get("execution_authority"),
            "provider_receipt_authoritative": state.get(
                "provider_receipt_authoritative", False
            ),
            "workforce_admission_authoritative": state.get(
                "workforce_admission_authoritative", False
            ),
            "runtime_development_mapping": state.get("runtime_development_mapping"),
            "collaboration_realm": state.get("collaboration_realm") or contract.get("collaboration_realm"),
            "submission_collaboration_provenance": (
                state.get("submission_collaboration_provenance")
                or state.get("collaboration_provenance")
            ),
            "collaboration_provenance": collaboration_provenance,
            "candidate_collaboration_provenance": candidate_collaboration_provenance,
            "error": state.get("error"),
            "operator_outcome_receipt": state.get("operator_outcome_receipt"),
            "operator_outcome_receipts": state.get("operator_outcome_receipts", []),
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

    @staticmethod
    def evaluate_candidate_acceptance(
        request: CandidateAcceptanceRequest | Mapping[str, Any],
        review: IndependentReviewReceipt | Mapping[str, Any],
        *,
        verified_repair_evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate independent evidence without mutating lifecycle state."""
        request_obj = (
            request
            if isinstance(request, CandidateAcceptanceRequest)
            else CandidateAcceptanceRequest(**dict(request))
        )
        review_obj = (
            review
            if isinstance(review, IndependentReviewReceipt)
            else IndependentReviewReceipt(**dict(review))
        )
        result: CandidateAcceptanceResult = _service_module().reduce_candidate_acceptance(
            request_obj,
            review_obj,
            verified_repair_evidence=verified_repair_evidence,
        )
        return result.to_dict()

    def project_candidate_acceptance_for_retry(
        self,
        request: CandidateAcceptanceRequest | Mapping[str, Any],
        review: IndependentReviewReceipt | Mapping[str, Any],
        *,
        verified_repair_evidence: Mapping[str, Any] | None = None,
        repair_target: str = "IMPLEMENTATION",
    ) -> dict[str, Any]:
        """Project one existing REPAIRABLE acceptance into Runtime retry evidence.

        The existing acceptance reducer remains authoritative. This method only
        persists the exact evidence bindings needed by the canonical Runtime
        RetryService and grants no approval, routing, worker, verifier,
        completion, merge, release, or production authority.
        """
        return _service_module().project_candidate_acceptance_for_runtime_repair(
            self,
            request,
            review,
            verified_repair_evidence=verified_repair_evidence,
            repair_target=repair_target,
        )
    # fmt: on
