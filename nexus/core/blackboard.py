from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping


class Blackboard:
    """Append-only phase artifact journal with immutable read views."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def append(self, phase: str, key: str, value: Any) -> Mapping[str, Any]:
        phase = str(phase or "").strip()
        key = str(key or "").strip()
        if not phase:
            raise ValueError("blackboard_phase_required")
        if not key:
            raise ValueError("blackboard_key_required")
        event = {
            "event_id": len(self._events) + 1,
            "phase": phase,
            "key": key,
            "value": deepcopy(value),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._events.append(event)
        return _freeze(event)

    def view(self, phase_filter: str | None = None) -> Mapping[str, Any]:
        phase = str(phase_filter).strip() if phase_filter is not None else None
        events = [event for event in self._events if phase is None or event["phase"] == phase]
        latest: dict[str, Any] = {}
        for event in events:
            latest[str(event["key"])] = deepcopy(event["value"])
        return MappingProxyType(
            {
                "events": tuple(_freeze(event) for event in events),
                "latest": _freeze(latest),
            }
        )

    def has(self, key: str, phase_filter: str | None = None) -> bool:
        key = str(key or "").strip()
        if not key:
            return False
        return key in self.view(phase_filter).get("latest", {})


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(val) for key, val in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return deepcopy(value)
