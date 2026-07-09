from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.services.local_heal.quota_state import QuotaState
    from nexus.services.local_heal.degradation_policy import DegradationDecision


class DegradationController:
    def __init__(self, requested_candidate_count: int = 3, local_available: bool = True) -> None:
        self._requested_candidate_count = requested_candidate_count
        self._local_available = local_available
        self._reason_chain: list[str] = []

    def on_quota_state_change(self, quota_state: QuotaState) -> DegradationDecision:
        from nexus.services.local_heal.degradation_policy import evaluate_degradation_policy

        decision = evaluate_degradation_policy(
            quota_state=quota_state,
            requested_candidate_count=self._requested_candidate_count,
            local_available=self._local_available,
        )
        chain_entry = f"{decision.action}:{decision.reason}"
        self._reason_chain.append(chain_entry)
        if len(self._reason_chain) > 100:
            self._reason_chain = self._reason_chain[-100:]
        return decision

    def get_reason_chain(self) -> list[str]:
        return list(self._reason_chain)

    def reset_chain(self) -> None:
        self._reason_chain.clear()
