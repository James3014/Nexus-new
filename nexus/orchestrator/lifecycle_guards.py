"""Synchronous fail-closed guards for lifecycle action envelopes.

The guard layer validates identity and preconditions only.  It does not choose
an execution lane, create a Target, approve a Candidate, or replace the
service's lifecycle authority.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional

from nexus.contracts.lifecycle_action import (
    ApprovalScope,
    LifecycleActionEnvelope,
    MutationDomain,
    PermissionProfile,
)

CANONICAL_SOURCE_ROOT = Path("/Users/jameschen/Workspace/nexus")
_TRUSTED_TOOL_MANIFEST_HASH: Optional[str] = None


def configure_runtime_manifest_hash(value: str) -> None:
    """Register the process-owned tool-name manifest once at startup."""
    global _TRUSTED_TOOL_MANIFEST_HASH
    if _TRUSTED_TOOL_MANIFEST_HASH is not None and _TRUSTED_TOOL_MANIFEST_HASH != value:
        raise RuntimeError("TOOL_MANIFEST_RUNTIME_REBIND_FORBIDDEN")
    _TRUSTED_TOOL_MANIFEST_HASH = value


def trusted_runtime_manifest_hash() -> Optional[str]:
    return _TRUSTED_TOOL_MANIFEST_HASH


class LifecycleGuardError(RuntimeError):
    """A pre/post action guard failed before mutation was allowed."""

    def __init__(self, code: str, message: str, *, details: Optional[Mapping[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = dict(details or {})
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "nexus.lifecycle_guard_error.v1",
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
            "mutation_permitted": False,
        }


def _repo_relative(path: str, *, root: Path) -> Path:
    candidate = Path(str(path))
    if candidate.is_absolute() or ".." in candidate.parts or ".git" in candidate.parts:
        raise LifecycleGuardError("ALLOWED_PATH_INVALID", "path is not a bounded repository-relative path", details={"path": str(path)})
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise LifecycleGuardError("ALLOWED_PATH_INVALID", "path escapes canonical root", details={"path": str(path)}) from exc
    return resolved


def _head(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=3, check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise LifecycleGuardError("EXPECTED_HEAD_UNAVAILABLE", "current repository HEAD could not be read")
    return result.stdout.strip()


def _card_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise LifecycleGuardError("TASK_CARD_UNREADABLE", "task card cannot be read", details={"path": str(path)}) from exc


def pre_action_guard(
    envelope: LifecycleActionEnvelope | Mapping[str, Any],
    *,
    request: Optional[Mapping[str, Any]] = None,
    canonical_root: Path = CANONICAL_SOURCE_ROOT,
    current_head: Optional[str] = None,
    tool_manifest_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Validate one action before any mutation or provider launch.

    All failures raise ``LifecycleGuardError``.  A passing receipt is
    observational and cannot widen the caller's authority.
    """
    try:
        action = envelope if isinstance(envelope, LifecycleActionEnvelope) else LifecycleActionEnvelope.model_validate(envelope)
    except Exception as exc:
        raise LifecycleGuardError("ACTION_ENVELOPE_INVALID", "lifecycle action envelope is invalid", details={"error": str(exc)}) from exc

    trusted_manifest = tool_manifest_hash or trusted_runtime_manifest_hash()
    if trusted_manifest is None:
        raise LifecycleGuardError("TOOL_MANIFEST_UNAVAILABLE", "trusted runtime tool manifest is not configured")
    if action.tool_manifest_hash != trusted_manifest:
        raise LifecycleGuardError(
            "TOOL_MANIFEST_NAME_DRIFT", "action was created against a different public tool-name manifest",
            details={"expected": trusted_manifest, "received": action.tool_manifest_hash, "definition_scope": "tool_names_only", "deferred_gate": "P6_FULL_DEFINITION_DRIFT"},
        )

    observed_head = current_head or _head(canonical_root)
    if action.mutation and action.expected_head != observed_head:
        raise LifecycleGuardError(
            "EXPECTED_HEAD_MISMATCH", "mutation expected a different repository HEAD",
            details={"expected": action.expected_head, "observed": observed_head},
        )
    repository_paths_applicable = action.mutation_domain in {MutationDomain.REPOSITORY, MutationDomain.INTEGRATION}
    if action.mutation and repository_paths_applicable and not action.allowed_paths:
        raise LifecycleGuardError("ALLOWED_PATHS_REQUIRED", "repository mutation has no bounded allowed paths")
    if action.mutation and action.permission_profile not in {
        PermissionProfile.MUTATE_BOUNDED, PermissionProfile.CANDIDATE, PermissionProfile.INTEGRATE,
    }:
        raise LifecycleGuardError("PERMISSION_PROFILE_INVALID", "mutation profile is not allowed")
    if action.approval_scope == ApprovalScope.REJECT:
        raise LifecycleGuardError("APPROVAL_REJECTED", "approval scope explicitly rejects this action")

    bounded_paths = {str(_repo_relative(path, root=canonical_root).relative_to(canonical_root.resolve())) for path in action.allowed_paths}
    if request is not None:
        requested_paths = {str(path).strip() for path in request.get("allowed_files", ()) if str(path).strip()}
        unknown = sorted(requested_paths - bounded_paths)
        if unknown:
            raise LifecycleGuardError(
                "ALLOWED_PATH_MISMATCH", "request paths exceed the action envelope", details={"paths": unknown},
            )

    if action.task_card_path and action.task_card_hash:
        card = _repo_relative(action.task_card_path, root=canonical_root)
        observed_card_hash = _card_sha256(card)
        if observed_card_hash != action.task_card_hash:
            raise LifecycleGuardError(
                "TASK_CARD_HASH_MISMATCH", "task card changed after action binding",
                details={"path": action.task_card_path, "expected": action.task_card_hash, "observed": observed_card_hash},
            )

    return {
        "schema": "nexus.lifecycle_guard_receipt.v1",
        "guard_stage": "pre_action",
        "passed": True,
        "mutation_permitted": bool(action.mutation),
        "task_id": action.task_id,
        "attempt_id": action.attempt_id,
        "action_id": action.action_id,
        "idempotency_key": action.idempotency_key,
        "expected_head": action.expected_head,
        "observed_head": observed_head,
        "allowed_paths": sorted(bounded_paths),
        "permission_profile": action.permission_profile.value,
        "approval_scope": action.approval_scope.value,
        "mutation_domain": action.mutation_domain.value,
        "repository_paths_applicable": repository_paths_applicable,
        "idempotency_authority": "self_hosted_task_service",
        "approval_expiry_enforced": False,
        "approval_binding_level": "scope_enum_only",
        "deferred_gate": "P6_APPROVAL_BINDING_AND_EXPIRY",
    }


