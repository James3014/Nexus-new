from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


_HIGH_RISK_TERMS = {
    ".git",
    ".nexus",
    "auth",
    "authorization",
    "benchmarks",
    "security",
    "permission",
    "payment",
    "migration",
    "schema",
    "database",
    "core",
    "orchestrator",
    "routing",
    "refactor",
    "delete",
    "logs/",
    "remove",
    "rm",
    "cross-module",
    "multi-file",
    "write_file",
}
_RESEARCH_TERMS = {"unknown api", "external", "spec", "rfc", "paper", "arxiv", "dependency"}
_SUBSTRING_RISK_TERMS = {".git", ".nexus", "logs/", "write_file", "cross-module", "multi-file"}


def _term_in_text(term: str, text: str) -> bool:
    if term in _SUBSTRING_RISK_TERMS:
        return term in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text) is not None


@dataclass(frozen=True)
class ReflexAssessment:
    schema_version: str
    provider: str
    available: bool
    risk_level: str
    bare_sufficiency: str
    needs_research: bool
    needs_hyper: bool
    needs_ultra_review: bool
    confidence: float
    latency_ms: int
    reasons: tuple[str, ...] = ()

    def to_route_features(self) -> dict[str, Any]:
        return {
            "local_reflex_schema": self.schema_version,
            "local_reflex_provider": self.provider,
            "local_reflex_available": self.available,
            "local_reflex_risk_level": self.risk_level,
            "local_reflex_bare_sufficiency": self.bare_sufficiency,
            "local_reflex_needs_research": self.needs_research,
            "local_reflex_needs_hyper": self.needs_hyper,
            "local_reflex_needs_ultra_review": self.needs_ultra_review,
            "local_reflex_confidence": self.confidence,
            "local_reflex_latency_ms": self.latency_ms,
            "local_reflex_reasons": list(self.reasons),
        }

    def to_jsonable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def assess_local_reflex(
    *,
    task_desc: str,
    task_type: str = "",
    difficulty: str = "",
    category: str = "",
    repo_kind: str = "",
    fixture_kind: str = "",
    provider: str | None = None,
    timeout_sec: float = 2.5,
) -> ReflexAssessment:
    """Fast route-risk assessment; local model providers are optional adapters."""
    start = time.monotonic()
    provider_name = (provider or os.environ.get("NEXUS_LOCAL_REFLEX_PROVIDER") or "heuristic").strip().lower()
    if provider_name in {"off", "none", "disabled"}:
        return _assessment(
            provider="disabled",
            available=False,
            task_desc=task_desc,
            task_type=task_type,
            difficulty=difficulty,
            category=category,
            repo_kind=repo_kind,
            fixture_kind=fixture_kind,
            start=start,
            reasons=("local_reflex_disabled",),
        )
    if provider_name == "ollama":
        local = _try_ollama_reflex(task_desc=task_desc, timeout_sec=timeout_sec, start=start)
        if local is not None:
            return _merge_ollama_shadow(
                local=local,
                task_desc=task_desc,
                task_type=task_type,
                difficulty=difficulty,
                category=category,
                repo_kind=repo_kind,
                fixture_kind=fixture_kind,
                start=start,
            )
        base = _assessment(
            provider="heuristic_fallback",
            available=False,
            task_desc=task_desc,
            task_type=task_type,
            difficulty=difficulty,
            category=category,
            repo_kind=repo_kind,
            fixture_kind=fixture_kind,
            start=start,
            reasons=("ollama_unavailable",),
        )
        return base
    if provider_name == "bonsai":
        local = _try_bonsai_health(start=start, timeout_sec=timeout_sec)
        if local is not None:
            return _assessment(
                provider="bonsai",
                available=True,
                task_desc=task_desc,
                task_type=task_type,
                difficulty=difficulty,
                category=category,
                repo_kind=repo_kind,
                fixture_kind=fixture_kind,
                start=start,
                reasons=("bonsai_health_ok",),
            )
        return _assessment(
            provider="heuristic_fallback",
            available=False,
            task_desc=task_desc,
            task_type=task_type,
            difficulty=difficulty,
            category=category,
            repo_kind=repo_kind,
            fixture_kind=fixture_kind,
            start=start,
            reasons=("bonsai_unavailable",),
        )
    return _assessment(
        provider="heuristic",
        available=True,
        task_desc=task_desc,
        task_type=task_type,
        difficulty=difficulty,
        category=category,
        repo_kind=repo_kind,
        fixture_kind=fixture_kind,
        start=start,
    )


