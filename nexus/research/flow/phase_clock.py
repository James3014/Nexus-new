from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class AutoFlowPhaseClock:
    def __init__(self, now: Callable[[], float] | None = None):
        self._now = now or time.monotonic
        self._phase_started_at = self._now()
        self.phase_wall_sec: dict[str, float] = {}

    def mark(self, phase: str) -> float:
        now = self._now()
        elapsed = round(now - self._phase_started_at, 4)
        self.phase_wall_sec[phase] = elapsed
        self._phase_started_at = now
        return elapsed

    def restart(self) -> None:
        self._phase_started_at = self._now()


def apply_auto_flow_timing_payload(
    payload: dict[str, Any],
    *,
    cli_elapsed_sec: float,
    phase_wall_sec: dict[str, float],
    breakdown_sec: dict[str, float],
) -> None:
    timing = payload.setdefault("timing", {})
    usage_trace = payload.setdefault("nexus_usage_trace", {})
    timing["cli_elapsed_sec"] = round(float(cli_elapsed_sec), 4)
    timing["phase_wall_sec"] = phase_wall_sec
    timing["breakdown_sec"] = breakdown_sec
    usage_trace["phase_wall_sec"] = phase_wall_sec
