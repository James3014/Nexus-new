from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.services.local_heal.quota_state import QuotaState


class QuotaMonitor:
    def __init__(self, poll_interval_seconds: int = 30) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._history: list[QuotaState] = []
        self._previous_state: QuotaState | None = None

    @property
    def poll_interval_seconds(self) -> int:
        return self._poll_interval_seconds

    def observe(self) -> QuotaState:
        from nexus.services.local_heal.quota_state import QuotaState as QS, resolve_quota_state

        state = resolve_quota_state()
        self._history.append(state)
        if len(self._history) > 100:
            self._history = self._history[-100:]
        self._previous_state = state
        return state

    def get_state_history(self) -> list[QuotaState]:
        return list(self._history)

    def get_current_state(self) -> QuotaState | None:
        if self._history:
            return self._history[-1]
        return None

    def detect_change(self) -> QuotaState | None:
        before = self._previous_state
        current = self.observe()
        if before is not None and current == before:
            return None
        return current
