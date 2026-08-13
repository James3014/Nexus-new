#!/usr/bin/env python3

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict

PHASE_OBSERVER_HOOKS = frozenset(
    {
        "on_phase_start",
        "on_phase_end",
        "on_phase_fail",
        "on_phase_retry",
        "on_phase_block",
        "on_phase_cancel",
        "on_phase_timeout",
        "on_phase_reconcile",
        "on_task_terminal",
    }
)


@dataclass(frozen=True)
class AttemptTransitionEvent:
    """Bounded, replayable lifecycle transition for one task attempt."""

    task_id: str
    attempt_id: str
    sequence: int
    state: str
    reason: str = ""
    candidate_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    timestamp: float = field(default_factory=time.time)
    schema: str = "nexus.attempt_transition.v1"

    def __post_init__(self) -> None:
        if self.schema != "nexus.attempt_transition.v1":
            raise ValueError("unsupported attempt transition schema")
        if not isinstance(self.task_id, str) or not isinstance(self.attempt_id, str):
            raise ValueError("task_id and attempt_id must be strings")
        if not self.task_id.strip() or not self.attempt_id.strip():
            raise ValueError("task_id and attempt_id are required")
        if isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if not isinstance(self.state, str) or not self.state.strip():
            raise ValueError("state is required")
        if not isinstance(self.reason, str):
            raise ValueError("reason must be a string")
        if not isinstance(self.timestamp, (int, float)) or isinstance(self.timestamp, bool):
            raise ValueError("timestamp must be numeric")
        if not isinstance(self.candidate_refs, tuple) or not isinstance(self.evidence_refs, tuple):
            raise ValueError("event references must be tuples")
        for refs in (self.candidate_refs, self.evidence_refs):
            if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
                raise ValueError("event references must be non-empty strings")

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["candidate_refs"] = list(self.candidate_refs)
        value["evidence_refs"] = list(self.evidence_refs)
        return value


def build_attempt_transition_event(
    *, task_id: str, attempt_id: str, sequence: int, state: str,
    reason: str = "", candidate_refs: tuple[str, ...] | list[str] = (),
    evidence_refs: tuple[str, ...] | list[str] = (),
) -> AttemptTransitionEvent:
    return AttemptTransitionEvent(
        task_id=task_id, attempt_id=attempt_id, sequence=sequence, state=state,
        reason=reason, candidate_refs=tuple(candidate_refs), evidence_refs=tuple(evidence_refs),
    )


@dataclass(frozen=True)
class NexusEvent:
    """不可變的系統事件"""

    event_id: str
    task_id: str
    phase: str
    event_type: str  # e.g., "state_change", "decision", "error", "phase_start"
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_lifecycle_hook_event(
    *, task_id: str, phase: str, hook: str, payload: Dict[str, Any] | None = None
) -> NexusEvent:
    return NexusEvent(
        event_id=f"evt_{hook}_{phase}_{int(time.time() * 1000)}",
        task_id=task_id,
        phase=phase,
        event_type="lifecycle_hook",
        payload={"hook": hook, **dict(payload or {})},
    )


def build_phase_transition_event(
    *, task_id: str, phase: str, transition: str, payload: Dict[str, Any] | None = None
) -> NexusEvent:
    return NexusEvent(
        event_id=f"evt_{transition}_{phase}_{int(time.time() * 1000)}",
        task_id=task_id,
        phase=phase,
        event_type="phase_transition",
        payload={"transition": transition, **dict(payload or {})},
    )


def build_phase_observer_event(
    *, task_id: str, phase: str, hook: str, payload: Dict[str, Any] | None = None
) -> NexusEvent:
    """Build one symmetric observer event; observer failures remain fail-open."""

    if hook not in PHASE_OBSERVER_HOOKS:
        raise ValueError(f"unknown_phase_observer_hook:{hook}")
    return build_lifecycle_hook_event(task_id=task_id, phase=phase, hook=hook, payload=payload)
