from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .protocols import LearnContextProtocol


class ReportService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx

    def build_report(
        self,
        topic: str = "",
        question_count: int = 5,
        pass_threshold: float = 0.6,
    ) -> dict[str, Any]:
        claims = self.ctx.load_claims()
        sources = {c.get("source_url", "") for c in claims if c.get("source_url")}
        valid_claims = [c for c in claims if self.ctx._is_valid_citation(c)]
        unresolved_questions: list[str] = []
        answered_questions: list[dict[str, Any]] = []
        question_set: list[dict[str, Any]] = []
        coverage = 0.0 if not claims else len(valid_claims) / len(claims)
        pass_rate = 1.0 if claims else 0.0
        topic_pack_counts: dict[str, int] = {}
        high_strength_claims = 0
        stale_claims_count = 0
        for claim in valid_claims:
            pack = str(claim.get("topic_pack", "general"))
            topic_pack_counts[pack] = topic_pack_counts.get(pack, 0) + 1
            if str(claim.get("evidence_strength", "")).lower() == "high":
                high_strength_claims += 1
            if float(claim.get("freshness_days", 0.0)) > 90:
                stale_claims_count += 1
        conflict_candidates = self.ctx._find_conflicts(valid_claims[:50])
        if topic:
            question_set = self.ctx._build_question_set(topic, question_count=question_count)
            answered_questions, unresolved_questions = self.ctx._answer_questions(question_set, valid_claims)
            pass_rate = (
                0.0 if not question_set else len(answered_questions) / len(question_set)
            )
            if pass_rate < pass_threshold and not unresolved_questions:
                unresolved_questions = [
                    f"Need more cited claims to reach pass threshold {pass_threshold}"
                ]

        report = {
            "status": "SUCCESS",
            "topic": topic,
            "sources_count": len(sources),
            "claims_count": len(claims),
            "claims_with_valid_citation": len(valid_claims),
            "citation_valid_ratio": round(0.0 if not claims else len(valid_claims) / len(claims), 4),
            "high_strength_claims": high_strength_claims,
            "stale_claims_count": stale_claims_count,
            "conflict_candidate_count": len(conflict_candidates),
            "topic_packs": topic_pack_counts,
            "top_sources": sorted(sources)[:5],
            "coverage": round(coverage, 4),
            "self_question_pass_rate": round(pass_rate, 4),
            "question_set": question_set,
            "answered_questions": answered_questions,
            "unresolved_questions": unresolved_questions,
            "converged": pass_rate >= pass_threshold,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        report["phase_slo_summary"] = self.ctx.build_phase_slo_report(window=300)
        return report
