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
