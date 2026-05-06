#!/usr/bin/env python3

from typing import Any, Dict
import time
from dataclasses import dataclass, field, asdict


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


def build_lifecycle_hook_event(*, task_id: str, phase: str, hook: str, payload: Dict[str, Any] | None = None) -> NexusEvent:
    return NexusEvent(
        event_id=f"evt_{hook}_{phase}_{int(time.time()*1000)}",
        task_id=task_id,
        phase=phase,
        event_type="lifecycle_hook",
        payload={"hook": hook, **dict(payload or {})},
    )


def build_phase_transition_event(*, task_id: str, phase: str, transition: str, payload: Dict[str, Any] | None = None) -> NexusEvent:
    return NexusEvent(
        event_id=f"evt_{transition}_{phase}_{int(time.time()*1000)}",
        task_id=task_id,
        phase=phase,
        event_type="phase_transition",
        payload={"transition": transition, **dict(payload or {})},
    )
