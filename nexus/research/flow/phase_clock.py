from __future__ import annotations

import time
from collections.abc import Callable


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
