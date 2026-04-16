from __future__ import annotations
from .protocols import LearnContextProtocol
from .citation_relevance import score_citation_relevance
from .learn_models import LearnClaim
import json
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import quote_plus
import html
import time
import concurrent.futures
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
from nexus.services.mem_palace import MemPalace
from nexus.core.skill_outcomes import OutcomePayload, build_outcome_event, append_skill_outcome_event
from nexus.services.memory import MemoryService

class AskService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx
    def _answer_questions(self, questions: list[dict[str, Any]], claims: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        answered, unresolved = [], []
        for q in questions:
            token = q["token"]
            matched = []
            for c in claims:
                if not self.ctx._is_valid_citation(c):
                    continue
                blob = f"{c.get('claim','')} {' '.join(c.get('topic_tags',[]))}".lower()
                if token in blob:
                    matched.append(
                        {
                            "source_url": c.get("source_url"),
                            "citation_span": c.get("citation_span"),
                            "claim": c.get("claim", "")}
                    )
                if len(matched) >= 2:
                    break
            if matched:
                answered.append({"token": token, "question": q["question"], "evidence": matched})
            else:
                unresolved.append({"token": token, "question": q["question"]})
        return answered, unresolved

    def _build_question_set(self, topic: str, question_count: int = 5) -> list[dict[str, Any]]:
        tokens = sorted(self.ctx._extract_tokens(topic))
        qs = []
        for token in tokens[: max(3, question_count)]:
            qs.append(
                {
                    "token": token,
                    "question": f"What cited evidence explains '{token}' in topic context?"}
            )
        return qs

    def _discover_sources(self, topic: str, max_sources: int = 3) -> list[str]:
        tokens = sorted(self.ctx._extract_tokens(topic))
        out: list[str] = []
        claims = self.ctx.load_claims()
        for c in claims:
            src = str(c.get("source_url", ""))
            if src.startswith("https://raw.githubusercontent.com/"):
                m = re.search(r"githubusercontent\.com/([^/]+/[^/]+)/", src)
                if m:
                    out.append(f"repo:{m.group(1)}")
        q = quote_plus(" ".join(tokens[:4]))
        out.append(f"https://duckduckgo.com/html/?q={q}")
        # stable unique
        uniq = []
        for s in out:
            if s not in uniq:
                uniq.append(s)
        return uniq[:max_sources]

    def _is_valid_citation(self, c: dict[str, Any]) -> bool:
        src = str(c.get("source_url") or "")
        span = c.get("citation_span")
        if not src or not isinstance(span, list) or len(span) != 2:
            return False
        try:
            start, end = int(span[0]), int(span[1])
            return end > start >= 0
        except Exception:
            return False

    def _route_topic_pack(self, claims: list[dict[str, Any]], topic: str, question: str) -> tuple[str, list[dict[str, Any]]]:
        if not claims:
            return "general", []
        pack_scores: dict[str, float] = {}
        for claim in claims:
            pack = str(claim.get("topic_pack", "general"))
            pack_scores[pack] = pack_scores.get(pack, 0.0) + self.ctx._claim_pack_score(claim, topic, question)
        selected_pack = max(pack_scores.items(), key=lambda item: item[1])[0] if pack_scores else "general"
        routed = [c for c in claims if str(c.get("topic_pack", "general")) == selected_pack]
        return selected_pack, (routed or claims)

    def ask(
        self,
        topic: str,
        question: str,
        top_k: int = 5,
        min_evidence: int = 1,
        min_token_coverage: float | None = None,
        max_staleness_days: int | None = 180,
    ) -> dict[str, Any]:
        claims = self.load_claims()
        tokens = self._extract_tokens(question)
        if not tokens:
            closure = self._persist_learning_closure(
                action="ask",
                status="PARTIAL",
                reason="empty_question",
                topic_or_source=topic,
                evidence_paths=[str(self.ctx.claims_path)],
                retrieval_hints=[],
                metrics={"claims_count": 0, "coverage": 0.0, "pass_rate": 0.0, "citation_valid_ratio": 0.0},
            )
            return {
                "status": "UNKNOWN",
                "answer": "UNKNOWN",
                "citations": [],
                "topic": topic,
                "question": question,
                "reason": "empty_question",
                "learning_closure": closure,
                "relevance_scores": relevance_scores, "filtered_out_count": filtered_out_count}

        selected_pack, routed_claims = self._route_topic_pack(claims, topic, question)
        filtered_claims = [
            c for c in routed_claims if max_staleness_days is None or float(c.get("freshness_days", 0.0)) <= float(max_staleness_days)
        ]
        scored: list[tuple[float, dict[str, Any], set[str]]] = []
        for c in filtered_claims:
            if not self._is_valid_citation(c):
                continue
            blob = f"{c.get('claim', '')} {' '.join(c.get('topic_tags', []))}".lower()
            words = {self._normalize_token(w) for w in re.findall(r"[a-z0-9_-]+", blob)}
            score = 0.0
            token_hits: set[str] = set()
            for t in tokens:
                if t in words:
                    score += 2.0
                    token_hits.add(t)
                elif any(w.startswith(t) or t.startswith(w) for w in words if len(w) >= 4):
                    score += 1.0
                    token_hits.add(t)
            if score > 0:
                score = (
                    score
                    + self._claim_strength_weight(c)
                    + float(c.get("freshness_score", 0.0))
                )
                scored.append((score, c, token_hits))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Greedy coverage-first selector: prioritize claims that add new token coverage,
        # then break ties by base score.
        
        # R2: Relevance Reranking and Filtering
        relevant_pairs = []
        filtered_out_count = 0
        relevance_scores = []
        
        for score, c, hits in scored:
            rel_score = score_citation_relevance(question, c.get("claim", ""), c)
            relevance_scores.append(rel_score)
            if rel_score >= 0.35:
                # Combine original coverage score with relevance
                combined_score = score * 0.4 + rel_score * 5.0
                relevant_pairs.append((combined_score, c, hits))
            else:
                filtered_out_count += 1
        
        scored = relevant_pairs
        scored.sort(key=lambda x: x[0], reverse=True)

        best_pairs: list[tuple[dict[str, Any], set[str]]] = []
        covered_tokens: set[str] = set()
        pool = [(score, c, hits) for score, c, hits in scored if self._is_valid_citation(c)]
        while pool and len(best_pairs) < top_k:
            best_idx = 0
            best_gain = -1
            best_score = -1
            for i, (score, _, hits) in enumerate(pool):
                gain = len(hits - covered_tokens)
                if gain > best_gain or (gain == best_gain and score > best_score):
                    best_idx = i
                    best_gain = gain
                    best_score = score
            score, c, hits = pool.pop(best_idx)
            if not best_pairs and best_gain <= 0 and score <= 0:
                break
            best_pairs.append((c, hits))
            covered_tokens.update(hits)

        best = [c for c, _ in best_pairs]
        token_coverage = 0.0 if not tokens else len(covered_tokens) / len(tokens)
        if min_token_coverage is None:
            if len(tokens) >= 5:
                min_token_coverage = 0.6
            elif len(tokens) >= 3:
                min_token_coverage = 0.5
            else:
                min_token_coverage = 0.5

        conflicts = self._find_conflicts(best)
        if conflicts:
            self._append_benchmark_candidate(
                topic=topic,
                question=question,
                actual_status="CONFLICT",
                reason="conflicting_cited_claims",
                token_coverage=token_coverage,
                topic_pack_selected=selected_pack,
                conflicts=conflicts,
            )
            closure = self._persist_learning_closure(
                action="ask",
                status="PARTIAL",
                reason="conflicting_cited_claims",
                topic_or_source=topic,
                evidence_paths=[str(self.ctx.claims_path)],
                retrieval_hints=sorted(tokens),
                metrics={
                    "claims_count": len(best),
                    "coverage": min(1.0, len(best) / max(1, top_k)),
                    "pass_rate": 0.0,
                    "citation_valid_ratio": 1.0 if best else 0.0,
                    "token_coverage": round(token_coverage, 4),
                    "conflict_count": len(conflicts)},
            )
            return {
                "status": "CONFLICT",
                "answer": "CONFLICT",
                "citations": [],
                "topic": topic,
                "question": question,
                "reason": "conflicting_cited_claims",
                "token_coverage": round(token_coverage, 4),
                "topic_pack_selected": selected_pack,
                "conflicts": conflicts,
                "learning_closure": closure}

        if len(best) < max(1, min_evidence) or token_coverage < float(min_token_coverage):
            unknown_reason = "insufficient_cited_claims" if len(best) < max(1, min_evidence) else "insufficient_token_coverage"
            self._append_benchmark_candidate(
                topic=topic,
                question=question,
                actual_status="UNKNOWN",
                reason=unknown_reason,
                token_coverage=token_coverage,
                topic_pack_selected=selected_pack,
            )
            closure = self._persist_learning_closure(
                action="ask",
                status="PARTIAL",
                reason=unknown_reason,
                topic_or_source=topic,
                evidence_paths=[str(self.ctx.claims_path)],
                retrieval_hints=sorted(tokens),
                metrics={
                    "claims_count": len(best),
                    "coverage": min(1.0, len(best) / max(1, top_k)),
                    "pass_rate": 0.0,
                    "citation_valid_ratio": 1.0 if best else 0.0,
                    "token_coverage": round(token_coverage, 4),
                    "topic_pack_selected": selected_pack},
            )
            return {
                "status": "UNKNOWN",
                "answer": "UNKNOWN",
                "citations": [],
                "topic": topic,
                "question": question,
                "reason": unknown_reason,
                "token_coverage": round(token_coverage, 4),
                "topic_pack_selected": selected_pack,
                "learning_closure": closure}

        lines = []
        citations = []
        for c in best:
            span = c.get("citation_span", [0, 0])
            source_url = c.get("source_url", "unknown://source")
            citation = f"{source_url}#span={span[0]}-{span[1]}"
            lines.append(f"- {c.get('claim', '')} [{citation}]")
            citations.append(
                {
                    "source_url": source_url,
                    "citation_span": span,
                    "claim": c.get("claim", "")}
            )
        return {
            "status": "ANSWERED",
            "topic": topic,
            "question": question,
            "answer": "\n".join(lines),
            "citations": citations,
            "claims_used": len(best),
            "min_evidence_required": max(1, min_evidence),
            "token_coverage": round(token_coverage, 4),
            "topic_pack_selected": selected_pack,
            "learning_closure": self._persist_learning_closure(
                action="ask",
                status="SUCCESS",
                reason="answered_with_citations",
                topic_or_source=topic,
                evidence_paths=[str(self.ctx.claims_path)],
                retrieval_hints=sorted(tokens),
                metrics={
                    "claims_count": len(best),
                    "coverage": min(1.0, len(best) / max(1, top_k)),
                    "pass_rate": 1.0,
                    "citation_valid_ratio": 1.0,
                    "topic_pack_selected": selected_pack},
            ),
            "timestamp": datetime.now(timezone.utc).isoformat()}
