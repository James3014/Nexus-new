from __future__ import annotations
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
    def __init__(self, project_root: Path, learn_mode_service: Any):
        self.learn_mode_service = learn_mode_service
        self.learn_mode_service.project_root = project_root
        self.learn_mode_service = learn_mode_service
        
    def _answer_questions(self, questions: list[dict[str, Any]], claims: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        answered, unresolved = [], []
        for q in questions:
            token = q["token"]
            matched = []
            for c in claims:
                if not self.learn_mode_service._is_valid_citation(c):
                    continue
                blob = f"{c.get('claim','')} {' '.join(c.get('topic_tags',[]))}".lower()
                if token in blob:
                    matched.append(
                        {
                            "source_url": c.get("source_url"),
                            "citation_span": c.get("citation_span"),
                            "claim": c.get("claim", ""),
                        }
                    )
                if len(matched) >= 2:
                    break
            if matched:
                answered.append({"token": token, "question": q["question"], "evidence": matched})
            else:
                unresolved.append({"token": token, "question": q["question"]})
        return answered, unresolved

    def _build_question_set(self, topic: str, question_count: int = 5) -> list[dict[str, Any]]:
        tokens = sorted(self.learn_mode_service._extract_tokens(topic))
        qs = []
        for token in tokens[: max(3, question_count)]:
            qs.append(
                {
                    "token": token,
                    "question": f"What cited evidence explains '{token}' in topic context?",
                }
            )
        return qs

    def _discover_sources(self, topic: str, max_sources: int = 3) -> list[str]:
        tokens = sorted(self.learn_mode_service._extract_tokens(topic))
        out: list[str] = []
        claims = self.learn_mode_service.load_claims()
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
            pack_scores[pack] = pack_scores.get(pack, 0.0) + self.learn_mode_service._claim_pack_score(claim, topic, question)
        selected_pack = max(pack_scores.items(), key=lambda item: item[1])[0] if pack_scores else "general"
        routed = [c for c in claims if str(c.get("topic_pack", "general")) == selected_pack]
        return selected_pack, (routed or claims)
