"""Typed desired-vs-loaded Gateway convergence contract for issue #1064.

This module owns policy and evidence shapes only. It never performs a Gateway
replacement effect, grants issue #526 authority, or creates a second effect
ledger / desired-state store.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator

GATEWAY_CONVERGENCE_SCHEMA = "nexus.gateway_convergence.v1"
GATEWAY_CONVERGENCE_EFFECT_OWNER = "ISSUE_526_GATEWAY_RECOVERY"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha40(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if not _SHA40_RE.fullmatch(normalized):
        raise ValueError(f"{label}_MALFORMED")
    return normalized


class DesiredDeploymentMode(str, Enum):
    PINNED = "PINNED"
    TRACK_ACCEPTED_MAIN = "TRACK_ACCEPTED_MAIN"


class UpstreamFreshness(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class EvidenceState(str, Enum):
    SAFE = "SAFE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class RecoveryEffectState(str, Enum):
    PRE_EFFECT_READY = "PRE_EFFECT_READY"
    EFFECT_MAY_HAVE_STARTED = "EFFECT_MAY_HAVE_STARTED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    TERMINAL_SUCCESS = "TERMINAL_SUCCESS"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


class ConvergenceAction(str, Enum):
    NOOP = "NOOP"
    BLOCKED = "BLOCKED"
    REQUEST_RECOVERY = "REQUEST_RECOVERY"
    START_PREPARED_RECOVERY = "START_PREPARED_RECOVERY"
    COALESCE_PRE_EFFECT_TARGET = "COALESCE_PRE_EFFECT_TARGET"
    RECONCILE_RECOVERY = "RECONCILE_RECOVERY"


class ConvergenceReason(str, Enum):
    ALREADY_CONVERGED = "ALREADY_CONVERGED"
    PINNED_ALREADY_LOADED = "PINNED_ALREADY_LOADED"
    UPSTREAM_UNKNOWN = "UPSTREAM_UNKNOWN"
    READINESS_BLOCKED = "READINESS_BLOCKED"
    READINESS_UNKNOWN = "READINESS_UNKNOWN"
    QUIESCENCE_BLOCKED = "QUIESCENCE_BLOCKED"
    QUIESCENCE_UNKNOWN = "QUIESCENCE_UNKNOWN"
    BACKOFF_ACTIVE = "BACKOFF_ACTIVE"
    EFFECT_RECONCILIATION_REQUIRED = "EFFECT_RECONCILIATION_REQUIRED"
    PRE_EFFECT_TARGET_SUPERSEDED = "PRE_EFFECT_TARGET_SUPERSEDED"
    PREPARED_EFFECT_MATCHES_DESIRED = "PREPARED_EFFECT_MATCHES_DESIRED"
    EXPLICIT_POLICY_REQUIRES_RECOVERY = "EXPLICIT_POLICY_REQUIRES_RECOVERY"
    EFFECT_TERMINAL_FAILURE = "EFFECT_TERMINAL_FAILURE"
    POSTFLIGHT_OBSERVATION_DRIFT = "POSTFLIGHT_OBSERVATION_DRIFT"


class DesiredDeploymentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal["nexus.gateway_convergence.v1"] = GATEWAY_CONVERGENCE_SCHEMA
    mode: DesiredDeploymentMode
    desired_commit: StrictStr
    desired_tree: StrictStr

    @field_validator("desired_commit")
    @classmethod
    def _commit(cls, value: str) -> str:
        return _sha40(value, "DESIRED_COMMIT")

    @field_validator("desired_tree")
    @classmethod
    def _tree(cls, value: str) -> str:
        return _sha40(value, "DESIRED_TREE")

    @property
    def generation_id(self) -> str:
        return canonical_hash(
            {
                "schema": self.schema_name,
                "mode": self.mode.value,
                "desired_commit": self.desired_commit,
                "desired_tree": self.desired_tree,
            }
        )


class GatewayConvergenceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    loaded_commit: StrictStr
    loaded_tree: StrictStr
    upstream_freshness: UpstreamFreshness
    observed_upstream_main_head: StrictStr | None = None
    readiness_state: EvidenceState
    quiescence_state: EvidenceState
    server_instance_id: StrictStr | None = None

    @field_validator("loaded_commit")
    @classmethod
    def _loaded_commit(cls, value: str) -> str:
        return _sha40(value, "LOADED_COMMIT")

    @field_validator("loaded_tree")
    @classmethod
    def _loaded_tree(cls, value: str) -> str:
        return _sha40(value, "LOADED_TREE")

    @field_validator("observed_upstream_main_head")
    @classmethod
    def _upstream_head(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _sha40(value, "OBSERVED_UPSTREAM_MAIN_HEAD")

    @model_validator(mode="after")
    def _freshness_consistency(self) -> "GatewayConvergenceObservation":
        if (
            self.upstream_freshness is not UpstreamFreshness.UNKNOWN
            and self.observed_upstream_main_head is None
        ):
            raise ValueError("KNOWN_UPSTREAM_FRESHNESS_REQUIRES_OBSERVED_HEAD")
        return self


class RecoveryEffectObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: RecoveryEffectState
    operation_id: StrictStr
    request_id: StrictStr
    idempotency_fence: StrictStr
    target_commit: StrictStr
    target_tree: StrictStr
    postflight_verified: bool = False
    postflight_loaded_commit: StrictStr | None = None
    postflight_loaded_tree: StrictStr | None = None
    postflight_receipt_hash: StrictStr | None = None

    @field_validator("operation_id", "request_id", "idempotency_fence")
    @classmethod
    def _identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 256:
            raise ValueError("RECOVERY_EFFECT_IDENTITY_MALFORMED")
        return normalized

    @field_validator("target_commit")
    @classmethod
    def _target_commit(cls, value: str) -> str:
        return _sha40(value, "RECOVERY_TARGET_COMMIT")

    @field_validator("target_tree")
    @classmethod
    def _target_tree(cls, value: str) -> str:
        return _sha40(value, "RECOVERY_TARGET_TREE")

    @field_validator("postflight_loaded_commit")
    @classmethod
    def _postflight_commit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _sha40(value, "POSTFLIGHT_LOADED_COMMIT")

    @field_validator("postflight_loaded_tree")
    @classmethod
    def _postflight_tree(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _sha40(value, "POSTFLIGHT_LOADED_TREE")

    @field_validator("postflight_receipt_hash")
    @classmethod
    def _postflight_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not _SHA64_RE.fullmatch(normalized):
            raise ValueError("POSTFLIGHT_RECEIPT_HASH_MALFORMED")
        return normalized

    @model_validator(mode="after")
    def _postflight_consistency(self) -> "RecoveryEffectObservation":
        success_fields = (
            self.postflight_loaded_commit,
            self.postflight_loaded_tree,
            self.postflight_receipt_hash,
        )
        if self.state is RecoveryEffectState.TERMINAL_SUCCESS:
            if not self.postflight_verified or any(value is None for value in success_fields):
                raise ValueError("TERMINAL_SUCCESS_REQUIRES_VERIFIED_POSTFLIGHT")
            if (
                self.postflight_loaded_commit != self.target_commit
                or self.postflight_loaded_tree != self.target_tree
            ):
                raise ValueError("TERMINAL_SUCCESS_POSTFLIGHT_TARGET_MISMATCH")
        elif self.postflight_verified or any(value is not None for value in success_fields):
            raise ValueError("NON_SUCCESS_EFFECT_MUST_NOT_CARRY_POSTFLIGHT_SUCCESS")
        return self


class GatewayConvergenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal["nexus.gateway_convergence.v1"] = GATEWAY_CONVERGENCE_SCHEMA
    policy: DesiredDeploymentPolicy
    observation: GatewayConvergenceObservation
    active_effect: RecoveryEffectObservation | None = None
    not_before: datetime | None = None

    @model_validator(mode="after")
    def _time_bounds(self) -> "GatewayConvergenceRequest":
        if self.not_before is not None and self.not_before.tzinfo is None:
            raise ValueError("NOT_BEFORE_MUST_BE_TIMEZONE_AWARE")
        return self


class GatewayConvergenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal["nexus.gateway_convergence.v1"] = GATEWAY_CONVERGENCE_SCHEMA
    action: ConvergenceAction
    reason: ConvergenceReason
    generation_id: StrictStr
    policy_mode: DesiredDeploymentMode
    desired_commit: StrictStr
    desired_tree: StrictStr
    observed_loaded_commit: StrictStr
    observed_loaded_tree: StrictStr
    effect_owner: Literal["ISSUE_526_GATEWAY_RECOVERY"] = GATEWAY_CONVERGENCE_EFFECT_OWNER
    effect_authorized: Literal[False] = False
    retry_authorized: Literal[False] = False
    operation_id: StrictStr | None = None
    request_id: StrictStr | None = None
    idempotency_fence: StrictStr | None = None
    superseded_target_commit: StrictStr | None = None
    superseded_target_tree: StrictStr | None = None
    next_generation_required: bool = False
