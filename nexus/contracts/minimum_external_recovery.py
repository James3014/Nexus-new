"""Minimum external recovery contract for a failed Nexus governance plane.

Policy-only. This module never mutates Git, GitHub policy, runtime, routing,
Workforce, Task Cards, standing grants, or Gateway/Core state.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ALLOWED_OWNER = "James3014"
_GOVERNANCE_AUTHORITY_PATHS = frozenset(
    {
        "nexus/orchestrator/standing_grant_store.py",
        "nexus/orchestrator/unified_mcp_gateway.py",
    }
)
_GOVERNANCE_REQUIRED_CHECKS = frozenset(
    {
        "Exact-base impact gate",
        "Trusted verifier (default branch)",
        "Full published Git history secret audit",
    }
)


class RecoveryContractError(ValueError):
    pass


class RecoveryDisposition(str, Enum):
    DENY = "DENY"
    ALLOW_ONE_BOUNDED_EFFECT = "ALLOW_ONE_BOUNDED_EFFECT"
    RECONCILE_ONLY = "RECONCILE_ONLY"


class PriorEffectState(str, Enum):
    NONE = "NONE"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    CONSUMED = "CONSUMED"


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise RecoveryContractError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _require_safe_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise RecoveryContractError(f"{label}_INVALID")


def _require_sha64(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA64.fullmatch(value):
        raise RecoveryContractError(f"{label}_INVALID")


@dataclass(frozen=True)
class GovernanceIntegrationSubject:
    repository: str
    issue_number: int
    pull_request_number: int
    expected_base_sha: str
    accepted_head_sha: str
    accepted_tree_sha: str
    accepted_diff_sha256: str
    independent_acceptance_sha256: str
    required_check_names: tuple[str, ...]
    repaired_authority_paths: tuple[str, ...]
    failed_action: str
    failure_code: str
    failure_evidence_sha256: str
    merge_method: str = "merge"

    def validate(self) -> None:
        if self.repository != "James3014/Nexus-new":
            raise RecoveryContractError("RECOVERY_REPOSITORY_INVALID")
        if self.issue_number <= 0 or self.pull_request_number <= 0:
            raise RecoveryContractError("RECOVERY_ISSUE_OR_PR_INVALID")
        for value, label in (
            (self.expected_base_sha, "EXPECTED_BASE_SHA"),
            (self.accepted_head_sha, "ACCEPTED_HEAD_SHA"),
            (self.accepted_tree_sha, "ACCEPTED_TREE_SHA"),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                raise RecoveryContractError(f"{label}_INVALID")
        for value, label in (
            (self.accepted_diff_sha256, "ACCEPTED_DIFF_SHA256"),
            (self.independent_acceptance_sha256, "INDEPENDENT_ACCEPTANCE_SHA256"),
            (self.failure_evidence_sha256, "FAILURE_EVIDENCE_SHA256"),
        ):
            _require_sha64(value, label)
        if not _GOVERNANCE_REQUIRED_CHECKS.issubset(self.required_check_names):
            raise RecoveryContractError("GOVERNANCE_REQUIRED_CHECKS_MISSING")
        if not set(self.repaired_authority_paths) & _GOVERNANCE_AUTHORITY_PATHS:
            raise RecoveryContractError("REPAIR_DOES_NOT_TOUCH_FAILED_AUTHORITY_SEAM")
        if self.failed_action != "nexus_owner_standing_grant_issue":
            raise RecoveryContractError("FAILED_ACTION_NOT_STANDING_GRANT_ISSUER")
        if self.failure_code != "EXPIRED":
            raise RecoveryContractError("FAILED_AUTHORITY_CAUSE_NOT_QUALIFYING")
        if self.merge_method != "merge":
            raise RecoveryContractError("RECOVERY_MERGE_METHOD_INVALID")

    @property
    def effect_identity_sha256(self) -> str:
        self.validate()
        return _canonical_sha256(
            {
                "repository": self.repository,
                "issue_number": self.issue_number,
                "pull_request_number": self.pull_request_number,
                "expected_base_sha": self.expected_base_sha,
                "accepted_head_sha": self.accepted_head_sha,
                "accepted_tree_sha": self.accepted_tree_sha,
                "accepted_diff_sha256": self.accepted_diff_sha256,
                "independent_acceptance_sha256": self.independent_acceptance_sha256,
                "required_check_names": list(self.required_check_names),
                "repaired_authority_paths": list(self.repaired_authority_paths),
                "failed_action": self.failed_action,
                "failure_code": self.failure_code,
                "failure_evidence_sha256": self.failure_evidence_sha256,
                "merge_method": self.merge_method,
            }
        )


@dataclass(frozen=True)
class GovernanceIntegrationPhysicalEvidence:
    schema: str
    repository: str
    pull_request_number: int
    base_sha: str
    head_sha: str
    tree_sha: str
    independent_acceptance_sha256: str
    successful_required_checks: tuple[str, ...]
    repaired_authority_paths: tuple[str, ...]
    failed_action: str
    failure_code: str
    failure_evidence_sha256: str
    evidence_sha256: str
    independent: bool = True

    def assert_subject(self, subject: GovernanceIntegrationSubject) -> None:
        subject.validate()
        if self.schema != "nexus.governance_integration_physical_evidence.v1":
            raise RecoveryContractError("GOVERNANCE_EVIDENCE_SCHEMA_INVALID")
        _require_sha64(self.independent_acceptance_sha256, "INDEPENDENT_ACCEPTANCE_SHA256")
        _require_sha64(self.failure_evidence_sha256, "FAILURE_EVIDENCE_SHA256")
        _require_sha64(self.evidence_sha256, "EVIDENCE_SHA256")
        if self.independent is not True:
            raise RecoveryContractError("INDEPENDENT_EVIDENCE_REQUIRED")
        observed = (
            self.repository,
            self.pull_request_number,
            self.base_sha,
            self.head_sha,
            self.tree_sha,
            self.independent_acceptance_sha256,
            self.repaired_authority_paths,
            self.failed_action,
            self.failure_code,
            self.failure_evidence_sha256,
        )
        expected = (
            subject.repository,
            subject.pull_request_number,
            subject.expected_base_sha,
            subject.accepted_head_sha,
            subject.accepted_tree_sha,
            subject.independent_acceptance_sha256,
            subject.repaired_authority_paths,
            subject.failed_action,
            subject.failure_code,
            subject.failure_evidence_sha256,
        )
        if observed != expected:
            raise RecoveryContractError("GOVERNANCE_PHYSICAL_SUBJECT_MISMATCH")
        if not set(subject.required_check_names).issubset(self.successful_required_checks):
            raise RecoveryContractError("GOVERNANCE_REQUIRED_CHECKS_NOT_SUCCESSFUL")


@dataclass(frozen=True)
class MinimumExternalRecoveryGrant:
    schema: str
    grant_id: str
    owner_login: str
    repository: str
    subject_kind: str
    subject_id: str
    effect_kind: str
    effect_id: str
    effect_identity_sha256: str
    issued_at: datetime
    expires_at: datetime
    one_shot: bool = True
    failed_plane: str = "NORMAL_GOVERNANCE"

    def validate(self) -> None:
        if self.schema != "nexus.minimum_external_recovery_grant.v1":
            raise RecoveryContractError("GRANT_SCHEMA_INVALID")
        if self.owner_login != _ALLOWED_OWNER:
            raise RecoveryContractError("OWNER_MISMATCH")
        for value, label in (
            (self.grant_id, "GRANT_ID"),
            (self.subject_kind, "SUBJECT_KIND"),
            (self.subject_id, "SUBJECT_ID"),
            (self.effect_kind, "EFFECT_KIND"),
            (self.effect_id, "EFFECT_ID"),
        ):
            _require_safe_id(value, label)
        _require_sha64(self.effect_identity_sha256, "EFFECT_IDENTITY_SHA256")
        if "/" not in self.repository or self.repository.strip() != self.repository:
            raise RecoveryContractError("REPOSITORY_INVALID")
        if self.failed_plane != "NORMAL_GOVERNANCE":
            raise RecoveryContractError("FAILED_PLANE_INVALID")
        if self.one_shot is not True:
            raise RecoveryContractError("ONE_SHOT_REQUIRED")
        if _utc(self.expires_at) <= _utc(self.issued_at):
            raise RecoveryContractError("GRANT_WINDOW_INVALID")

    def assert_current(self, *, now: datetime) -> None:
        self.validate()
        instant = _utc(now)
        if instant < _utc(self.issued_at):
            raise RecoveryContractError("GRANT_NOT_YET_VALID")
        if instant >= _utc(self.expires_at):
            raise RecoveryContractError("GRANT_EXPIRED")


@dataclass(frozen=True)
class IndependentRecoveryEvidence:
    schema: str
    repository: str
    subject_kind: str
    subject_id: str
    effect_kind: str
    effect_id: str
    effect_identity_sha256: str
    normal_governance_available: bool
    independent: bool
    evidence_sha256: str

    def validate(self) -> None:
        if self.schema != "nexus.minimum_external_recovery_evidence.v1":
            raise RecoveryContractError("EVIDENCE_SCHEMA_INVALID")
        _require_sha64(self.effect_identity_sha256, "EFFECT_IDENTITY_SHA256")
        _require_sha64(self.evidence_sha256, "EVIDENCE_SHA256")
        if self.independent is not True:
            raise RecoveryContractError("INDEPENDENT_EVIDENCE_REQUIRED")


@dataclass(frozen=True)
class RecoveryObservation:
    repository: str
    subject_kind: str
    subject_id: str
    effect_kind: str
    effect_id: str
    effect_identity_sha256: str
    prior_effect_state: PriorEffectState


@dataclass(frozen=True)
class RecoveryDecision:
    schema: str
    disposition: RecoveryDisposition
    reason: str
    grant_id: str | None
    effect_id: str | None
    decision_sha256: str


def _decision(
    disposition: RecoveryDisposition,
    reason: str,
    *,
    grant_id: str | None,
    effect_id: str | None,
) -> RecoveryDecision:
    payload = {
        "schema": "nexus.minimum_external_recovery_decision.v1",
        "disposition": disposition.value,
        "reason": reason,
        "grant_id": grant_id,
        "effect_id": effect_id,
    }
    return RecoveryDecision(
        schema=payload["schema"],
        disposition=disposition,
        reason=reason,
        grant_id=grant_id,
        effect_id=effect_id,
        decision_sha256=_canonical_sha256(payload),
    )


def evaluate_minimum_external_recovery(
    *,
    grant: MinimumExternalRecoveryGrant | None,
    evidence: IndependentRecoveryEvidence,
    observation: RecoveryObservation,
    now: datetime,
) -> RecoveryDecision:
    evidence.validate()

    if observation.prior_effect_state is PriorEffectState.OUTCOME_UNKNOWN:
        return _decision(
            RecoveryDisposition.RECONCILE_ONLY,
            "AMBIGUOUS_PRIOR_EFFECT",
            grant_id=grant.grant_id if grant else None,
            effect_id=observation.effect_id,
        )
    if observation.prior_effect_state is PriorEffectState.CONSUMED:
        return _decision(
            RecoveryDisposition.DENY,
            "RECOVERY_REPLAY_DENIED",
            grant_id=grant.grant_id if grant else None,
            effect_id=observation.effect_id,
        )
    if grant is None:
        return _decision(
            RecoveryDisposition.DENY,
            "FRESH_EXTERNAL_OWNER_GRANT_REQUIRED",
            grant_id=None,
            effect_id=observation.effect_id,
        )

    try:
        grant.assert_current(now=now)
    except RecoveryContractError as exc:
        return _decision(
            RecoveryDisposition.DENY,
            str(exc),
            grant_id=grant.grant_id,
            effect_id=observation.effect_id,
        )

    grant_subject = (
        grant.repository,
        grant.subject_kind,
        grant.subject_id,
        grant.effect_kind,
        grant.effect_id,
        grant.effect_identity_sha256,
    )
    observed_subject = (
        observation.repository,
        observation.subject_kind,
        observation.subject_id,
        observation.effect_kind,
        observation.effect_id,
        observation.effect_identity_sha256,
    )
    evidence_subject = (
        evidence.repository,
        evidence.subject_kind,
        evidence.subject_id,
        evidence.effect_kind,
        evidence.effect_id,
        evidence.effect_identity_sha256,
    )

    if grant_subject != observed_subject or evidence_subject != observed_subject:
        return _decision(
            RecoveryDisposition.DENY,
            "RECOVERY_SUBJECT_MISMATCH",
            grant_id=grant.grant_id,
            effect_id=observation.effect_id,
        )
    if evidence.normal_governance_available is True:
        return _decision(
            RecoveryDisposition.DENY,
            "NORMAL_GOVERNANCE_AVAILABLE_USE_NORMAL_PATH",
            grant_id=grant.grant_id,
            effect_id=observation.effect_id,
        )

    return _decision(
        RecoveryDisposition.ALLOW_ONE_BOUNDED_EFFECT,
        "EXACT_EXTERNAL_RECOVERY_CONTRACT_SATISFIED",
        grant_id=grant.grant_id,
        effect_id=observation.effect_id,
    )


def evaluate_governance_integration_recovery(
    *,
    subject: GovernanceIntegrationSubject,
    grant: MinimumExternalRecoveryGrant | None,
    physical_evidence: GovernanceIntegrationPhysicalEvidence,
    observation: RecoveryObservation,
    now: datetime,
) -> RecoveryDecision:
    """Project exact physical recursion evidence into the generic one-shot contract."""
    physical_evidence.assert_subject(subject)
    identity = subject.effect_identity_sha256
    expected = (
        subject.repository,
        "pull_request",
        str(subject.pull_request_number),
        "GOVERNANCE_INTEGRATION_MERGE",
        f"pr-{subject.pull_request_number}-merge",
        identity,
    )
    observed = (
        observation.repository,
        observation.subject_kind,
        observation.subject_id,
        observation.effect_kind,
        observation.effect_id,
        observation.effect_identity_sha256,
    )
    if observed != expected:
        return _decision(
            RecoveryDisposition.DENY,
            "RECOVERY_SUBJECT_MISMATCH",
            grant_id=grant.grant_id if grant else None,
            effect_id=observation.effect_id,
        )
    evidence = IndependentRecoveryEvidence(
        schema="nexus.minimum_external_recovery_evidence.v1",
        repository=subject.repository,
        subject_kind="pull_request",
        subject_id=str(subject.pull_request_number),
        effect_kind="GOVERNANCE_INTEGRATION_MERGE",
        effect_id=f"pr-{subject.pull_request_number}-merge",
        effect_identity_sha256=identity,
        normal_governance_available=False,
        independent=physical_evidence.independent,
        evidence_sha256=physical_evidence.evidence_sha256,
    )
    return evaluate_minimum_external_recovery(
        grant=grant, evidence=evidence, observation=observation, now=now
    )
