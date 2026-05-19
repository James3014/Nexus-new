from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CandidatePoolPolicy:
    local_support_candidates: int
    local_support_score_cap: float
    reason_codes: tuple[str, ...]

    @property
    def enabled(self) -> bool:
        return self.local_support_candidates > 0


def decide_candidate_pool_policy(
    *,
    autoreason_enabled: bool = False,
    ddtree_enabled: bool,
    llm_mode: bool,
    candidate_count: int,
    ddtree_max_candidates: int,
    route_cost_controls: Mapping[str, Any] | None = None,
) -> CandidatePoolPolicy:
    controls = route_cost_controls or {}
    if not llm_mode:
        return CandidatePoolPolicy(0, 1.0, ())
    if controls.get("autoreason_mixed_candidate_pool") is True and autoreason_enabled:
        return CandidatePoolPolicy(
            local_support_candidates=1,
            local_support_score_cap=0.999,
            reason_codes=("autoreason_mixed_candidate_pool", "one_llm_plus_local_support"),
        )
    if not ddtree_enabled or controls.get("ddtree_mixed_candidate_pool") is not True:
        return CandidatePoolPolicy(0, 1.0, ())
    max_candidates = max(1, int(ddtree_max_candidates or 2))
    requested = max(1, int(candidate_count or 1))
    if requested <= max_candidates:
        return CandidatePoolPolicy(0, 1.0, ("ddtree_pool_within_budget",))
    support_needed = max(0, (max_candidates + 1) - 1)
    if support_needed <= 0:
        return CandidatePoolPolicy(0, 1.0, ())
    return CandidatePoolPolicy(
        local_support_candidates=support_needed,
        local_support_score_cap=0.999,
        reason_codes=("ddtree_mixed_candidate_pool", "one_llm_plus_local_support"),
    )
