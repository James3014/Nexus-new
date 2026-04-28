from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AutoreasonCandidate:
    candidate_id: str
    summary: str
    evidence_refs: list[str]
    score: float = 0.0

    @classmethod
    def from_mapping(cls, payload: dict[str, Any], index: int) -> "AutoreasonCandidate":
        return cls(
            candidate_id=str(payload.get("candidate_id") or payload.get("id") or f"candidate-{index + 1}"),
            summary=str(payload.get("summary") or payload.get("hint") or payload.get("body") or ""),
            evidence_refs=[str(item) for item in payload.get("evidence_refs", []) or []],
            score=float(payload.get("score", 0.0) or 0.0),
        )


class AutoreasonService:
    """Deterministic candidate judge used before model-backed autoreason is enabled."""

    def run(
        self,
        candidates: list[dict[str, Any]],
        *,
        task_desc: str = "",
        stop_threshold: int = 2,
    ) -> dict[str, Any]:
        parsed = [AutoreasonCandidate.from_mapping(item, index) for index, item in enumerate(candidates)]
        if not parsed:
            return {
                "schema": "nexus_autoreason_result_v1",
                "status": "NO_CANDIDATES",
                "task_desc": task_desc,
                "winner": None,
                "judge_votes": [],
                "borda_scores": {},
                "stop_reason": "no_candidates",
            }

        judge_votes = [
            self._vote("evidence", parsed),
            self._vote("specificity", parsed),
            self._vote("base_score", parsed),
        ]
        borda_scores = {candidate.candidate_id: 0 for candidate in parsed}
        for vote in judge_votes:
            for rank, candidate_id in enumerate(vote["ranking"]):
                borda_scores[candidate_id] += len(parsed) - rank
        winner = max(parsed, key=lambda item: (borda_scores[item.candidate_id], item.score, item.candidate_id))
        winning_votes = sum(1 for vote in judge_votes if vote["ranking"] and vote["ranking"][0] == winner.candidate_id)
        stop_reason = "a_streak_met" if winning_votes >= max(1, stop_threshold) else "budget_submit"
        return {
            "schema": "nexus_autoreason_result_v1",
            "status": "SUCCESS",
            "task_desc": task_desc,
            "winner": winner.candidate_id,
            "judge_votes": judge_votes,
            "borda_scores": borda_scores,
            "stop_reason": stop_reason,
        }

    def _vote(self, judge: str, candidates: list[AutoreasonCandidate]) -> dict[str, Any]:
        if judge == "evidence":
            ranked = sorted(candidates, key=lambda item: (len(item.evidence_refs), item.score, item.candidate_id), reverse=True)
        elif judge == "specificity":
            ranked = sorted(candidates, key=lambda item: (len(item.summary), len(item.evidence_refs), item.candidate_id), reverse=True)
        else:
            ranked = sorted(candidates, key=lambda item: (item.score, len(item.evidence_refs), item.candidate_id), reverse=True)
        return {
            "judge": judge,
            "ranking": [item.candidate_id for item in ranked],
            "reason": f"ranked_by_{judge}",
        }
