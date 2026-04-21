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
