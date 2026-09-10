"""Compatibility facade for runtime-owned task-context continuity contracts."""

from __future__ import annotations

from nexus_runtime.task_context import continuity as _continuity
from nexus_runtime.task_context.continuity import (
    EVENT_TYPES,
    MAX_CONTINUITY_COLLECTION_ITEMS,
    PROTECTED,
    REHYDRATION_PROJECTION_SCHEMA,
    REJECTED_STATES,
    SCHEMA,
    Any,
    ContinuityEvent,
    ContinuitySnapshot,
    Iterable,
    Mapping,
    Optional,
    ResumeContext,
    TaskRehydrationProjection,
    annotations,
    asdict,
    build_rehydration_projection,
    dataclass,
    events_from_attempt_records,
    field,
    hashlib,
    json,
    project,
    resume,
)

__all__ = (
    "Any", "ContinuityEvent", "ContinuitySnapshot", "EVENT_TYPES", "Iterable",
    "MAX_CONTINUITY_COLLECTION_ITEMS", "Mapping", "Optional", "PROTECTED",
    "REHYDRATION_PROJECTION_SCHEMA", "REJECTED_STATES", "ResumeContext", "SCHEMA",
    "TaskRehydrationProjection", "annotations", "asdict", "build_rehydration_projection",
    "dataclass", "events_from_attempt_records", "field", "hashlib", "json", "project", "resume",
)


def __getattr__(name: str):
    try:
        return getattr(_continuity, name)
    except AttributeError as exc:
        raise AttributeError(f"runtime task-context export is unavailable: {name}") from exc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
