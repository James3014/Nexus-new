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
        if type(self.normal_governance_available) is not bool:
            raise RecoveryContractError("NORMAL_GOVERNANCE_AVAILABILITY_INVALID")


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
    """Decision record for minimum external recovery.

    Note on G03 invariant: ``decision_sha256`` is a narrow decision-summary checksum
    over the canonical decision payload. It does NOT serve as standalone external
    authority; authoritative consumers re-verify exact grant, evidence, and
    observation identities rather than trusting this digest alone.
    """

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
    try:
        evidence.validate()
    except RecoveryContractError as exc:
        return _decision(
            RecoveryDisposition.DENY,
            str(exc),
            grant_id=grant.grant_id if grant else None,
            effect_id=getattr(observation, "effect_id", None),
        )

    # G01: prior_effect_state must strictly be a valid PriorEffectState enum instance
    if (
        not isinstance(observation.prior_effect_state, PriorEffectState)
        or type(observation.prior_effect_state) is not PriorEffectState
    ):
        return _decision(
            RecoveryDisposition.DENY,
            "PRIOR_EFFECT_STATE_INVALID",
            grant_id=grant.grant_id if grant else None,
            effect_id=getattr(observation, "effect_id", None),
        )

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
    if observation.prior_effect_state is not PriorEffectState.NONE:
        return _decision(
            RecoveryDisposition.DENY,
            "PRIOR_EFFECT_STATE_INVALID",
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

    # G02: only strict boolean False permits recovery; True denies; malformed values fail closed
    if type(evidence.normal_governance_available) is not bool:
        return _decision(
            RecoveryDisposition.DENY,
            "NORMAL_GOVERNANCE_AVAILABILITY_INVALID",
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