def post_action_receipt_formatter(
    *,
    action: LifecycleActionEnvelope | Mapping[str, Any],
    status: str,
    commit_sha: Optional[str] = None,
    receipt: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Format post-action evidence; this is not a verifier or reconciler."""
    try:
        envelope = action if isinstance(action, LifecycleActionEnvelope) else LifecycleActionEnvelope.model_validate(action)
    except Exception as exc:
        raise LifecycleGuardError("ACTION_ENVELOPE_INVALID", "post-action envelope is invalid", details={"error": str(exc)}) from exc
    observed = dict(receipt or {})
    verifier_evidence = observed.get("verifier_evidence")
    evidence_complete = bool(
        observed.get("commit_sha")
        and observed.get("receipt_hash")
        and verifier_evidence
    )
    changed_paths = list(observed.get("changed_files") or [])
    allowed = set(envelope.allowed_paths)
    paths_in_scope = not envelope.mutation or envelope.mutation_domain not in {MutationDomain.REPOSITORY, MutationDomain.INTEGRATION} or all(
        any(path == boundary or boundary.endswith("/") and path.startswith(boundary) for boundary in allowed)
        for path in changed_paths
    )
    return {
        "schema": "nexus.lifecycle_guard_receipt.v1",
        "guard_stage": "post_action",
        "passed": True,
        "task_id": envelope.task_id,
        "attempt_id": envelope.attempt_id,
        "action_id": envelope.action_id,
        "status": status,
        "commit_sha": commit_sha or observed.get("commit_sha"),
        "verifier_evidence_present": bool(verifier_evidence),
        "evidence_complete": evidence_complete,
        "paths_in_scope": paths_in_scope,
        "verification_authority": "self_hosted_task_service",
        "mutation_permitted": bool(envelope.mutation),
    }
