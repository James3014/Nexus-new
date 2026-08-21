"""Observation-only completion-path telemetry contracts.

The projection in this module is intentionally authority-free. It consumes
explicit, immutable evidence events and reports whether the Completion Path
Compression pilot can be evaluated. Missing evidence is never inferred as a
successful zero.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

SCHEMA = "nexus.completion_path_telemetry_event.v1"
NOT_OBSERVED = "NOT_OBSERVED"
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

MilestoneKind = Literal[
    "READY",
    "CANDIDATE_READY",
    "VERIFIED",
    "PR_READY",
    "MERGED",
    "RECONCILED",
    "CLOSED",
]
FrictionKind = Literal[
    "UNNECESSARY_OWNER_INTERRUPT",
    "GENUINE_EXTERNAL_OWNER_GATE",
    "UNNECESSARY_FULL_REBIND",
    "AFFECTED_DIMENSION_REBIND",
    "DUPLICATE_VERIFICATION",
    "BLOCKED_LANE_GLOBAL_STOP",
]
EventKind = Literal[
    "READY",
    "CANDIDATE_READY",
    "VERIFIED",
    "PR_READY",
    "MERGED",
    "RECONCILED",
    "CLOSED",
    "UNNECESSARY_OWNER_INTERRUPT",
    "GENUINE_EXTERNAL_OWNER_GATE",
    "UNNECESSARY_FULL_REBIND",
    "AFFECTED_DIMENSION_REBIND",
    "DUPLICATE_VERIFICATION",
    "BLOCKED_LANE_GLOBAL_STOP",
    "OBSERVATION_WINDOW_CLOSED",
]

_MILESTONE_ORDER: tuple[MilestoneKind, ...] = (
    "READY",
    "CANDIDATE_READY",
    "VERIFIED",
    "PR_READY",
    "MERGED",
    "RECONCILED",
    "CLOSED",
)
_CANDIDATE_STAGES = frozenset({"CANDIDATE_READY", "VERIFIED", "PR_READY", "MERGED", "RECONCILED", "CLOSED"})
_GITHUB_STAGES = frozenset({"PR_READY", "MERGED", "RECONCILED", "CLOSED"})
_COUNTED_FRICTION = {
    "UNNECESSARY_OWNER_INTERRUPT": "owner_interrupt_count",
    "UNNECESSARY_FULL_REBIND": "unnecessary_full_rebind_count",
    "DUPLICATE_VERIFICATION": "duplicate_verification_count",
    "BLOCKED_LANE_GLOBAL_STOP": "blocked_lane_global_stop_count",
}
_COUNTER_FIELDS = tuple(_COUNTED_FRICTION.values())


class CompletionPathEvent(BaseModel):
    """Strict immutable evidence event for one completion path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema: StrictStr = SCHEMA
    event_id: StrictStr = Field(min_length=1, max_length=256)
    issue_id: StrictStr = Field(min_length=1, max_length=256)
    kind: EventKind
    occurred_at: datetime
    evidence_ref: StrictStr = Field(min_length=1, max_length=512)
    candidate_id: StrictStr | None = Field(default=None, min_length=1, max_length=256)
    repository: StrictStr | None = Field(default=None, min_length=3, max_length=256)
    pr_number: StrictInt | None = Field(default=None, ge=1)
    candidate_head_sha: StrictStr | None = None
    merge_commit_sha: StrictStr | None = None
    current_main_sha: StrictStr | None = None

    @field_validator("schema")
    @classmethod
    def _validate_schema(cls, value: str) -> str:
        if value != SCHEMA:
            raise ValueError("COMPLETION_PATH_SCHEMA_INVALID")
        return value

    @field_validator("occurred_at")
    @classmethod
    def _validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("COMPLETION_PATH_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value.astimezone(timezone.utc)

    @field_validator("repository")
    @classmethod
    def _validate_repository(cls, value: str | None) -> str | None:
        if value is not None and not _REPOSITORY.fullmatch(value):
            raise ValueError("COMPLETION_PATH_REPOSITORY_INVALID")
        return value

    @field_validator("candidate_head_sha", "merge_commit_sha", "current_main_sha")
    @classmethod
    def _validate_git_sha(cls, value: str | None) -> str | None:
        if value is not None and not _GIT_SHA.fullmatch(value):
            raise ValueError("COMPLETION_PATH_GIT_SHA_INVALID")
        return value

    @model_validator(mode="after")
    def _validate_required_bindings(self) -> "CompletionPathEvent":
        if self.kind in _CANDIDATE_STAGES and self.candidate_id is None:
            raise ValueError("COMPLETION_PATH_CANDIDATE_ID_REQUIRED")
        if self.kind in _GITHUB_STAGES:
            if self.repository is None or self.pr_number is None or self.candidate_head_sha is None:
                raise ValueError("COMPLETION_PATH_GITHUB_BINDING_REQUIRED")
        if self.kind == "MERGED" and (self.merge_commit_sha is None or self.current_main_sha is None):
            raise ValueError("COMPLETION_PATH_MERGE_BINDING_REQUIRED")
        return self

    def semantic_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _deduplicate(events: Iterable[CompletionPathEvent | dict[str, Any]]) -> list[CompletionPathEvent]:
    by_id: dict[str, CompletionPathEvent] = {}
    ordered: list[CompletionPathEvent] = []
    for raw in events:
        event = raw if isinstance(raw, CompletionPathEvent) else CompletionPathEvent.model_validate(raw)
        previous = by_id.get(event.event_id)
        if previous is not None:
            if previous.semantic_payload() != event.semantic_payload():
                raise ValueError("COMPLETION_PATH_CONFLICTING_DUPLICATE_EVENT")
            continue
        by_id[event.event_id] = event
        ordered.append(event)
    return ordered


def project_completion_path(
    events: Iterable[CompletionPathEvent | dict[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic fail-closed telemetry projection.

    The result is observational only. It cannot authorize mutation or any
    lifecycle/GitHub action.
    """

    normalized = _deduplicate(events)
    if not normalized:
        raise ValueError("COMPLETION_PATH_EVENTS_REQUIRED")

    issue_ids = {event.issue_id for event in normalized}
    if len(issue_ids) != 1:
        raise ValueError("COMPLETION_PATH_ISSUE_ID_CONFLICT")

    normalized.sort(key=lambda event: (event.occurred_at, event.event_id))
    close_events = [event for event in normalized if event.kind == "OBSERVATION_WINDOW_CLOSED"]
    if len(close_events) > 1:
        raise ValueError("COMPLETION_PATH_MULTIPLE_WINDOW_CLOSURES")
    window_closed_at = close_events[0].occurred_at if close_events else None
    if window_closed_at is not None and any(
        event.occurred_at > window_closed_at for event in normalized if event.kind != "OBSERVATION_WINDOW_CLOSED"
    ):
        raise ValueError("COMPLETION_PATH_EVENT_AFTER_WINDOW_CLOSED")

    merged_identity_events = [event for event in normalized if event.kind == "MERGED"]
    if len({event.merge_commit_sha for event in merged_identity_events}) > 1:
        raise ValueError("COMPLETION_PATH_MERGE_COMMIT_CONFLICT")
    if len({event.current_main_sha for event in merged_identity_events}) > 1:
        raise ValueError("COMPLETION_PATH_CURRENT_MAIN_CONFLICT")

    milestones: dict[str, str] = {kind.lower() + "_at": NOT_OBSERVED for kind in _MILESTONE_ORDER}
    milestone_events: dict[str, CompletionPathEvent] = {}
    for event in normalized:
        if event.kind not in _MILESTONE_ORDER:
            continue
        previous = milestone_events.get(event.kind)
        if previous is not None:
            if previous.occurred_at != event.occurred_at or previous.semantic_payload() != event.semantic_payload():
                raise ValueError("COMPLETION_PATH_CONFLICTING_MILESTONE")
            continue
        milestone_events[event.kind] = event
        milestones[event.kind.lower() + "_at"] = event.occurred_at.isoformat()

    seen_times = [milestone_events[kind].occurred_at for kind in _MILESTONE_ORDER if kind in milestone_events]
    if any(later < earlier for earlier, later in zip(seen_times, seen_times[1:])):
        raise ValueError("COMPLETION_PATH_MILESTONE_ORDER_REGRESSION")

    candidate_ids = {
        event.candidate_id
        for event in normalized
        if event.candidate_id is not None and (event.kind in _CANDIDATE_STAGES or event.kind in _GITHUB_STAGES)
    }
    if len(candidate_ids) > 1:
        raise ValueError("COMPLETION_PATH_CANDIDATE_ID_CONFLICT")

    github_events = [event for event in normalized if event.kind in _GITHUB_STAGES]
    for attr, error in (
        ("repository", "COMPLETION_PATH_REPOSITORY_CONFLICT"),
        ("pr_number", "COMPLETION_PATH_PR_CONFLICT"),
        ("candidate_head_sha", "COMPLETION_PATH_CANDIDATE_HEAD_CONFLICT"),
    ):
        values = {getattr(event, attr) for event in github_events}
        if len(values) > 1:
            raise ValueError(error)

    merged_events = [event for event in normalized if event.kind == "MERGED"]
    if len({event.merge_commit_sha for event in merged_events}) > 1:
        raise ValueError("COMPLETION_PATH_MERGE_COMMIT_CONFLICT")
    if len({event.current_main_sha for event in merged_events}) > 1:
        raise ValueError("COMPLETION_PATH_CURRENT_MAIN_CONFLICT")

    raw_counts = {field: 0 for field in _COUNTER_FIELDS}
    observed_friction: set[str] = set()
    for event in normalized:
        field = _COUNTED_FRICTION.get(event.kind)
        if field is not None:
            raw_counts[field] += 1
            observed_friction.add(field)

    counters: dict[str, int | str] = {}
    counter_observability: dict[str, Literal["OBSERVED", "NOT_OBSERVED"]] = {}
    for field in _COUNTER_FIELDS:
        observed = window_closed_at is not None or field in observed_friction
        counter_observability[field] = "OBSERVED" if observed else NOT_OBSERVED
        counters[field] = raw_counts[field] if observed else NOT_OBSERVED

    all_milestones_observed = all(kind in milestone_events for kind in _MILESTONE_ORDER)
    required_bindings_present = (
        len(candidate_ids) == 1
        and bool(github_events)
        and all(
            event.repository is not None
            and event.pr_number is not None
            and event.candidate_head_sha is not None
            for event in github_events
        )
        and len(merged_events) == 1
        and merged_events[0].merge_commit_sha is not None
        and merged_events[0].current_main_sha is not None
    )
    evaluable = window_closed_at is not None and all_milestones_observed and required_bindings_present
    gate_pass = evaluable and all(counters[field] == 0 for field in _COUNTER_FIELDS)

    return {
        "schema": "nexus.completion_path_telemetry_projection.v1",
        "issue_id": next(iter(issue_ids)),
        "candidate_id": next(iter(candidate_ids)) if len(candidate_ids) == 1 else NOT_OBSERVED,
        "repository": github_events[0].repository if github_events else NOT_OBSERVED,
        "pr_number": github_events[0].pr_number if github_events else NOT_OBSERVED,
        "candidate_head_sha": github_events[0].candidate_head_sha if github_events else NOT_OBSERVED,
        "merge_commit_sha": merged_events[0].merge_commit_sha if len(merged_events) == 1 else NOT_OBSERVED,
        "current_main_sha": merged_events[0].current_main_sha if len(merged_events) == 1 else NOT_OBSERVED,
        **milestones,
        "observation_window_closed_at": window_closed_at.isoformat() if window_closed_at else NOT_OBSERVED,
        **counters,
        "counter_observability": counter_observability,
        "compression_gate_evaluable": evaluable,
        "compression_gate_pass": gate_pass,
        "mutation_authorized": False,
    }
