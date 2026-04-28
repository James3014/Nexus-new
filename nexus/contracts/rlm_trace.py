from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


RLM_TRACE_SCHEMA_VERSION = "rlm-trace-v1"

_ALLOWED_TRACE_FIELDS = {
    "schema_version",
    "task_id",
    "phase",
    "iteration_id",
    "parent_iteration_id",
    "action_type",
    "tool_call",
    "observation",
    "delta_hypothesis",
    "confidence",
    "allowed_tools",
    "blocked_reason",
    "policy_reason",
    "stop_reason",
    "artifact_refs",
}


@dataclass(frozen=True)
class RLMTraceEvent:
    """Auditable recursive-loop event for Nexus R/X internals."""

    task_id: str
    phase: str
    iteration_id: str
    schema_version: str = RLM_TRACE_SCHEMA_VERSION
    parent_iteration_id: str = ""
    action_type: str = ""
    tool_call: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    delta_hypothesis: str = ""
    confidence: float = 0.0
    allowed_tools: list[str] = field(default_factory=list)
    blocked_reason: str = ""
    policy_reason: str = ""
    stop_reason: str = ""
    artifact_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if not self.phase.strip():
            raise ValueError("phase is required")
        if not self.iteration_id.strip():
            raise ValueError("iteration_id is required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RLMTraceEvent":
        extra = set(payload) - _ALLOWED_TRACE_FIELDS
        if extra:
            raise ValueError(f"unknown RLMTraceEvent fields: {sorted(extra)}")
        return cls(**payload)


class RLMTraceWriter:
    """Append-only JSONL writer for RLM trace events."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event: RLMTraceEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")

