from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


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


class JudgeProvider(Protocol):
    name: str

    def rank(self, *, task_desc: str, candidates: list[AutoreasonCandidate]) -> dict[str, Any]:
        ...


class AutoreasonService:
    """Deterministic autoreason engine with candidate factory + blind Borda panel."""

    def __init__(self, *, judge_count: int = 3, judge_providers: list[JudgeProvider] | None = None) -> None:
        self.config = AutoreasonConfig.from_values(judge_count=judge_count, a_streak_threshold=2)
        self.judge_providers = list(judge_providers or [])

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

    def candidate_factory_from_summaries(
        self,
        summaries: list[dict[str, Any]] | None,
        *,
        task_desc: str = "",
    ) -> dict[str, Any]:
        """Build an auditable A/B/AB tournament from sprint candidate summaries."""
        candidates = [
            item
            for item in (summaries or [])
            if isinstance(item, dict) and str(item.get("hint") or item.get("source") or "").strip()
        ]
        if len(candidates) < 2:
            return {
                "schema": "nexus_autoreason_candidate_factory_v1",
                "status": "SKIPPED",
                "reason": "insufficient_candidate_summaries",
                "task_desc": task_desc,
                "candidates": [],
                "candidate_roles": {},
            }

        def _candidate_payload(item: dict[str, Any], role: str, index: int) -> dict[str, Any]:
            refs = [str(item.get("stdout_excerpt") or "").strip()]
            refs = [ref for ref in refs if ref]
            return {
                "candidate_id": role,
                "source_candidate_id": str(item.get("candidate_id") or f"candidate-{index + 1}"),
                "summary": str(item.get("hint") or item.get("source") or ""),
                "evidence_refs": refs,
                "score": float(item.get("score", 0.0) or 0.0),
                "role": role,
            }

        ranked = sorted(
            enumerate(candidates),
            key=lambda pair: (
                float(pair[1].get("score", 0.0) or 0.0),
                len(str(pair[1].get("stdout_excerpt") or "")),
                len(str(pair[1].get("hint") or pair[1].get("source") or "")),
            ),
            reverse=True,
        )
        best_index, best = ranked[0]
        challenger_index, challenger = ranked[1]
        incumbent = _candidate_payload(challenger, "A", challenger_index)
        revision = _candidate_payload(best, "B", best_index)
        synthesis = {
            "candidate_id": "AB",
            "source_candidate_id": f"{incumbent['source_candidate_id']}+{revision['source_candidate_id']}",
            "summary": (
                f"Synthesize incumbent stability from {incumbent['source_candidate_id']} "
                f"with revision evidence from {revision['source_candidate_id']}: {revision['summary']}"
            ),
            "evidence_refs": list(dict.fromkeys([*incumbent["evidence_refs"], *revision["evidence_refs"], "factory:ab_synthesis"])),
            "score": max(float(incumbent["score"]), float(revision["score"])) + 0.05,
            "role": "AB",
        }
        out = self.candidate_factory(incumbent=incumbent, revision=revision, synthesis=synthesis)
        return {
            "schema": "nexus_autoreason_candidate_factory_v1",
            "status": "READY",
            "task_desc": task_desc,
            "candidates": out,
            "candidate_roles": {item["candidate_id"]: item.get("role", item["candidate_id"]) for item in out},
            "regression_guard": {
                "strategy": "blind_borda_a_b_ab",
                "requires_winner": True,
                "preferred_winner": "AB",
            },
        }

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
                "candidate_factory": {
                    "schema": "nexus_autoreason_candidate_factory_v1",
                    "status": "SKIPPED",
                    "reason": "no_candidates",
                },
            }

        cfg = AutoreasonConfig.from_values(
            judge_count=self.config.judge_count if judge_count is None else judge_count,
            a_streak_threshold=stop_threshold,
        )
        judge_votes = self._semantic_votes(task_desc=task_desc, candidates=parsed, judge_count=cfg.judge_count)
        judge_mode = "semantic" if judge_votes else "deterministic_evidence_quality"
        if not judge_votes:
            judge_votes = self._evidence_quality_votes(task_desc=task_desc, candidates=parsed, judge_count=cfg.judge_count)
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
            "judge_mode": judge_mode,
            "semantic_judged": judge_mode == "semantic",
            "borda_scores": borda_scores,
            "stop_reason": stop_reason,
            "winner_role": winner.candidate_id if winner.candidate_id in {"A", "B", "AB"} else "legacy",
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

    def _evidence_quality_votes(
        self,
        *,
        task_desc: str,
        candidates: list[AutoreasonCandidate],
        judge_count: int,
    ) -> list[dict[str, Any]]:
        judges = [
            ("correctness", {"tests": 0.45, "semantic_fit": 0.25, "regression": 0.15, "minimality": 0.1, "score": 0.05}),
            ("regression", {"tests": 0.3, "semantic_fit": 0.15, "regression": 0.35, "minimality": 0.1, "score": 0.1}),
            ("semantic_fit", {"tests": 0.2, "semantic_fit": 0.45, "regression": 0.15, "minimality": 0.1, "score": 0.1}),
            ("minimality", {"tests": 0.2, "semantic_fit": 0.2, "regression": 0.15, "minimality": 0.35, "score": 0.1}),
            ("coverage", {"tests": 0.35, "semantic_fit": 0.2, "regression": 0.25, "minimality": 0.05, "score": 0.15}),
            ("risk", {"tests": 0.25, "semantic_fit": 0.15, "regression": 0.3, "minimality": 0.2, "score": 0.1}),
            ("stability", {"tests": 0.25, "semantic_fit": 0.2, "regression": 0.3, "minimality": 0.1, "score": 0.15}),
        ][: max(3, min(7, int(judge_count or 3)))]
        votes: list[dict[str, Any]] = []
        for judge, weights in judges:
            scored = [(candidate, self._quality_score(candidate, task_desc=task_desc, weights=weights)) for candidate in candidates]
            ranked = sorted(scored, key=lambda item: (item[1]["total"], item[0].score, item[0].candidate_id), reverse=True)
            votes.append(
                {
                    "judge": judge,
                    "ranking": [candidate.candidate_id for candidate, _score in ranked],
                    "reason": f"ranked_by_{judge}_evidence_quality",
                    "rubric": {candidate.candidate_id: score for candidate, score in ranked},
                }
            )
        return votes

    def _quality_score(self, candidate: AutoreasonCandidate, *, task_desc: str, weights: dict[str, float]) -> dict[str, Any]:
        text = f"{candidate.summary} {' '.join(candidate.evidence_refs)}".lower()
        task_tokens = {
            token
            for token in task_desc.lower().replace("_", " ").split()
            if len(token) >= 4 and token not in {"with", "when", "from", "this", "that", "only"}
        }
        semantic_hits = sum(1 for token in task_tokens if token in text)
        tests = self._signal_score(text, positive=("pytest", "test_", "passed", "regression", "::test", "assert"))
        regression = self._signal_score(text, positive=("regression", "edge", "boundary", "timeout", "race", "rollback", "source_id"))
        semantic_fit = min(1.0, semantic_hits / max(1, min(5, len(task_tokens))))
        generic_noise = self._signal_score(text, positive=("generic", "log", "maybe", "guess", "unclear"))
        minimality = max(0.0, 1.0 - min(1.0, max(0, len(candidate.summary) - 180) / 600.0) - generic_noise * 0.15)
        base_score = max(0.0, min(1.0, float(candidate.score or 0.0)))
        total = (
            tests * weights["tests"]
            + semantic_fit * weights["semantic_fit"]
            + regression * weights["regression"]
            + minimality * weights["minimality"]
            + base_score * weights["score"]
        )
        return {
            "total": round(total, 4),
            "tests": round(tests, 4),
            "semantic_fit": round(semantic_fit, 4),
            "regression": round(regression, 4),
            "minimality": round(minimality, 4),
            "base_score": round(base_score, 4),
        }

    def _signal_score(self, text: str, *, positive: tuple[str, ...]) -> float:
        hits = sum(1 for token in positive if token in text)
        return min(1.0, hits / max(1, min(3, len(positive))))

    def _semantic_votes(
        self,
        *,
        task_desc: str,
        candidates: list[AutoreasonCandidate],
        judge_count: int,
    ) -> list[dict[str, Any]]:
        if not self.judge_providers:
            return []
        votes: list[dict[str, Any]] = []
        safe_count = max(1, min(7, int(judge_count or 3)))
        valid_ids = {item.candidate_id for item in candidates}
        for index in range(safe_count):
            provider = self.judge_providers[index % len(self.judge_providers)]
            try:
                vote = provider.rank(task_desc=task_desc, candidates=list(candidates))
            except Exception:
                return []
            ranking = [str(item) for item in vote.get("ranking", []) if str(item) in valid_ids]
            for candidate in candidates:
                if candidate.candidate_id not in ranking:
                    ranking.append(candidate.candidate_id)
            votes.append(
                {
                    "judge": str(vote.get("judge") or getattr(provider, "name", f"semantic-{index + 1}")),
                    "ranking": ranking,
                    "reason": str(vote.get("reason") or "semantic_blind_rank"),
                    "rubric": vote.get("rubric") if isinstance(vote.get("rubric"), dict) else {},
                }
            )
        return votes

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
