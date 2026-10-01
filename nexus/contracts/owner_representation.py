"""Canonical fail-closed authority contract for EXTERNAL_PUBLICATION /
OWNER_REPRESENTATION.

This is the single canonical owner for publicly representing the Nexus Owner
or project to an external destination.  It defines policy evidence only: no
mint, inference, inheritance, widening, or self-approval is performed here and
no transport is invoked from this module.

Core invariants enforced by the consuming seam (``owner_representation.py``):

.. code-block:: text

   AUTHENTICATED       != OWNER_AUTHORIZED
   CAN_EDIT_CODE       != CAN_PUBLISH
   CAN_COMMIT          != CAN_PUBLISH
   CAN_PUSH            != CAN_REPRESENT_OWNER
   CAN_MERGE           != CAN_REPRESENT_OWNER
   TASK_COMPLETION     != CAN_REPRESENT_OWNER
   PUSH_DENIED         != ISSUE_PUBLICATION_AUTHORIZED
   MODEL/WORKER OUTPUT != OWNER STATEMENT

A third-party external Owner-representation grant is one-shot by default; a
completed external publication cannot be replayed into a second write.  One
grant never implies follow-up actions (``CREATE_ISSUE != COMMENT != EDIT !=
CLOSE != CREATE_PR != PUBLIC_FORK != PUBLISH_BRANCH ...``).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)

from nexus.contracts.autonomy_goal import canonical_autonomy_hash

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._#-]{0,127}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")


def _safe_id(value: str, field: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{field.upper()}_INVALID")
    return value


def _safe_target(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not _SAFE_TARGET.fullmatch(value):
        raise ValueError(f"{field.upper()}_INVALID")
    return value


def _sha64(value: str, field: str) -> str:
    if not _SHA64.fullmatch(value):
        raise ValueError(f"{field.upper()}_INVALID")
    return value


class OwnerRepresentationBlocked(RuntimeError):
    """Raised by the publication seam when a proposed effect is not authorized."""


def canonical_publication_content_hash(title: str, body: str) -> str:
    """Return the canonical SHA-256 over exactly what will be published."""
    return canonical_autonomy_hash({"title": title, "body": body})


class ExternalDestinationKind(str, Enum):
    OWNER_CONTROLLED_INTERNAL_COLLABORATION = "OWNER_CONTROLLED_INTERNAL_COLLABORATION"
    THIRD_PARTY_OR_EXTERNAL_OWNER_REPRESENTATION = "THIRD_PARTY_OR_EXTERNAL_OWNER_REPRESENTATION"
    UNKNOWN = "UNKNOWN"


class ExternalPublicationEffect(str, Enum):
    """Exact action classes covered by OWNER_REPRESENTATION authority."""

    CREATE_ISSUE = "CREATE_ISSUE"
    COMMENT = "COMMENT"
    EDIT = "EDIT"
    CLOSE = "CLOSE"
    CREATE_PR = "CREATE_PR"
    PUBLIC_FORK = "PUBLIC_FORK"
    PUBLISH_BRANCH_AS_EXTERNAL_CONTRIBUTION = "PUBLISH_BRANCH_AS_EXTERNAL_CONTRIBUTION"
    PUBLIC_TRANSPORT_WRITE = "PUBLIC_TRANSPORT_WRITE"


class PublicationDerivation(str, Enum):
    """How a proposed effect came to exist.  Inference carries no authority."""

    EXPLICIT_OWNER_DECISION = "EXPLICIT_OWNER_DECISION"
    OWNER_INTERACTIVE_CONFIRMATION = "OWNER_INTERACTIVE_CONFIRMATION"
    PUSH_DENIED = "PUSH_DENIED"
    TASK_COMPLETION = "TASK_COMPLETION"
    WORKER_OUTPUT = "WORKER_OUTPUT"
    UNTYPED = "UNTYPED"


_INFERENCE_DERIVATIONS = frozenset({
    PublicationDerivation.PUSH_DENIED,
    PublicationDerivation.TASK_COMPLETION,
    PublicationDerivation.WORKER_OUTPUT,
    PublicationDerivation.UNTYPED,
})

# Public fork and branch-published-as-external-contribution always represent
# the Owner/project publicly regardless of the target repository ownership.
_ALWAYS_EXTERNAL_EFFECTS = frozenset({
    ExternalPublicationEffect.PUBLIC_FORK,
    ExternalPublicationEffect.PUBLISH_BRANCH_AS_EXTERNAL_CONTRIBUTION,
})


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExternalDestination(_FrozenModel):
    """One exact public destination host/account/repository."""

    schema: Literal["nexus.external_destination.v1"] = "nexus.external_destination.v1"
    host: StrictStr
    owner_account: StrictStr
    repository: StrictStr

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        if not value or value != value.strip() or not _HOST.fullmatch(value):
            raise ValueError("HOST_INVALID")
        if "/" in value or ":" in value or "@" in value:
            raise ValueError("HOST_INVALID")
        return value

    @field_validator("owner_account", "repository")
    @classmethod
    def validate_account(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @property
    def repository_id(self) -> str:
        return f"{self.owner_account}/{self.repository}"

    @property
    def canonical_remote(self) -> str:
        return f"https://{self.host}/{self.owner_account}/{self.repository}.git"


class ExternalContentEnvelope(_FrozenModel):
    """Frozen purpose envelope: narrow purpose text plus exact content hash."""

    schema: Literal["nexus.external_content_envelope.v1"] = "nexus.external_content_envelope.v1"
    purpose: StrictStr
    content_hash: StrictStr

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        text = value.strip()
        if not text or text != value or len(text) > 256:
            raise ValueError("PURPOSE_INVALID")
        return text

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _sha64(value, "content_hash")


class ExternalPublicationProposal(_FrozenModel):
    """One proposed external effect, bound to exact content and intent."""

    schema: Literal["nexus.external_publication_proposal.v1"] = (
        "nexus.external_publication_proposal.v1"
    )
    destination: ExternalDestination
    effect: ExternalPublicationEffect
    target: StrictStr | None = None
    title: StrictStr
    body: StrictStr
    purpose: StrictStr
    content_hash: StrictStr
    actor: StrictStr
    transport: StrictStr
    operation_id: StrictStr
    derivation: PublicationDerivation = PublicationDerivation.UNTYPED
    requested_at: AwareDatetime | None = None

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str | None) -> str | None:
        return _safe_target(value, "target")

    @field_validator("actor", "transport", "operation_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        text = value.strip()
        if not text or text != value or len(text) > 256:
            raise ValueError("PURPOSE_INVALID")
        return text

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _sha64(value, "content_hash")

    @model_validator(mode="after")
    def validate_content_bound(self) -> "ExternalPublicationProposal":
        expected = canonical_publication_content_hash(self.title, self.body)
        if self.content_hash != expected:
            raise ValueError("CONTENT_HASH_MISMATCH")
        requires_target = {
            ExternalPublicationEffect.COMMENT,
            ExternalPublicationEffect.EDIT,
            ExternalPublicationEffect.CLOSE,
            ExternalPublicationEffect.CREATE_PR,
        }
        if self.effect in requires_target and self.target is None:
            raise ValueError("TARGET_REQUIRED")
        if self.effect is ExternalPublicationEffect.CREATE_ISSUE and self.target is not None:
            raise ValueError("TARGET_FORBIDDEN_FOR_CREATE_ISSUE")
        return self


class OwnerRepresentationGrantSpec(_FrozenModel):
    """All Owner-grant policy fields; hash is bound by the concrete grant."""

    schema: Literal["nexus.owner_representation_grant.v1"] = "nexus.owner_representation_grant.v1"
    grant_id: StrictStr
    issued_by: StrictStr
    owner_id: StrictStr
    coordinator_id: StrictStr
    destination: ExternalDestination
    effect: ExternalPublicationEffect
    target: StrictStr | None = None
    content_hash: StrictStr
    purpose: StrictStr
    actor: StrictStr
    transport: StrictStr
    operation_id: StrictStr
    replay_mode: Literal["ONE_SHOT"] = "ONE_SHOT"
    granted_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None
    revocation_reason: StrictStr | None = None
    superseded_by: StrictStr | None = None

    @field_validator(
        "grant_id",
        "issued_by",
        "owner_id",
        "coordinator_id",
        "actor",
        "transport",
        "operation_id",
    )
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str | None) -> str | None:
        return _safe_target(value, "target")

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _sha64(value, "content_hash")

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        text = value.strip()
        if not text or text != value or len(text) > 256:
            raise ValueError("PURPOSE_INVALID")
        return text

    @field_validator("revocation_reason")
    @classmethod
    def validate_revocation_reason(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value.strip() != value):
            raise ValueError("REVOCATION_REASON_INVALID")
        return value

    @field_validator("superseded_by")
    @classmethod
    def validate_superseded_by(cls, value: str | None) -> str | None:
        if value is not None:
            _safe_id(value, "superseded_by")
        return value

    @model_validator(mode="after")
    def validate_grant(self) -> "OwnerRepresentationGrantSpec":
        if self.expires_at <= self.granted_at:
            raise ValueError("GRANT_EXPIRY_INVALID")
        if (self.revoked_at is None) != (self.revocation_reason is None):
            raise ValueError("REVOCATION_BINDING_INVALID")
        return self


class OwnerRepresentationGrant(OwnerRepresentationGrantSpec):
    """Immutable one-shot Owner grant for one exact external publication.

    A worker/model/agent can never mint, infer, inherit, widen, or self-approve
    this grant.  Building this object validates and hash-binds a grant, but a
    grant object alone is inert: only a durable receipt persisted by the
    canonical :class:`OwnerRepresentationGrantStore` makes it authoritative,
    and the consuming seam verifies that store-backed trust chain immediately
    before any effect.
    """

    grant_hash: StrictStr

    @field_validator("grant_hash")
    @classmethod
    def validate_grant_hash_format(cls, value: str) -> str:
        return _sha64(value, "grant_hash")

    @model_validator(mode="after")
    def validate_grant_hash(self) -> "OwnerRepresentationGrant":
        payload = self.model_dump(mode="json", exclude={"grant_hash"})
        if self.grant_hash != canonical_autonomy_hash(payload):
            raise ValueError("GRANT_HASH_INVALID")
        return self


class OwnerExactPublicationAuthorizationSpec(_FrozenModel):
    """Immutable exact Owner authorization for one exact external publication effect.

    Issued only by the Owner.  Binds the exact destination, effect, target,
    content hash, narrow purpose, actor, transport, operation, and grant hash.
    A worker/coordinator/agent can never mint, infer, inherit, widen, or
    self-approve this authority.
    """

    schema: Literal["nexus.owner_exact_publication_authorization.v1"] = (
        "nexus.owner_exact_publication_authorization.v1"
    )
    authorization_id: StrictStr
    owner_id: StrictStr
    coordinator_id: StrictStr
    destination: ExternalDestination
    effect: ExternalPublicationEffect
    target: StrictStr | None = None
    content_hash: StrictStr
    purpose: StrictStr
    actor: StrictStr
    transport: StrictStr
    operation_id: StrictStr
    grant_hash: StrictStr
    owner_key_id: StrictStr
    owner_signature: StrictStr
    owner_signature_algorithm: Literal["RSA-SHA256"] = "RSA-SHA256"
    replay_mode: Literal["ONE_SHOT"] = "ONE_SHOT"
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None
    revocation_reason: StrictStr | None = None
    superseded_by: StrictStr | None = None

    @field_validator(
        "authorization_id",
        "owner_id",
        "coordinator_id",
        "actor",
        "transport",
        "operation_id",
        "owner_key_id",
    )
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str | None) -> str | None:
        return _safe_target(value, "target")

    @field_validator("content_hash", "grant_hash")
    @classmethod
    def validate_hashes(cls, value: str, info) -> str:
        return _sha64(value, info.field_name)

    @field_validator("owner_signature")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        if not value or len(value) > 4096:
            raise ValueError("OWNER_SIGNATURE_INVALID")
        return value

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        text = value.strip()
        if not text or text != value or len(text) > 256:
            raise ValueError("PURPOSE_INVALID")
        return text

    @field_validator("revocation_reason")
    @classmethod
    def validate_revocation_reason(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value.strip() != value):
            raise ValueError("REVOCATION_REASON_INVALID")
        return value

    @field_validator("superseded_by")
    @classmethod
    def validate_superseded_by(cls, value: str | None) -> str | None:
        if value is not None:
            _safe_id(value, "superseded_by")
        return value

    @model_validator(mode="after")
    def validate_authorization(self) -> "OwnerExactPublicationAuthorizationSpec":
        if self.expires_at <= self.issued_at:
            raise ValueError("AUTHORIZATION_EXPIRY_INVALID")
        if (self.revoked_at is None) != (self.revocation_reason is None):
            raise ValueError("REVOCATION_BINDING_INVALID")
        return self


class OwnerExactPublicationAuthorization(OwnerExactPublicationAuthorizationSpec):
    """Hash-sealed immutable Owner authorization for one exact external publication."""

    authorization_hash: StrictStr

    @field_validator("authorization_hash")
    @classmethod
    def validate_auth_hash_format(cls, value: str) -> str:
        return _sha64(value, "authorization_hash")

    @model_validator(mode="after")
    def validate_authorization_hash(self) -> "OwnerExactPublicationAuthorization":
        payload = self.model_dump(mode="json", exclude={"authorization_hash"})
        if self.authorization_hash != canonical_autonomy_hash(payload):
            raise ValueError("AUTHORIZATION_HASH_INVALID")
        return self


class InternalCollaborationBound(_FrozenModel):
    """One explicitly Owner-controlled internal collaboration contract.

    A destination/effect is ``OWNER_CONTROLLED_INTERNAL_COLLABORATION`` only
    when it is bound here; repo ownership alone never classifies it.
    """

    schema: Literal["nexus.internal_collaboration_bound.v1"] = (
        "nexus.internal_collaboration_bound.v1"
    )
    contract_id: StrictStr
    owner_id: StrictStr
    destination: ExternalDestination
    authorized_effects: tuple[ExternalPublicationEffect, ...]

    @field_validator("contract_id", "owner_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _safe_id(value, info.field_name)

    @field_validator("authorized_effects")
    @classmethod
    def canonicalize_effects(
        cls, values: tuple[ExternalPublicationEffect, ...]
    ) -> tuple[ExternalPublicationEffect, ...]:
        if not values:
            raise ValueError("AUTHORIZED_EFFECTS_REQUIRED")
        normalized = tuple(sorted(set(values), key=lambda item: item.value))
        if _ALWAYS_EXTERNAL_EFFECTS & set(normalized):
            raise ValueError("ALWAYS_EXTERNAL_EFFECT_FORBIDDEN_IN_INTERNAL_BOUND")
        return normalized


class OwnerRepresentationReason(str, Enum):
    GRANT_INVALID = "GRANT_INVALID"
    PROPOSAL_INVALID = "PROPOSAL_INVALID"
    DESTINATION_UNKNOWN = "DESTINATION_UNKNOWN"
    DESTINATION_MISMATCH = "DESTINATION_MISMATCH"
    ACTION_OUT_OF_SCOPE = "ACTION_OUT_OF_SCOPE"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    CONTENT_SUBSTITUTION = "CONTENT_SUBSTITUTION"
    PURPOSE_SUBSTITUTION = "PURPOSE_SUBSTITUTION"
    GRANT_NOT_YET_VALID = "GRANT_NOT_YET_VALID"
    GRANT_EXPIRED = "GRANT_EXPIRED"
    GRANT_REVOKED = "GRANT_REVOKED"
    GRANT_SUPERSEDED = "GRANT_SUPERSEDED"
    STANDING_EXTERNAL_GRANT_NOT_SUPPORTED = "STANDING_EXTERNAL_GRANT_NOT_SUPPORTED"
    COORDINATOR_MISMATCH = "COORDINATOR_MISMATCH"
    ACTOR_MISMATCH = "ACTOR_MISMATCH"
    TRANSPORT_MISMATCH = "TRANSPORT_MISMATCH"
    OPERATION_MISMATCH = "OPERATION_MISMATCH"
    OWNER_REPRESENTATION_REQUIRED = "OWNER_REPRESENTATION_REQUIRED"
    PUSH_DENIED_IS_NOT_PUBLICATION_AUTHORITY = "PUSH_DENIED_IS_NOT_PUBLICATION_AUTHORITY"
    PUBLICATION_AUTHORITY_NON_INFERABLE = "PUBLICATION_AUTHORITY_NON_INFERABLE"
    FOLLOWUP_NOT_IMPLIED = "FOLLOWUP_NOT_IMPLIED"
    PUBLICATION_BLOCKED = "PUBLICATION_BLOCKED"
    GRANT_NOT_ISSUED = "GRANT_NOT_ISSUED"
    GRANT_ALREADY_ISSUED = "GRANT_ALREADY_ISSUED"
    OPERATION_CONFLICT = "OPERATION_CONFLICT"
    OPERATION_TERMINAL_OR_INFLIGHT = "OPERATION_TERMINAL_OR_INFLIGHT"
    GRANT_REUSED = "GRANT_REUSED"
    REPLAY_FORBIDDEN = "REPLAY_FORBIDDEN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    DISPATCH_NOT_PREPARED = "DISPATCH_NOT_PREPARED"
    INTERNAL_AUTOMATION_PASSTHROUGH = "INTERNAL_AUTOMATION_PASSTHROUGH"
    ISSUANCE_AUTHORIZATION_REQUIRED = "ISSUANCE_AUTHORIZATION_REQUIRED"
    ISSUANCE_AUTHORIZATION_REJECTED = "ISSUANCE_AUTHORIZATION_REJECTED"
    ISSUANCE_AUTHORITY_CHANGED = "ISSUANCE_AUTHORITY_CHANGED"
    ISSUANCE_AUTHORITY_NOT_LIVE = "ISSUANCE_AUTHORITY_NOT_LIVE"
    ISSUANCE_PERMIT_SLOT_CONSUMED = "ISSUANCE_PERMIT_SLOT_CONSUMED"
    PERMIT_ALREADY_MINTED = "PERMIT_ALREADY_MINTED"
    EXACT_OWNER_AUTHORIZATION_REQUIRED = "EXACT_OWNER_AUTHORIZATION_REQUIRED"
    EXACT_OWNER_AUTHORIZATION_REJECTED = "EXACT_OWNER_AUTHORIZATION_REJECTED"
    EXACT_OWNER_AUTHORIZATION_MISMATCH = "EXACT_OWNER_AUTHORIZATION_MISMATCH"
    EXACT_OWNER_AUTHORIZATION_EXPIRED = "EXACT_OWNER_AUTHORIZATION_EXPIRED"
    EXACT_OWNER_AUTHORIZATION_REVOKED = "EXACT_OWNER_AUTHORIZATION_REVOKED"
    EXACT_OWNER_AUTHORIZATION_CONSUMED = "EXACT_OWNER_AUTHORIZATION_CONSUMED"


class OwnerRepresentationOutcome(str, Enum):
    GRANT_MATCH = "GRANT_MATCH"
    BLOCKED = "BLOCKED"


class OwnerRepresentationDecision(_FrozenModel):
    schema: Literal["nexus.owner_representation_decision.v1"] = (
        "nexus.owner_representation_decision.v1"
    )
    outcome: OwnerRepresentationOutcome
    reason_codes: tuple[OwnerRepresentationReason, ...] = ()
    publication_authorized: StrictBool = False
    grant_hash: StrictStr | None = None
    proposal_hash: StrictStr
    decision_hash: StrictStr
    claim_ceiling: Literal["OWNER_REPRESENTATION_EXACT_ONE_SHOT_ONLY"] = (
        "OWNER_REPRESENTATION_EXACT_ONE_SHOT_ONLY"
    )

    @field_validator("grant_hash", "proposal_hash", "decision_hash")
    @classmethod
    def validate_hashes(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return _sha64(value, info.field_name)

    @model_validator(mode="after")
    def validate_decision(self) -> "OwnerRepresentationDecision":
        matched = self.outcome is OwnerRepresentationOutcome.GRANT_MATCH
        if self.publication_authorized is not matched:
            raise ValueError("DECISION_AUTHORITY_INVALID")
        if matched != (not self.reason_codes):
            raise ValueError("DECISION_REASONS_INVALID")
        if matched and self.grant_hash is None:
            raise ValueError("DECISION_GRANT_HASH_REQUIRED")
        payload = self.model_dump(mode="json", exclude={"decision_hash"})
        if self.decision_hash != canonical_autonomy_hash(payload):
            raise ValueError("DECISION_HASH_INVALID")
        return self


def _decision(
    *,
    outcome: OwnerRepresentationOutcome,
    reason_codes: tuple[OwnerRepresentationReason, ...],
    proposal_hash: str,
    grant_hash: str | None = None,
) -> OwnerRepresentationDecision:
    payload = {
        "schema": "nexus.owner_representation_decision.v1",
        "outcome": outcome.value,
        "reason_codes": [code.value for code in reason_codes],
        "publication_authorized": outcome is OwnerRepresentationOutcome.GRANT_MATCH,
        "grant_hash": grant_hash,
        "proposal_hash": proposal_hash,
        "claim_ceiling": "OWNER_REPRESENTATION_EXACT_ONE_SHOT_ONLY",
    }
    return OwnerRepresentationDecision.model_validate({
        **payload,
        "decision_hash": canonical_autonomy_hash(payload),
    })


def _proposal_hash(proposal: ExternalPublicationProposal) -> str:
    return canonical_autonomy_hash(proposal.model_dump(mode="json"))


def classification(
    destination: ExternalDestination,
    effect: ExternalPublicationEffect,
    bounds: tuple[InternalCollaborationBound, ...] = (),
) -> ExternalDestinationKind:
    """Classify one destination/effect, failing closed on ambiguity.

    An explicitly bound internal collaboration contract makes the effect
    ``OWNER_CONTROLLED_INTERNAL_COLLABORATION``.  ``PUBLIC_FORK`` and
    ``PUBLISH_BRANCH_AS_EXTERNAL_CONTRIBUTION`` are always external
    representation.  Anything else on a recognized public host is
    ``THIRD_PARTY_OR_EXTERNAL_OWNER_REPRESENTATION``; unrecognized hosts are
    ``UNKNOWN`` (BLOCK).
    """
    if effect in _ALWAYS_EXTERNAL_EFFECTS:
        return ExternalDestinationKind.THIRD_PARTY_OR_EXTERNAL_OWNER_REPRESENTATION
    for bound in bounds:
        if bound.destination == destination and effect in bound.authorized_effects:
            return ExternalDestinationKind.OWNER_CONTROLLED_INTERNAL_COLLABORATION
    if destination.host in {"github.com", "gitlab.com", "bitbucket.org"}:
        return ExternalDestinationKind.THIRD_PARTY_OR_EXTERNAL_OWNER_REPRESENTATION
    return ExternalDestinationKind.UNKNOWN


def evaluate_owner_representation(
    grant: OwnerRepresentationGrant | Mapping[str, Any],
    proposal: ExternalPublicationProposal | Mapping[str, Any],
    now: datetime | None = None,
) -> OwnerRepresentationDecision:
    """Resolve one exact one-shot Owner grant against one exact proposal.

    Pure: no state, no transport, no replay ledger.  Replay/one-shot
    consumption is enforced by the durable publication seam.
    """
    try:
        validated_grant = OwnerRepresentationGrant.model_validate(
            grant.model_dump(mode="json") if isinstance(grant, OwnerRepresentationGrant) else grant
        )
    except Exception:
        validated_grant = None
    try:
        validated_proposal = ExternalPublicationProposal.model_validate(
            proposal.model_dump(mode="json")
            if isinstance(proposal, ExternalPublicationProposal)
            else proposal
        )
    except Exception:
        return _decision(
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=(OwnerRepresentationReason.PROPOSAL_INVALID,),
            proposal_hash="0" * 64,
            grant_hash=(validated_grant.grant_hash if validated_grant is not None else None),
        )

    proposal_hash = _proposal_hash(validated_proposal)
    if validated_grant is None:
        reasons: list[OwnerRepresentationReason] = [
            OwnerRepresentationReason.GRANT_INVALID,
            OwnerRepresentationReason.PUBLICATION_AUTHORITY_NON_INFERABLE,
        ]
        if validated_proposal.derivation is PublicationDerivation.PUSH_DENIED:
            reasons.append(OwnerRepresentationReason.PUSH_DENIED_IS_NOT_PUBLICATION_AUTHORITY)
        return _decision(
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=tuple(dict.fromkeys(reasons)),
            proposal_hash=proposal_hash,
        )

    if validated_grant.replay_mode != "ONE_SHOT":
        return _decision(
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=(OwnerRepresentationReason.STANDING_EXTERNAL_GRANT_NOT_SUPPORTED,),
            proposal_hash=proposal_hash,
            grant_hash=validated_grant.grant_hash,
        )
    if validated_grant.superseded_by is not None:
        return _decision(
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=(OwnerRepresentationReason.GRANT_SUPERSEDED,),
            proposal_hash=proposal_hash,
            grant_hash=validated_grant.grant_hash,
        )

    reasons: list[OwnerRepresentationReason] = []
    if validated_grant.destination != validated_proposal.destination:
        reasons.append(OwnerRepresentationReason.DESTINATION_MISMATCH)
    if validated_grant.effect != validated_proposal.effect:
        reasons.append(OwnerRepresentationReason.FOLLOWUP_NOT_IMPLIED)
    if validated_grant.target != validated_proposal.target:
        reasons.append(OwnerRepresentationReason.TARGET_MISMATCH)
    if validated_grant.content_hash != validated_proposal.content_hash:
        reasons.append(OwnerRepresentationReason.CONTENT_SUBSTITUTION)
    if validated_grant.purpose != validated_proposal.purpose:
        reasons.append(OwnerRepresentationReason.PURPOSE_SUBSTITUTION)
    if validated_grant.actor != validated_proposal.actor:
        reasons.append(OwnerRepresentationReason.ACTOR_MISMATCH)
    if validated_grant.transport != validated_proposal.transport:
        reasons.append(OwnerRepresentationReason.TRANSPORT_MISMATCH)
    if validated_grant.operation_id != validated_proposal.operation_id:
        reasons.append(OwnerRepresentationReason.OPERATION_MISMATCH)
    if reasons:
        return _decision(
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=tuple(dict.fromkeys(reasons)),
            proposal_hash=proposal_hash,
            grant_hash=validated_grant.grant_hash,
        )

    current = (
        now
        if now is not None
        else (
            validated_proposal.requested_at
            if validated_proposal.requested_at is not None
            else datetime.now(timezone.utc)
        )
    )
    if current < validated_grant.granted_at:
        reasons.append(OwnerRepresentationReason.GRANT_NOT_YET_VALID)
    if current >= validated_grant.expires_at:
        reasons.append(OwnerRepresentationReason.GRANT_EXPIRED)
    if validated_grant.revoked_at is not None:
        reasons.append(OwnerRepresentationReason.GRANT_REVOKED)
    if reasons:
        return _decision(
            outcome=OwnerRepresentationOutcome.BLOCKED,
            reason_codes=tuple(dict.fromkeys(reasons)),
            proposal_hash=proposal_hash,
            grant_hash=validated_grant.grant_hash,
        )
    return _decision(
        outcome=OwnerRepresentationOutcome.GRANT_MATCH,
        reason_codes=(),
        proposal_hash=proposal_hash,
        grant_hash=validated_grant.grant_hash,
    )


def is_inference_derivation(value: PublicationDerivation) -> bool:
    return value in _INFERENCE_DERIVATIONS


__all__ = [
    "ExternalContentEnvelope",
    "ExternalDestination",
    "ExternalDestinationKind",
    "ExternalPublicationEffect",
    "ExternalPublicationProposal",
    "InternalCollaborationBound",
    "OwnerExactPublicationAuthorization",
    "OwnerExactPublicationAuthorizationSpec",
    "OwnerRepresentationBlocked",
    "OwnerRepresentationDecision",
    "OwnerRepresentationGrant",
    "OwnerRepresentationGrantSpec",
    "OwnerRepresentationOutcome",
    "OwnerRepresentationReason",
    "PublicationDerivation",
    "canonical_publication_content_hash",
    "classification",
    "evaluate_owner_representation",
    "is_inference_derivation",
]
