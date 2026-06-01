from __future__ import annotations
from .protocols import LearnContextProtocol
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

class ConvergeService:
    def __init__(self, ctx: LearnContextProtocol):
        self.ctx = ctx
    def _find_conflicts(self, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for i, left in enumerate(claims):
            ltoks = self.ctx._extract_tokens(str(left.get("claim", "")))
            if not ltoks:
                continue
            for right in claims[i + 1 :]:
                rtoks = self.ctx._extract_tokens(str(right.get("claim", "")))
                if not rtoks:
                    continue
                overlap = ltoks & rtoks
                union = ltoks | rtoks
                overlap_ratio = 0.0 if not union else len(overlap) / len(union)
                if overlap_ratio < 0.55:
                    continue
                if self.ctx._claim_polarity(str(left.get("claim", ""))) == self.ctx._claim_polarity(str(right.get("claim", ""))):
                    continue
                conflicts.append(
                    {
                        "left": {
                            "claim": left.get("claim", ""),
                            "source_url": left.get("source_url", ""),
                            "citation_span": left.get("citation_span", [])},
                        "right": {
                            "claim": right.get("claim", ""),
                            "source_url": right.get("source_url", ""),
                            "citation_span": right.get("citation_span", [])},
                        "conflict_score": round(overlap_ratio, 4)}
                )
        return conflicts
