from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Mapping


LOCAL_EVENT_PIPELINE_SCHEMA = "nexus.local_event_pipeline.v1"
EVENT_TYPES = {"progress", "cancel", "downgrade", "retry", "sealed_evidence"}


@dataclass
class LocalEventPipeline:
    max_events_per_run: int = 32
    _events: dict[str, deque[dict[str, Any]]] = field(default_factory=lambda: defaultdict(deque))
    last_receipt: dict[str, Any] | None = None

    async def publish(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        evidence_seal_status: str = "NOT_APPLICABLE",
    ) -> dict[str, Any]:
        receipt = self._build_receipt(
            run_id=run_id,
            event_type=event_type,
            payload=payload or {},
            evidence_seal_status=evidence_seal_status,
        )
        self.last_receipt = receipt
        if receipt["status"] != "PASS":
            return receipt
        self._events[run_id].append(receipt["event"])
        return receipt

    def events_for(self, run_id: str) -> list[dict[str, Any]]:
        return list(self._events.get(run_id, ()))

    def _build_receipt(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        evidence_seal_status: str,
    ) -> dict[str, Any]:
        blockers: list[str] = []
        if not run_id.strip():
            blockers.append("missing_run_id")
        if event_type not in EVENT_TYPES:
            blockers.append("unknown_event_type")
        if len(self._events.get(run_id, ())) >= max(1, int(self.max_events_per_run)):
            blockers.append("event_backpressure_overflow")
        if event_type == "sealed_evidence" and evidence_seal_status != "PASS":
            blockers.append("unsealed_evidence_event_blocked")
        sequence = len(self._events.get(run_id, ())) + 1
        event = {
            "run_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "payload": dict(payload),
        }
        unique_blockers = sorted(set(blockers))
        return {
            "schema": LOCAL_EVENT_PIPELINE_SCHEMA,
            "status": "PASS" if not unique_blockers else "RETURN",
            "event": event,
            "blockers": unique_blockers,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        }
