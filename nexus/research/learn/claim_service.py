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

class ClaimService:
    def __init__(self, project_root: Path, learn_mode_service: Any):
        self.learn_mode_service = learn_mode_service
        self.learn_mode_service.project_root = project_root
        self.learn_mode_service = learn_mode_service
        
    def _append_claims(self, claims: list[LearnClaim]) -> None:
        existing = {self.learn_mode_service._claim_key(c) for c in self.learn_mode_service.load_claims()}
        with self.learn_mode_service.claims_path.open("a", encoding="utf-8") as f:
            for c in claims:
                key = self.learn_mode_service._claim_key(c)
                if key in existing:
                    continue
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
                existing.add(key)

    def _enrich_claim(self, claim: dict[str, Any]) -> dict[str, Any]:
        out = dict(claim)
        created_at = str(out.get("created_at") or datetime.now(timezone.utc).isoformat())
        freshness_days, freshness_score = self.learn_mode_service._freshness_score_for(created_at)
        out["created_at"] = created_at
        out["topic_pack"] = out.get("topic_pack") or self.learn_mode_service._infer_topic_pack(
            str(out.get("source_url", "")),
            str(out.get("claim", "")),
        )
        out["evidence_strength"] = out.get("evidence_strength") or self.learn_mode_service._estimate_evidence_strength(
            str(out.get("source_url", "")),
            str(out.get("claim", "")),
        )
        out["freshness_days"] = float(out.get("freshness_days", freshness_days) or freshness_days)
        out["freshness_score"] = float(out.get("freshness_score", freshness_score) or freshness_score)
        return out