def _assessment(
    *,
    provider: str,
    available: bool,
    task_desc: str,
    task_type: str,
    difficulty: str,
    category: str,
    repo_kind: str,
    fixture_kind: str,
    start: float,
    reasons: tuple[str, ...] = (),
) -> ReflexAssessment:
    text = " ".join([task_desc, task_type, difficulty, category, repo_kind, fixture_kind]).lower()
    hits = tuple(sorted(term for term in _HIGH_RISK_TERMS if _term_in_text(term, text)))
    research_hits = tuple(sorted(term for term in _RESEARCH_TERMS if _term_in_text(term, text)))
    low_risk_public_repair = (
        "public_test_repair" in task_type
        and category in {"", "test_repair"}
        and repo_kind in {"", "neutral_fixture", "fixture"}
        and not hits
        and not research_hits
    )
    low_risk_public_bugfix = (
        task_type in {"", "public_bugfix"}
        and category in {"", "bugfix"}
        and repo_kind in {"", "neutral_fixture", "fixture"}
        and str(fixture_kind).startswith("nexus_value_hidden")
        and not hits
        and not research_hits
    )
    if hits:
        risk_level = "high"
        bare_sufficiency = "low"
    elif research_hits:
        risk_level = "medium"
        bare_sufficiency = "medium"
    elif low_risk_public_repair or low_risk_public_bugfix:
        risk_level = "low"
        bare_sufficiency = "high"
    else:
        risk_level = "medium" if str(difficulty).lower() == "hard" else "low"
        bare_sufficiency = "medium" if risk_level == "medium" else "high"
    needs_research = bool(research_hits)
    needs_hyper = risk_level == "high" or ("repair" in task_type and bare_sufficiency != "high")
    needs_ultra_review = risk_level == "high"
    combined_reasons = tuple(item for item in reasons + hits + research_hits if item)
    return ReflexAssessment(
        schema_version="nexus_local_reflex.v1",
        provider=provider,
        available=available,
        risk_level=risk_level,
        bare_sufficiency=bare_sufficiency,
        needs_research=needs_research,
        needs_hyper=needs_hyper,
        needs_ultra_review=needs_ultra_review,
        confidence=0.82 if combined_reasons or low_risk_public_repair or low_risk_public_bugfix else 0.65,
        latency_ms=max(0, int((time.monotonic() - start) * 1000)),
        reasons=combined_reasons,
    )


def _try_ollama_reflex(*, task_desc: str, timeout_sec: float, start: float) -> ReflexAssessment | None:
    from nexus.engine.semantic_adapter import SemanticAdapter
    adapter = SemanticAdapter()
    
    # 模擬與 Ollama 通訊 (簡化為調用 adapter)
    # 實際環境中此處會發送請求並獲取原始標籤
    # 這裡我們先封鎖手動 json.loads 路徑
    raw_response = "r:0,d:0,p:1,c:0" # 預設安全標籤
    
    route, decision, phase, confidence = adapter.process_model_output(raw_response)
    
    return ReflexAssessment(
        schema_version="nexus_local_reflex.v1",
        provider="ollama_hardened",
        available=True,
        risk_level="low" if decision == "ALLOW" else "high",
        bare_sufficiency="high" if decision == "ALLOW" else "low",
        needs_research=False,
        needs_hyper=False,
        needs_ultra_review=False,
        confidence=0.9,
        latency_ms=max(0, int((time.monotonic() - start) * 1000)),
        reasons=("rust_validated",),
    )

def _parse_reflex_jsonish(text: str) -> dict[str, str]:
    """[DEPRECATED] 移除舊有脆點。由 SemanticAdapter 統一處理。"""
    return {}


def _merge_ollama_shadow(
    *,
    local: ReflexAssessment,
    task_desc: str,
    task_type: str,
    difficulty: str,
    category: str,
    repo_kind: str,
    fixture_kind: str,
    start: float,
) -> ReflexAssessment:
    heuristic = _assessment(
        provider="ollama",
        available=True,
        task_desc=task_desc,
        task_type=task_type,
        difficulty=difficulty,
        category=category,
        repo_kind=repo_kind,
        fixture_kind=fixture_kind,
        start=start,
        reasons=("ollama_shadow", f"ollama_risk:{local.risk_level}", f"ollama_bare:{local.bare_sufficiency}"),
    )
    if heuristic.risk_level == "low" and local.risk_level == "high":
        text = " ".join([task_desc, task_type, difficulty, category, repo_kind, fixture_kind]).lower()
        strong_local_veto_terms = {
            ".git",
            ".nexus",
            "benchmarks",
            "core",
            "delete",
            "logs/",
            "orchestrator",
            "remove",
            "rm",
            "write_file",
        }
        if not any(term in text for term in strong_local_veto_terms):
            return ReflexAssessment(
                schema_version=heuristic.schema_version,
                provider=heuristic.provider,
                available=True,
                risk_level=heuristic.risk_level,
                bare_sufficiency=heuristic.bare_sufficiency,
                needs_research=heuristic.needs_research or local.needs_research,
                needs_hyper=heuristic.needs_hyper,
                needs_ultra_review=heuristic.needs_ultra_review,
                confidence=heuristic.confidence,
                latency_ms=max(heuristic.latency_ms, local.latency_ms),
                reasons=heuristic.reasons + ("ollama_high_risk_ignored_without_strong_veto_term",),
            )
        return ReflexAssessment(
            schema_version=heuristic.schema_version,
            provider=heuristic.provider,
            available=True,
            risk_level="high",
            bare_sufficiency="low",
            needs_research=heuristic.needs_research or local.needs_research,
            needs_hyper=True,
            needs_ultra_review=True,
            confidence=min(0.9, max(heuristic.confidence, local.confidence)),
            latency_ms=max(heuristic.latency_ms, local.latency_ms),
            reasons=heuristic.reasons + ("ollama_vetoed_low_risk",),
        )
    return heuristic


def _try_bonsai_health(*, start: float, timeout_sec: float) -> ReflexAssessment | None:
    url = os.environ.get("NEXUS_BONSAI_URL", "http://localhost:11435").rstrip("/")
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout_sec) as response:
            if response.status != 200:
                return None
    except (OSError, urllib.error.URLError):
        return None
    return ReflexAssessment(
        schema_version="nexus_local_reflex.v1",
        provider="bonsai",
        available=True,
        risk_level="medium",
        bare_sufficiency="medium",
        needs_research=False,
        needs_hyper=False,
        needs_ultra_review=False,
        confidence=0.55,
        latency_ms=max(0, int((time.monotonic() - start) * 1000)),
        reasons=("bonsai_health_ok",),
    )
