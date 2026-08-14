"""Read-only normalized claimable-work discovery and filtering.

Issue #130A projection seam.  This module consumes already-normalized
work-item mappings (never raw GitHub prose) and returns an advisory ordered
list of items a caller may consider claiming.  Listing performs zero
mutation: it never acquires, validates, renews, recovers, or releases a work
claim, never touches lock/state files, and never selects a route, model,
scheduler, or Planner capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class WorkItemStatus(str, Enum):
    READY_NOW = "READY_NOW"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ClaimIntent(str, Enum):
    AUTO_CLAIM_IF_READY = "AUTO_CLAIM_IF_READY"
    MANUAL_DISPATCH = "MANUAL_DISPATCH"
    NOT_CLAIMABLE = "NOT_CLAIMABLE"


class ClaimEnforcementState(str, Enum):
    PROJECTION_ONLY = "PROJECTION_ONLY"
    REPO_ENFORCED = "REPO_ENFORCED"
    UNKNOWN = "UNKNOWN"


class WorkPriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class AdmissionDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class BlockReason(str, Enum):
    MALFORMED = "MALFORMED"
    NOT_READY = "NOT_READY"
    ROLE_INCOMPATIBLE = "ROLE_INCOMPATIBLE"
    CLAIM_INTENT_INELIGIBLE = "CLAIM_INTENT_INELIGIBLE"
    PROJECTION_ONLY = "PROJECTION_ONLY"
    PREREQUISITES_UNSATISFIED = "PREREQUISITES_UNSATISFIED"
    ADMISSION_NOT_ALLOWED = "ADMISSION_NOT_ALLOWED"
    ALREADY_OWNED = "ALREADY_OWNED"
    REALM_BLOCKED = "REALM_BLOCKED"
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"


@dataclass(frozen=True)
class WorkItem:
    """One normalized, pre-parsed claimable-work candidate."""

    issue_id: str
    status: WorkItemStatus
    roles: frozenset[str]
    claim_intent: ClaimIntent
    claim_enforcement_state: ClaimEnforcementState
    prerequisites_satisfied: bool
    admission: AdmissionDecision
    priority: WorkPriority
    direct_successor: bool = False
    owner: str | None = None
    realm: str | None = None
    provider: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "WorkItem":
        """Parse one normalized work item, failing closed on malformed input.

        Raises ``ValueError`` when a required field is missing, has the wrong
        type, or carries an unknown enum value.  Callers treat that as a
        hard exclusion, never as implicit eligibility.
        """

        def _required(key: str) -> Any:
            if key not in raw:
                raise ValueError(f"missing required field: {key}")
            return raw[key]

        issue_id = _required("issue_id")
        if not isinstance(issue_id, str) or not issue_id:
            raise ValueError("issue_id must be a non-empty string")

        roles = _required("roles")
        if (
            not isinstance(roles, (set, frozenset, list, tuple))
            or not roles
            or not all(isinstance(r, str) and r for r in roles)
        ):
            raise ValueError("roles must be a non-empty sequence of strings")

        prerequisites = _required("prerequisites_satisfied")
        if not isinstance(prerequisites, bool):
            raise ValueError("prerequisites_satisfied must be a boolean")

        direct_successor = raw.get("direct_successor", False)
        if not isinstance(direct_successor, bool):
            raise ValueError("direct_successor must be a boolean")
        for optional_key in ("owner", "realm", "provider"):
            value = raw.get(optional_key)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{optional_key} must be a non-empty string or null")

        try:
            return cls(
                issue_id=issue_id,
                status=WorkItemStatus(_required("status")),
                roles=frozenset(roles),
                claim_intent=ClaimIntent(_required("claim_intent")),
                claim_enforcement_state=ClaimEnforcementState(_required("claim_enforcement_state")),
                prerequisites_satisfied=prerequisites,
                admission=AdmissionDecision(_required("admission")),
                priority=WorkPriority(_required("priority")),
                direct_successor=direct_successor,
                owner=raw.get("owner"),
                realm=raw.get("realm"),
                provider=raw.get("provider"),
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from None


@dataclass(frozen=True)
class BlockedWorkItem:
    issue_id: str
    reason: BlockReason


@dataclass(frozen=True)
class ClaimableWorkProjection:
    claimable: tuple[WorkItem, ...]
    blocked: tuple[BlockedWorkItem, ...]


_PRIORITY_RANK = {WorkPriority.P0: 0, WorkPriority.P1: 1, WorkPriority.P2: 2}


def _block_reason(
    item: WorkItem,
    *,
    role: str,
    current_owners: frozenset[str],
    blocked_realms: frozenset[str],
    blocked_providers: frozenset[str],
) -> BlockReason | None:
    if item.status is not WorkItemStatus.READY_NOW:
        return BlockReason.NOT_READY
    if role not in item.roles:
        return BlockReason.ROLE_INCOMPATIBLE
    if item.claim_intent is not ClaimIntent.AUTO_CLAIM_IF_READY:
        return BlockReason.CLAIM_INTENT_INELIGIBLE
    if item.claim_enforcement_state is not ClaimEnforcementState.REPO_ENFORCED:
        return BlockReason.PROJECTION_ONLY
    if item.prerequisites_satisfied is not True:
        return BlockReason.PREREQUISITES_UNSATISFIED
    if item.admission is not AdmissionDecision.ALLOW:
        return BlockReason.ADMISSION_NOT_ALLOWED
    if item.owner is not None or item.issue_id in current_owners:
        return BlockReason.ALREADY_OWNED
    if item.realm is not None and item.realm in blocked_realms:
        return BlockReason.REALM_BLOCKED
    if item.provider is not None and item.provider in blocked_providers:
        return BlockReason.PROVIDER_BLOCKED
    return None


def _sort_key(item: WorkItem) -> tuple[int, int]:
    # Explicit direct successor first, then P0 > P1 > P2.  ``sorted`` is
    # stable, so equal keys preserve the input order (ties remain ties).
    return (0 if item.direct_successor else 1, _PRIORITY_RANK[item.priority])


def list_claimable_work(
    items: Sequence[Mapping[str, Any] | WorkItem],
    *,
    role: str,
    current_owners: frozenset[str] = frozenset(),
    blocked_realms: frozenset[str] = frozenset(),
    blocked_providers: frozenset[str] = frozenset(),
) -> ClaimableWorkProjection:
    """Return the advisory ordered projection of claimable work.

    The projection is deterministic and read-only.  Malformed or unknown
    inputs are excluded with ``MALFORMED`` instead of being treated as
    eligible.  This function never claims, locks, or mutates anything.
    """

    claimable: list[WorkItem] = []
    blocked: list[BlockedWorkItem] = []
    for raw in items:
        if isinstance(raw, WorkItem):
            item = raw
        else:
            try:
                item = WorkItem.from_mapping(raw)
            except ValueError:
                issue_id = (
                    raw.get("issue_id", "<unknown>") if isinstance(raw, Mapping) else "<unknown>"
                )
                blocked.append(
                    BlockedWorkItem(issue_id=str(issue_id), reason=BlockReason.MALFORMED)
                )
                continue
        reason = _block_reason(
            item,
            role=role,
            current_owners=current_owners,
            blocked_realms=blocked_realms,
            blocked_providers=blocked_providers,
        )
        if reason is None:
            claimable.append(item)
        else:
            blocked.append(BlockedWorkItem(issue_id=item.issue_id, reason=reason))

    return ClaimableWorkProjection(
        claimable=tuple(sorted(claimable, key=_sort_key)),
        blocked=tuple(blocked),
    )
