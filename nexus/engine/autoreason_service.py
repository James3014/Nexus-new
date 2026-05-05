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


@dataclass(frozen=True)
class AutoreasonConfig:
    judge_count: int = 3
    a_streak_threshold: int = 2

    @classmethod
    def from_values(cls, judge_count: int, a_streak_threshold: int) -> "AutoreasonConfig":
        safe_judge = max(3, min(7, int(judge_count or 3)))
        safe_streak = max(1, int(a_streak_threshold or 2))
        return cls(judge_count=safe_judge, a_streak_threshold=safe_streak)


class AutoreasonService:
    """Deterministic autoreason engine with candidate factory + blind Borda panel."""

    def __init__(self, *, judge_count: int = 3) -> None:
        self.config = AutoreasonConfig.from_values(judge_count=judge_count, a_streak_threshold=2)

    def candidate_factory(
        self,
        *,
        incumbent: dict[str, Any] | None = None,
        revision: dict[str, Any] | None = None,
        synthesis: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if isinstance(incumbent, dict):
            out.append({"candidate_id": "A", **incumbent})
        if isinstance(revision, dict):
            out.append({"candidate_id": "B", **revision})
        if isinstance(synthesis, dict):
            out.append({"candidate_id": "AB", **synthesis})
        return out

    def run(
        self,
        candidates: list[dict[str, Any]] | None = None,
        *,
        incumbent: dict[str, Any] | None = None,
        revision: dict[str, Any] | None = None,
        synthesis: dict[str, Any] | None = None,
        task_desc: str = "",
        stop_threshold: int = 2,
        judge_count: int | None = None,
    ) -> dict[str, Any]:
        source_candidates = list(candidates or [])
        if not source_candidates:
            source_candidates = self.candidate_factory(
                incumbent=incumbent,
                revision=revision,
                synthesis=synthesis,
            )
        parsed = [AutoreasonCandidate.from_mapping(item, index) for index, item in enumerate(source_candidates)]
        if not parsed:
            return {
                "schema": "nexus_autoreason_result_v1",
                "enabled": False,
                "status": "NO_CANDIDATES",
                "task_desc": task_desc,
                "winner": None,
                "judge_votes": [],
                "borda_scores": {},
                "stop_reason": "no_candidates",
            }

        cfg = AutoreasonConfig.from_values(
            judge_count=self.config.judge_count if judge_count is None else judge_count,
            a_streak_threshold=stop_threshold,
        )
        judge_votes = [self._vote(judge, parsed) for judge in self._build_judge_panel(cfg.judge_count)]
        borda_scores = {candidate.candidate_id: 0 for candidate in parsed}
        for vote in judge_votes:
            for rank, candidate_id in enumerate(vote["ranking"]):
                borda_scores[candidate_id] += len(parsed) - rank
        winner = max(parsed, key=lambda item: (borda_scores[item.candidate_id], item.score, item.candidate_id))
        winning_votes = sum(1 for vote in judge_votes if vote["ranking"] and vote["ranking"][0] == winner.candidate_id)
        stop_reason = "a_streak_met" if winning_votes >= cfg.a_streak_threshold else "budget_submit"
        return {
            "schema": "nexus_autoreason_result_v1",
            "enabled": True,
            "status": "SUCCESS",
            "task_desc": task_desc,
            "winner": winner.candidate_id,
            "judge_votes": judge_votes,
            "judge_count": cfg.judge_count,
            "borda_scores": borda_scores,
            "stop_reason": stop_reason,
        }

    def _build_judge_panel(self, judge_count: int) -> list[str]:
        strategies = [
            "evidence",
            "specificity",
            "base_score",
            "balanced",
            "risk",
            "coverage",
            "stability",
        ]
        return strategies[: max(3, min(7, judge_count))]

    def _vote(self, judge: str, candidates: list[AutoreasonCandidate]) -> dict[str, Any]:
        if judge == "evidence":
            ranked = sorted(candidates, key=lambda item: (len(item.evidence_refs), item.score, item.candidate_id), reverse=True)
        elif judge == "specificity":
            ranked = sorted(candidates, key=lambda item: (len(item.summary), len(item.evidence_refs), item.candidate_id), reverse=True)
        elif judge == "balanced":
            ranked = sorted(candidates, key=lambda item: (len(item.evidence_refs) + len(item.summary) * 0.01 + item.score, item.candidate_id), reverse=True)
        elif judge == "risk":
            ranked = sorted(candidates, key=lambda item: (len(item.evidence_refs), len(item.summary), item.candidate_id), reverse=True)
        elif judge == "coverage":
            ranked = sorted(candidates, key=lambda item: (len(item.summary), item.score, item.candidate_id), reverse=True)
        elif judge == "stability":
            ranked = sorted(candidates, key=lambda item: (item.score, item.candidate_id), reverse=True)
        else:
            ranked = sorted(candidates, key=lambda item: (item.score, len(item.evidence_refs), item.candidate_id), reverse=True)
        return {
            "judge": judge,
            "ranking": [item.candidate_id for item in ranked],
            "reason": f"ranked_by_{judge}_blind",
        }
