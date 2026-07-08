from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SUPPORTED_ACTION_TYPES = frozenset([
    "memory_read",
    "memory_write",
    "memory_append",
    "memory_search",
    "memory_create",
    "memory_update",
    "memory_ignore",
])


@dataclass(frozen=True)
class MemoryActionReceipt:
    memory_action_id: str
    task_id: str
    phase: str
    action_type: str
    memory_file: str
    memory_key: str
    reason: str
    input_refs: tuple[str, ...]
    output_ref: str | None
    used_by_later_stage: bool = False
    outcome: str = "success"
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.action_type not in SUPPORTED_ACTION_TYPES:
            raise ValueError(f"Invalid action_type: {self.action_type}. Must be one of {SUPPORTED_ACTION_TYPES}")
        if self.outcome == "failed" and not self.failure_reason:
            raise ValueError("outcome='failed' requires failure_reason is not None")
        if not self.memory_action_id:
            raise ValueError("memory_action_id must not be empty")

    def to_jsonl_row(self) -> dict[str, Any]:
        return {
            "memory_action_id": self.memory_action_id,
            "task_id": self.task_id,
            "phase": self.phase,
            "action_type": self.action_type,
            "memory_file": self.memory_file,
            "memory_key": self.memory_key,
            "reason": self.reason,
            "input_refs": list(self.input_refs),
            "output_ref": self.output_ref,
            "used_by_later_stage": self.used_by_later_stage,
            "outcome": self.outcome,
            "failure_reason": self.failure_reason,
        }
