"""Fail-closed contracts for governed Target reuse and integration closure."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


def _sha(value: str, size: int = 40) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{size}}}", value):
        raise ValueError(f"expected lowercase {size}-character hash")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class TargetResolutionMode(str, Enum):
    DIRECT_CANONICAL = "DIRECT_CANONICAL"
    REUSE_EXISTING_TARGET = "REUSE_EXISTING_TARGET"
    CREATE_ISOLATED_TARGET = "CREATE_ISOLATED_TARGET"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class TargetResolutionDecision:
    schema: str
    task_id: str
    campaign_id: str
    attempt_id: str
    mode: TargetResolutionMode
    target_id: str | None
    target_path: str | None
    target_branch: str | None
    base_revision: str
    owner_task_id: str | None
    reason: str | None = None
    reused: bool = False

    def __post_init__(self) -> None:
        if self.schema != "nexus.target_resolution_decision.v1":
            raise ValueError("unsupported Target resolution schema")
        if not self.task_id or not self.campaign_id or not self.attempt_id:
            raise ValueError("task, campaign, and attempt identity are required")
        _sha(self.base_revision)
        if self.mode is TargetResolutionMode.BLOCK and not self.reason:
            raise ValueError("blocked Target resolution requires a reason")
        if self.mode in {
            TargetResolutionMode.REUSE_EXISTING_TARGET,
            TargetResolutionMode.CREATE_ISOLATED_TARGET,
        } and not self.target_id:
            raise ValueError("isolated Target resolution requires target_id")

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.__dict__)
        value["mode"] = self.mode.value
        return value


@dataclass(frozen=True)
class ExternalAcceptanceReceipt:
    """Acceptance must come from a reviewer/verifier, never worker output."""

    schema: str
    task_id: str
    attempt_id: str
    candidate_commit: str
    receipt_hash: str
    reviewer_id: str
    passed: bool
    verifier_artifact: str

    def __post_init__(self) -> None:
        if self.schema != "nexus.external_acceptance_receipt.v1":
            raise ValueError("unsupported acceptance receipt schema")
        _sha(self.candidate_commit)
        _sha(self.receipt_hash, 64)
        if not all((self.task_id, self.attempt_id, self.reviewer_id, self.verifier_artifact)):
            raise ValueError("acceptance identity and verifier artifact are required")
        if not self.passed:
            raise ValueError("only a passed external acceptance may authorize integration")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class IntegrationAuthorizationEnvelope:
    schema: str
    task_id: str
    campaign_id: str
    task_card_hash: str
    candidate_commit: str
    candidate_receipt_hash: str
    acceptance_receipt_hash: str
    canonical_root: str
    canonical_branch: str
    expected_canonical_head: str
    canonical_dirty_baseline: str
    integration_plan_hash: str
    action_set: tuple[str, ...]
    cleanup_target_id: str
    cleanup_target_path: str
    durable_ref: str
    rollback: str
    issued_at: str
    expires_at: str | None = None
    attempt_id: str = ""
    candidate_tree_sha: str = "0" * 40
    candidate_state_hash: str = "0" * 64
    reviewer_id: str = ""
    verifier_artifact_hash: str = ""
    require_clean: bool = True
    strategy: str = ""
    verification_commands_hash: str = ""
    post_apply_commands_hash: str = ""
    cleanup_requested: bool = True
    approval_scope: str = "ALLOW_ACTION_ONCE"

    def __post_init__(self) -> None:
        if self.schema != "nexus.integration_authorization.v1":
            raise ValueError("unsupported authorization schema")
        for value, size in (
            (self.task_card_hash, 64),
            (self.candidate_receipt_hash, 64),
            (self.acceptance_receipt_hash, 64),
            (self.integration_plan_hash, 64),
        ):
            _sha(value, size)
        _sha(self.candidate_commit)
        _sha(self.expected_canonical_head)
        _sha(self.candidate_tree_sha)
        _sha(self.candidate_state_hash, 64)
        if self.verifier_artifact_hash:
            _sha(self.verifier_artifact_hash, 64)
        if self.verification_commands_hash:
            _sha(self.verification_commands_hash, 64)
        if self.post_apply_commands_hash:
            _sha(self.post_apply_commands_hash, 64)
        if self.approval_scope != "ALLOW_ACTION_ONCE":
            raise ValueError("authorization scope must be ALLOW_ACTION_ONCE")
        if not self.action_set or len(set(self.action_set)) != len(self.action_set):
            raise ValueError("authorization action_set must be non-empty and unique")
        if not all((self.task_id, self.campaign_id, self.canonical_root, self.canonical_branch,
                    self.canonical_dirty_baseline, self.cleanup_target_id,
                    self.cleanup_target_path, self.durable_ref, self.rollback, self.issued_at)):
            raise ValueError("authorization binding fields are required")

    @property
    def authorization_hash(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.__dict__)
        value["action_set"] = list(self.action_set)
        return value

    def validate_current(self, current: Mapping[str, Any], *, now: datetime | None = None) -> None:
        binding = {
            "task_id": self.task_id,
            "campaign_id": self.campaign_id,
            "task_card_hash": self.task_card_hash,
            "candidate_commit": self.candidate_commit,
            "candidate_receipt_hash": self.candidate_receipt_hash,
            "acceptance_receipt_hash": self.acceptance_receipt_hash,
            "canonical_root": self.canonical_root,
            "canonical_branch": self.canonical_branch,
            "expected_canonical_head": self.expected_canonical_head,
            "canonical_dirty_baseline": self.canonical_dirty_baseline,
            "integration_plan_hash": self.integration_plan_hash,
            "cleanup_target_id": self.cleanup_target_id,
            "cleanup_target_path": self.cleanup_target_path,
            "durable_ref": self.durable_ref,
            "attempt_id": self.attempt_id,
            "candidate_tree_sha": self.candidate_tree_sha,
            "candidate_state_hash": self.candidate_state_hash,
            "reviewer_id": self.reviewer_id,
            "verifier_artifact_hash": self.verifier_artifact_hash,
            "require_clean": self.require_clean,
            "strategy": self.strategy,
            "verification_commands_hash": self.verification_commands_hash,
            "post_apply_commands_hash": self.post_apply_commands_hash,
            "cleanup_requested": self.cleanup_requested,
            "approval_scope": self.approval_scope,
        }
        mismatches = [key for key, value in binding.items() if str(current.get(key)) != str(value)]
        if mismatches:
            raise ValueError("authorization drift: " + ", ".join(mismatches))
        if self.expires_at:
            expiry = datetime.fromisoformat(self.expires_at)
            if (now or datetime.now(timezone.utc)) >= expiry:
                raise ValueError("authorization expired")


@dataclass(frozen=True)
class IntegrationPreview:
    schema: str
    task_id: str
    target_id: str
    candidate_commit: str
    acceptance_receipt_hash: str
    canonical_branch: str
    expected_canonical_head: str
    strategy: str
    verification_commands: tuple[str, ...]
    cleanup_target_id: str
    rollback: str
    plan_hash: str

    def __post_init__(self) -> None:
        if self.schema != "nexus.integration_preview.v1":
            raise ValueError("unsupported integration preview schema")
        _sha(self.candidate_commit)
        _sha(self.acceptance_receipt_hash, 64)
        _sha(self.expected_canonical_head)
        _sha(self.plan_hash, 64)

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.__dict__)
        value["verification_commands"] = list(self.verification_commands)
        return value


@dataclass(frozen=True)
class CleanupDecision:
    schema: str
    decision: str
    task_id: str
    target_id: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    actions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.schema != "nexus.target_cleanup_decision.v1":
            raise ValueError("unsupported cleanup decision schema")
        if self.decision not in {"ELIGIBLE", "RETAIN", "BLOCK"}:
            raise ValueError("cleanup decision must be ELIGIBLE, RETAIN, or BLOCK")
        if self.decision == "ELIGIBLE" and self.reasons:
            raise ValueError("eligible cleanup cannot contain blockers")

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.__dict__)
        value["reasons"] = list(self.reasons)
        value["actions"] = list(self.actions)
        return value


@dataclass(frozen=True)
class IntegrationExecutionReceipt:
    schema: str
    task_id: str
    candidate_commit: str
    staging_commit: str
    integration_commit: str | None
    staged: bool
    applied: bool
    canonical_head_before: str
    canonical_head_after: str
    canonical_status_before: str
    canonical_status_after: str
    verifier_passed: bool
    cleanup: CleanupDecision

    def __post_init__(self) -> None:
        if self.schema != "nexus.transactional_integration_receipt.v1":
            raise ValueError("unsupported integration receipt schema")
        for value in (self.candidate_commit, self.staging_commit, self.canonical_head_before, self.canonical_head_after):
            _sha(value)
        if self.integration_commit is not None:
            _sha(self.integration_commit)

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.__dict__)
        value["cleanup"] = self.cleanup.to_dict()
        return value


# Short aliases make the contract ergonomic without adding another authority.
TargetResolution = TargetResolutionDecision
AcceptanceReceipt = ExternalAcceptanceReceipt
IntegrationAuthorization = IntegrationAuthorizationEnvelope
