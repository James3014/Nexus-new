from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SelectionTraceEvent:
    event_id: str
    parent_event_id: str | None
    phase: str
    event_type: str
    candidate_index: int | None
    candidate_hash: str | None
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    decision: str
    reason: str
    reversible: bool
    receipt_ref: str = ""


SUPPORTED_EVENT_TYPES = frozenset([
    "candidate_observed",
    "candidate_feature_extracted",
    "candidate_duplicate_grouped",
    "candidate_scored",
    "popularity_trap_detected",
    "winner_selected",
    "selection_fail_closed",
])


@dataclass
class SelectionTrace:
    trace_id: str
    task_id: str
    events: list[SelectionTraceEvent] = field(default_factory=list)
    root_event_id: str | None = None
    final_event_id: str | None = None
    fail_closed: bool = False
    _frozen: bool = False

    def append_event(self, event: SelectionTraceEvent) -> None:
        if self._frozen:
            raise RuntimeError("Trace is frozen after final_event_id is set")

        # Auto-assign event_id
        if not event.event_id:
            event = SelectionTraceEvent(
                event_id=f"evt-{len(self.events)}",
                parent_event_id=event.parent_event_id,
                phase=event.phase,
                event_type=event.event_type,
                candidate_index=event.candidate_index,
                candidate_hash=event.candidate_hash,
                inputs=event.inputs,
                outputs=event.outputs,
                decision=event.decision,
                reason=event.reason,
                reversible=event.reversible,
                receipt_ref=event.receipt_ref,
            )

        # Auto-link parent_event_id
        if event.parent_event_id is None and self.events:
            # Find last event with different event_type
            for prev in reversed(self.events):
                if prev.event_type != event.event_type:
                    from dataclasses import replace
                    event = replace(event, parent_event_id=prev.event_id)
                    break

        self.events.append(event)
        self.final_event_id = event.event_id

        if self.root_event_id is None:
            self.root_event_id = event.event_id

    def freeze(self) -> None:
        self._frozen = True

    def to_receipt_fragment(self) -> dict[str, Any]:
        return {
            "p5_trace_event_count": len(self.events),
            "p5_trace_fail_closed": self.fail_closed,
            "p5_trace_events": [
                {
                    "event_id": e.event_id,
                    "phase": e.phase,
                    "event_type": e.event_type,
                    "candidate_index": e.candidate_index,
                    "decision": e.decision,
                    "reason": e.reason,
                    "reversible": e.reversible,
                }
                for e in self.events
            ],
            "p5_trace_root_event_id": self.root_event_id or "",
            "p5_trace_final_event_id": self.final_event_id or "",
        }
