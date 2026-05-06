from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from nexus.contracts.s2t_policy import NO_VERIFIED_CANDIDATE, S2TCandidate


VerifyCandidate = Callable[[S2TCandidate], bool]


@dataclass(frozen=True)
class S2TRepairSelection:
    selected_candidate_id: str
    verified: bool
    attempted_candidate_ids: tuple[str, ...]
    failure_reason: str = ""


class S2TRepairCandidateLoop:
    """Try ranked repair candidates until one verifies or the budget is exhausted."""

    def __init__(self, *, max_attempts: int = 3) -> None:
        self.max_attempts = max(1, int(max_attempts or 1))

    def run(self, candidates: list[S2TCandidate], verify: VerifyCandidate) -> S2TRepairSelection:
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                candidate.selector_score,
                bool(candidate.evidence_refs),
                -len(candidate.risk_flags),
                candidate.static_score,
            ),
            reverse=True,
        )
        attempted: list[str] = []
        for candidate in ranked[: self.max_attempts]:
            attempted.append(candidate.candidate_id)
            if candidate.verifier_result == "fail":
                continue
            if verify(candidate):
                return S2TRepairSelection(
                    selected_candidate_id=candidate.candidate_id,
                    verified=True,
                    attempted_candidate_ids=tuple(attempted),
                )
        return S2TRepairSelection(
            selected_candidate_id=NO_VERIFIED_CANDIDATE,
            verified=False,
            attempted_candidate_ids=tuple(attempted),
            failure_reason="budget_exhausted_or_no_verified_candidate",
        )
