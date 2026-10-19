"""Synchronous fail-closed guards for lifecycle action envelopes.

The guard layer validates identity and preconditions only.  It does not choose
an execution lane, create a Target, approve a Candidate, or replace the
service's lifecycle authority.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from nexus.contracts.lifecycle_action import (
    ApprovalScope,
    ContractKind,
    LifecycleActionEnvelope,
    MutationDomain,
    PermissionProfile,
    validate_owner_inline_contract,
)
from nexus.contracts.measure_dir_scope import dir_scope_enabled, split_dir_scope
from nexus.orchestrator.canonical_source_root import CANONICAL_SOURCE_ROOT, LOADED_SOURCE_ROOT
from nexus.orchestrator.measure_external_target import (
    ExternalTargetError,
    accepted_external_controller,
)
from nexus.orchestrator.task_card_scope import protected_path_reason

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


def _validate_architecture_approval_at(
    approval: Any,
    *,
    required: bool,
    task_id: str,
    attempt_id: str,
    candidate_commit_sha: str,
    candidate_tree_sha: str,
    authority_findings_sha256: str,
    _validation_time: Optional[datetime] = None,
) -> dict[str, Any] | None:
    """Validate the narrow acknowledgement for a repository authority change."""
    if not required:
        if approval is not None:
            raise LifecycleGuardError("ARCHITECTURE_APPROVAL_UNEXPECTED", "architecture approval is not required")
        return None
    if not isinstance(approval, Mapping):
        raise LifecycleGuardError("OWNER_ARCHITECTURE_APPROVAL_REQUIRED", "exact Owner Architecture Approval is required")
    allowed_keys = {
        "schema", "approval_id", "approved_by", "issued_at", "expires_at", "approval_scope",
        "bound_task_id", "bound_attempt_id", "candidate_commit_sha", "candidate_tree_sha",
        "authority_findings_sha256", "consumed_at",
    }
    unknown = sorted(set(approval) - allowed_keys)
    if unknown:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_UNKNOWN_FIELDS", "architecture approval contains unknown fields", details={"unknown": unknown})
    expected = {
        "schema": "nexus.architecture_approval.v1",
        "bound_task_id": task_id,
        "bound_attempt_id": attempt_id,
        "candidate_commit_sha": candidate_commit_sha,
        "candidate_tree_sha": candidate_tree_sha,
        "authority_findings_sha256": authority_findings_sha256,
    }
    if "task_id" in approval or "attempt_id" in approval:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_BINDING_AMBIGUOUS", "architecture approval must use bound_task_id/bound_attempt_id")
    missing = [key for key, value in expected.items() if not str(approval.get(key) or "").strip()]
    if missing:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_BINDING_INCOMPLETE", "architecture approval binding is incomplete", details={"missing": missing})
    mismatches = {key: {"expected": value, "received": approval.get(key)} for key, value in expected.items() if str(approval.get(key)) != str(value)}
    if mismatches:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_BINDING_MISMATCH", "architecture approval is bound to a different candidate", details={"mismatches": mismatches})
    if not re.fullmatch(r"[0-9a-f]{40}", str(approval.get("candidate_commit_sha"))):
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_COMMIT_INVALID", "candidate commit must be a SHA-1")
    if not re.fullmatch(r"[0-9a-f]{40}", str(approval.get("candidate_tree_sha"))):
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_TREE_INVALID", "candidate tree must be a SHA-1")
    if not re.fullmatch(r"[0-9a-f]{64}", str(approval.get("authority_findings_sha256"))):
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_FINDINGS_HASH_INVALID", "authority findings hash must be SHA-256")
    try:
        issued = datetime.fromisoformat(str(approval.get("issued_at")).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(approval.get("expires_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_EXPIRY_INVALID", "architecture approval timestamps are invalid") from exc
    validation_time = _validation_time or datetime.now(timezone.utc)
    if validation_time.tzinfo is None:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_EXPIRY_INVALID", "architecture approval validation time must be timezone-aware")
    if issued.tzinfo is None or expires.tzinfo is None or expires <= issued or issued > validation_time:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_EXPIRY_INVALID", "architecture approval expiry must follow issuance")
    if expires <= validation_time:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_EXPIRED", "architecture approval has expired")
    if approval.get("consumed_at"):
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_ALREADY_CONSUMED", "architecture approval is one-shot and already consumed")
    if not str(approval.get("approved_by") or "").strip():
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_APPROVER_REQUIRED", "architecture approval requires an Owner identity")
    if not str(approval.get("approval_id") or "").strip():
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_ID_REQUIRED", "architecture approval requires an approval id")
    if str(approval.get("approval_scope") or "ALLOW_ACTION_ONCE") != "ALLOW_ACTION_ONCE":
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_SCOPE_UNSUPPORTED", "architecture approval must be one-shot")
    return dict(approval)


def validate_architecture_approval(
    approval: Any,
    *,
    required: bool,
    task_id: str,
    attempt_id: str,
    candidate_commit_sha: str,
    candidate_tree_sha: str,
    authority_findings_sha256: str,
) -> dict[str, Any] | None:
    """Validate an unconsumed approval against the current wall clock."""
    return _validate_architecture_approval_at(
        approval,
        required=required,
        task_id=task_id,
        attempt_id=attempt_id,
        candidate_commit_sha=candidate_commit_sha,
        candidate_tree_sha=candidate_tree_sha,
        authority_findings_sha256=authority_findings_sha256,
        _validation_time=datetime.now(timezone.utc),
    )


def validate_consumed_architecture_approval(
    approval: Any,
    *,
    task_id: str,
    attempt_id: str,
    candidate_commit_sha: str,
    candidate_tree_sha: str,
    authority_findings_sha256: str,
) -> dict[str, Any]:
    """Validate the durable, already-consumed architecture acknowledgement."""
    if not isinstance(approval, Mapping) or not approval.get("consumed_at"):
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_NOT_CONSUMED", "persisted architecture approval has no consume marker")
    consumed_at = approval.get("consumed_at")
    incoming = dict(approval)
    incoming.pop("consumed_at", None)
    try:
        issued = datetime.fromisoformat(str(approval.get("issued_at")).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(approval.get("expires_at")).replace("Z", "+00:00"))
        consumed = datetime.fromisoformat(str(consumed_at).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_CONSUMED_AT_INVALID", "consume timestamp is invalid") from exc
    if consumed.tzinfo is None or issued.tzinfo is None or expires.tzinfo is None:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_CONSUMED_AT_INVALID", "consume timestamp is outside approval lifetime")
    if consumed > datetime.now(timezone.utc) or consumed < issued or consumed >= expires:
        raise LifecycleGuardError("ARCHITECTURE_APPROVAL_CONSUMED_AT_INVALID", "consume timestamp is outside approval lifetime")
    validated = _validate_architecture_approval_at(
        incoming,
        required=True,
        task_id=task_id,
        attempt_id=attempt_id,
        candidate_commit_sha=candidate_commit_sha,
        candidate_tree_sha=candidate_tree_sha,
        authority_findings_sha256=authority_findings_sha256,
        _validation_time=consumed,
    )
    return {**validated, "consumed_at": str(consumed_at)}


def validate_approval_grant(
    approval: Any,
    *,
    task_id: str,
    attempt_id: str,
    action_type: str,
    task_card_hash: Optional[str],
    contract_kind: str = ContractKind.TRACKED_TASK_CARD.value,
    contract_hash: Optional[str] = None,
    owner_inline_contract: Optional[Mapping[str, Any]] = None,
    tool_manifest_hash: str,
    full_tool_schema_hash: str,
    permission_policy_hash: str,
    lifecycle_revision: str,
    server_instance_id: str,
    allow_consumed: bool = False,
) -> dict[str, Any]:
    """Validate the versioned approval binding before candidate mutation."""
    if not isinstance(approval, Mapping):
        raise LifecycleGuardError(
            "APPROVAL_LEGACY_BINDING_INVALIDATED",
            "approval v2 is required for candidate approval",
            details={"required_schema": "nexus.approval.v2"},
        )
    required = (
        "schema", "approval_id", "approved_by", "issued_at", "expires_at",
        "bound_task_id", "bound_attempt_id", "bound_action_type", "contract_kind", "contract_hash",
        "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash",
        "lifecycle_revision", "server_instance_id",
    )
    missing = [field for field in required if not str(approval.get(field) or "").strip()]
    if str(approval.get("schema") or "") != "nexus.approval.v2":
        missing.append("schema=nexus.approval.v2")
    if missing:
        raise LifecycleGuardError(
            "APPROVAL_BINDING_INCOMPLETE",
            "approval grant is missing versioned identity fields",
            details={"missing": missing},
        )
    if str(approval.get("approval_scope") or "ALLOW_ACTION_ONCE") != "ALLOW_ACTION_ONCE":
        raise LifecycleGuardError("APPROVAL_SCOPE_UNSUPPORTED", "only ALLOW_ACTION_ONCE is supported")
    if (
        str(approval.get("bound_task_id")) != task_id
        or str(approval.get("bound_attempt_id")) != attempt_id
        or str(approval.get("bound_action_type")) != action_type
    ):
        raise LifecycleGuardError("APPROVAL_BINDING_MISMATCH", "approval is bound to a different task attempt or action")
    if contract_kind not in {ContractKind.TRACKED_TASK_CARD.value, ContractKind.OWNER_INLINE.value}:
        raise LifecycleGuardError("APPROVAL_CONTRACT_KIND_UNSUPPORTED", "approval contract kind is not lifecycle-authorized")
    if contract_kind == ContractKind.TRACKED_TASK_CARD.value:
        if not task_card_hash or not re.fullmatch(r"[0-9a-f]{64}", str(task_card_hash)):
            raise LifecycleGuardError("CANDIDATE_TASK_CARD_HASH_REQUIRED", "tracked task card approval requires a SHA-256 card hash")
        if contract_hash is None:
            contract_hash = task_card_hash
    else:
        if task_card_hash is not None:
            raise LifecycleGuardError("APPROVAL_BINDING_MISMATCH", "Owner Inline approval cannot carry task_card_hash")
        if not contract_hash or not re.fullmatch(r"[0-9a-f]{64}", str(contract_hash)):
            raise LifecycleGuardError("CONTRACT_HASH_MISMATCH", "Owner Inline approval requires a SHA-256 contract hash")
        try:
            validated = validate_owner_inline_contract(owner_inline_contract or {}, expected_task_id=task_id)
        except ValueError as exc:
            raise LifecycleGuardError(str(exc), "Owner Inline contract failed approval binding validation") from exc
        if validated["contract_hash"] != contract_hash:
            raise LifecycleGuardError("CONTRACT_HASH_MISMATCH", "Owner Inline contract hash does not match persisted identity")
    expected = {
        "contract_kind": contract_kind,
        "contract_hash": contract_hash,
        "task_card_hash": task_card_hash,
        "tool_manifest_hash": tool_manifest_hash,
        "full_tool_schema_hash": full_tool_schema_hash,
        "permission_policy_hash": permission_policy_hash,
        "lifecycle_revision": lifecycle_revision,
        "server_instance_id": server_instance_id,
    }
    binding_mismatches = {
        key: {"expected": value, "received": approval.get(key)}
        for key, value in {"contract_kind": contract_kind, "contract_hash": contract_hash, "task_card_hash": task_card_hash}.items()
        if str(approval.get(key)) != str(value)
    }
    if binding_mismatches:
        raise LifecycleGuardError("APPROVAL_BINDING_MISMATCH", "approval contract binding does not match persisted task identity", details={"mismatches": binding_mismatches})
    mismatches = {
        key: {"expected": value, "received": approval.get(key)}
        for key, value in expected.items()
        if key not in {"contract_kind", "contract_hash", "task_card_hash"}
        if str(approval.get(key)) != str(value)
    }
    if mismatches:
        raise LifecycleGuardError(
            "APPROVAL_DEFINITION_DRIFT",
            "approval identity does not match current runtime",
            details={"mismatches": mismatches},
        )
    try:
        issued = datetime.fromisoformat(str(approval["issued_at"]).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(approval["expires_at"]).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise LifecycleGuardError("APPROVAL_EXPIRY_INVALID", "approval timestamps are not ISO timestamps") from exc
    if issued.tzinfo is None or expires.tzinfo is None or expires <= issued:
        raise LifecycleGuardError("APPROVAL_EXPIRY_INVALID", "approval expiry must be after issuance")
    if expires <= datetime.now(timezone.utc):
        raise LifecycleGuardError("APPROVAL_EXPIRED", "approval grant has expired")
    if approval.get("consumed_at") and not allow_consumed:
        raise LifecycleGuardError("APPROVAL_ALREADY_CONSUMED", "approval grant was already consumed")
    if allow_consumed and not approval.get("consumed_at"):
        raise LifecycleGuardError("APPROVAL_NOT_CONSUMED", "persisted approval binding has no consume marker")
    return {
        "schema": "nexus.approval.v2",
        "approval_id": str(approval["approval_id"]),
        "approved_by": str(approval["approved_by"]),
        "issued_at": str(approval["issued_at"]),
        "expires_at": str(approval["expires_at"]),
        "bound_task_id": task_id,
        "bound_attempt_id": attempt_id,
        "bound_action_type": action_type,
        "contract_kind": contract_kind,
        "contract_hash": contract_hash,
        "task_card_hash": task_card_hash,
        "approval_scope": "ALLOW_ACTION_ONCE",
        "consumed": bool(approval.get("consumed_at")),
        "consumed_at": approval.get("consumed_at"),
    }


_UNTRACKED_GRANT_IDENTITY_FIELDS = (
    "approval_id",
    "approved_by",
    "bound_task_id",
    "bound_action_type",
)


def require_bound_approval_grant(
    grant: Any,
    *,
    task_id: str,
    attempt_id: str,
    action_type: str,
    task_card_hash: Optional[str],
    contract_kind: str,
    contract_hash: Optional[str],
    owner_inline_contract: Optional[Mapping[str, Any]] = None,
    allow_consumed: bool = False,
) -> None:
    """Require an approval grant that names its approver and binds task and action.

    Tracked-card and Owner Inline tasks use the full ``validate_approval_grant``
    contract.  A task with no card or inline contract cannot carry a contract
    hash binding, so it still needs approver identity plus task, attempt and
    action binding; a bare ``{"schema": ...}`` or ``{"consumed_at": ...}`` is
    never authority.  Runtime hashes cannot be re-derived outside the gateway,
    so they are checked for presence and taken from the grant itself.
    """
    if not isinstance(grant, Mapping):
        raise LifecycleGuardError("APPROVAL_GRANT_REQUIRED", "an approval grant is required")
    full = (
        contract_kind == ContractKind.OWNER_INLINE.value
        or bool(task_card_hash)
        or all(
            str(grant.get(field) or "").strip()
            for field in (
                "bound_task_id", "bound_attempt_id", "bound_action_type", "contract_kind",
                "contract_hash", "tool_manifest_hash", "full_tool_schema_hash",
                "permission_policy_hash", "lifecycle_revision", "server_instance_id",
            )
        )
    )
    if full:
        try:
            validate_approval_grant(
                grant,
                task_id=task_id,
                attempt_id=attempt_id,
                action_type=action_type,
                task_card_hash=task_card_hash,
                contract_kind=contract_kind,
                contract_hash=contract_hash,
                owner_inline_contract=owner_inline_contract,
                tool_manifest_hash=str(grant.get("tool_manifest_hash") or ""),
                full_tool_schema_hash=str(grant.get("full_tool_schema_hash") or ""),
                permission_policy_hash=str(grant.get("permission_policy_hash") or ""),
                lifecycle_revision=str(grant.get("lifecycle_revision") or ""),
                server_instance_id=str(grant.get("server_instance_id") or ""),
                allow_consumed=allow_consumed,
            )
        except LifecycleGuardError as exc:
            # A consumed grant was validated, including expiry, when it was consumed.
            if not (exc.code == "APPROVAL_EXPIRED" and allow_consumed and grant.get("consumed_at")):
                raise
        return
    missing = [
        field
        for field in _UNTRACKED_GRANT_IDENTITY_FIELDS
        if not str(grant.get(field) or "").strip()
    ]
    if missing:
        raise LifecycleGuardError(
            "APPROVAL_BINDING_INCOMPLETE",
            "approval grant is missing approver or binding identity",
            details={"missing": missing},
        )
    bound_attempt = str(grant.get("bound_attempt_id") or "")
    if (
        str(grant["bound_task_id"]) != task_id
        or str(grant["bound_action_type"]) != action_type
        or (attempt_id and bound_attempt != attempt_id)
    ):
        raise LifecycleGuardError(
            "APPROVAL_BINDING_MISMATCH", "approval is bound to a different task attempt or action"
        )
    if str(grant.get("approval_scope") or "ALLOW_ACTION_ONCE") != "ALLOW_ACTION_ONCE":
        raise LifecycleGuardError("APPROVAL_SCOPE_UNSUPPORTED", "only ALLOW_ACTION_ONCE is supported")
    if grant.get("expires_at") and not (allow_consumed and grant.get("consumed_at")):
        try:
            expires = datetime.fromisoformat(str(grant["expires_at"]).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise LifecycleGuardError("APPROVAL_EXPIRY_INVALID", "approval expiry is not an ISO timestamp") from exc
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise LifecycleGuardError("APPROVAL_EXPIRED", "approval grant has expired")


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


def _bounded_path(path: str, *, root: Path) -> str:
    """The envelope path as validated under ``root``.

    On a measurement Gateway with ``NEXUS_MEASURE_DIR_SCOPE=1`` (#2721) a
    ``dir/`` scope keeps its trailing ``/`` so it matches the request entry;
    the same resolve/containment check as for a file still runs.  Otherwise
    unchanged.
    """
    bounded = str(_repo_relative(path, root=root).relative_to(root.resolve()))
    if dir_scope_enabled() and split_dir_scope(path) is not None:
        if bounded == ".":
            raise LifecycleGuardError(
                "ALLOWED_PATH_INVALID",
                "directory scope covers the repository root",
                details={"path": str(path)},
            )
        # A directory covers everything below it: never a protected path or an
        # ancestor of one (``docs/`` covers ``docs/governance``), #2786 review.
        reason = protected_path_reason(path) or protected_path_reason(bounded)
        if reason is not None:
            raise LifecycleGuardError(
                "ALLOWED_PATH_PROTECTED",
                "directory scope covers a protected path",
                details={"path": str(path), "reason": reason},
            )
        return bounded + "/"
    return bounded


def guard_dir_scopes(
    envelope: LifecycleActionEnvelope | Mapping[str, Any],
    *,
    request: Optional[Mapping[str, Any]],
    canonical_root: Path = CANONICAL_SOURCE_ROOT,
) -> None:
    """The ``dir/`` scope checks of ``pre_action_guard`` on their own (#2786).

    For a caller that does not run the full guard (the ephemeral service): the
    same root/protected-path checks and the external-target requirement.  A
    no-op unless ``NEXUS_MEASURE_DIR_SCOPE=1`` was set at start.
    """
    if not dir_scope_enabled():
        return
    try:
        action = (
            envelope
            if isinstance(envelope, LifecycleActionEnvelope)
            else LifecycleActionEnvelope.model_validate(envelope)
        )
    except Exception as exc:
        raise LifecycleGuardError(
            "ACTION_ENVELOPE_INVALID",
            "lifecycle action envelope is invalid",
            details={"error": str(exc)},
        ) from exc
    for path in action.allowed_paths:
        if split_dir_scope(path) is not None:
            _bounded_path(path, root=canonical_root)
    _require_external_dir_scope(action, request, root=canonical_root)


def _require_external_dir_scope(
    action: LifecycleActionEnvelope,
    request: Optional[Mapping[str, Any]],
    *,
    root: Path,
) -> None:
    """A ``dir/`` scope exists only for a validated measurement external target (#2786).

    Every entry point that carries an action envelope runs ``pre_action_guard``,
    so this is the one place that confines directory scopes to a
    ``nexus_worker_candidate`` request whose Controller is re-validated here as
    an external measurement copy (never the Nexus-new checkout itself).
    """
    if not any(split_dir_scope(path) is not None for path in action.allowed_paths):
        return
    refused = LifecycleGuardError(
        "DIR_SCOPE_REQUIRES_EXTERNAL_TARGET",
        "a directory scope requires a measurement external target",
    )
    if not isinstance(request, Mapping) or request.get("worker_candidate_ingress") is not True:
        raise refused
    try:
        external = accepted_external_controller(
            request.get("controller_repo_root"),
            action.expected_head,
            nexus_root=root,
            forbidden_roots=(LOADED_SOURCE_ROOT,),
        )
    except ExternalTargetError as exc:
        raise LifecycleGuardError(str(exc), "external target re-validation failed") from exc
    if external is None:
        raise refused
    for path in action.allowed_paths:
        stripped = split_dir_scope(path)
        if stripped is not None:
            _external_dir_scope(stripped, path, root=external.repo_root)


def _external_dir_scope(stripped: str, path: str, *, root: Path) -> None:
    """Resolve one ``dir/`` scope inside the external Controller (#2786 r2).

    Walked component by component with ``lstat``: each component must exist and
    be a real directory, never a symlink (a tracked ``alias -> .`` or
    ``alias -> docs/governance`` would otherwise widen the scope), so the
    scope is strictly below the root.  A missing directory is refused: a
    benchmark task scopes an existing package of the pinned repository.
    """
    parts = tuple(part for part in stripped.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise LifecycleGuardError(
            "ALLOWED_PATH_INVALID",
            "directory scope is not strictly inside the external target",
            details={"path": str(path)},
        )
    current = Path(root)
    for part in parts:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except OSError as exc:
            raise LifecycleGuardError(
                "ALLOWED_PATH_INVALID",
                "directory scope does not exist in the external target",
                details={"path": str(path)},
            ) from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise LifecycleGuardError(
                "ALLOWED_PATH_INVALID",
                "directory scope is not a real directory of the external target",
                details={"path": str(path)},
            )
    relative = current.relative_to(root).as_posix()
    reason = protected_path_reason(relative)
    if reason is not None:
        raise LifecycleGuardError(
            "ALLOWED_PATH_PROTECTED",
            "directory scope covers a protected path",
            details={"path": str(path), "reason": reason},
        )


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

    bounded_paths = {_bounded_path(path, root=canonical_root) for path in action.allowed_paths}
    if dir_scope_enabled():
        _require_external_dir_scope(action, request, root=canonical_root)
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

    if action.contract_kind == ContractKind.OWNER_INLINE:
        inline = request.get("owner_inline_contract") if isinstance(request, Mapping) else None
        try:
            validated = validate_owner_inline_contract(
                inline if isinstance(inline, Mapping) else {},
                expected_task_id=action.task_id,
                expected_head=action.expected_head,
            )
        except ValueError as exc:
            raise LifecycleGuardError(str(exc), "Owner inline contract failed immutable binding validation") from exc
        if validated["contract_hash"] != action.contract_hash:
            raise LifecycleGuardError(
                "CONTRACT_HASH_MISMATCH", "Owner inline contract hash does not match action envelope",
                details={"expected": action.contract_hash, "observed": validated["contract_hash"]},
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
        "contract_kind": action.contract_kind.value,
        "contract_hash": action.contract_hash,
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
