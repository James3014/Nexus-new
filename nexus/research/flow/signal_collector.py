from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TypedDict

from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.research.findings_memory import FindingsMemoryStore
from nexus.research.flow.history_signal_store import HistorySignalStore


class RouteSignals(TypedDict):
    findings_hits: int
    memory_hits: int
    historical_hints: list[str]
    adjusted_root_cause_confidence: float
    decision: Any
    is_doc_fix: bool
    is_cross_module_task: bool
    has_commercial_signal: bool
    has_strong_commercial_signal: bool
    has_hard_signal: bool


def task_body_only(task_desc: str) -> str:
    return (task_desc or "").split("\n\nNexus wearing contract:", 1)[0]


def classify_commercial_signal(task_type: str, task_desc: str) -> tuple[bool, bool]:
    """Return (commercial_signal, strong_commercial_signal) for public tasks."""
    if not str(task_type).startswith("public_"):
        return False, False

    task_body = task_body_only(task_desc)
    task_upper = task_body.upper()
    commercial_keywords_soft = (
        "CLAIM",
        "EVIDENCE",
        "ARTIFACT",
        "GOVERNANCE",
        "SECRET",
        "AUTHORIZATION",
        "TRUST",
        "SEMANTIC",
        "COMPLIANCE",
        "REPAIR",
    )
    commercial_keywords_strong = (
        "CLAIM",
        "EVIDENCE",
        "ARTIFACT",
        "GOVERNANCE",
        "SECRET",
        "AUTHORIZATION",
        "TRUST",
        "COMPLIANCE",
        "SECURITY",
        "RISK",
    )

    has_commercial_signal = any(kw in task_upper for kw in commercial_keywords_soft)
    has_strong_commercial_signal = any(kw in task_upper for kw in commercial_keywords_strong)
    return has_commercial_signal, has_strong_commercial_signal


def extract_keywords(text: str, *, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_]{4,}", (text or "").lower())
    stop = {
        "fix",
        "with",
        "under",
        "from",
        "that",
        "this",
        "task",
        "mode",
        "flow",
        "test",
        "file",
        "when",
    }
    out: list[str] = []
    for token in tokens:
        if token in stop:
            continue
        if token not in out:
            out.append(token)
        if len(out) >= limit:
            break
    return out


def load_history_memory_signal(repo_root: Path, *, task_desc: str, task_type: str) -> dict[str, Any]:
    return HistorySignalStore(repo_root, keyword_extractor=extract_keywords).load_memory_signal(
        task_desc=task_desc,
        task_type=task_type,
    )


def collect_route_signals(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    target_file: str | None = None,
    findings_memory_store_cls: type[FindingsMemoryStore] = FindingsMemoryStore,
) -> RouteSignals:
    task_body = task_body_only(task_desc)
    findings_hits = 0
    memory_hits = 0
    historical_hints = []
    adjusted_root_cause_confidence = root_cause_confidence
    effective_findings_query = findings_query or derive_findings_query(task_body, target_file=target_file)
    if effective_findings_query:
        store = findings_memory_store_cls(repo_root)
        hits = store.search(effective_findings_query)
        findings_hits = len(hits)
        for h in hits:
            historical_hints.extend(h.retrieval_hints)

        if findings_hits >= 1:
            adjusted_root_cause_confidence = max(0.0, root_cause_confidence - 0.15)
    memory_signal = load_history_memory_signal(repo_root, task_desc=task_desc, task_type=task_type)
    memory_hits = int(memory_signal.get("memory_hits", 0) or 0)
    historical_hints.extend(list(memory_signal.get("memory_hints", [])))
    if memory_hits > 0:
        adjusted_root_cause_confidence = max(0.0, adjusted_root_cause_confidence - 0.1)

    policy = ResearchPolicy()
    prediction = {
        "candidate_count": candidate_count,
        "root_cause_confidence": adjusted_root_cause_confidence,
    }
    decision = policy.route({}, task_body, task_type=task_type, prediction=prediction)

    task_lower = task_body.lower()
    target_lower = (target_file or "").lower()
    doc_patterns = ["readme", ".md", "doc:", "fix typo", "documentation", "typo:"]
    is_doc_fix = any(p in task_lower for p in doc_patterns) or any(p in target_lower for p in doc_patterns if p.startswith("."))

    task_upper = task_body.upper()
    hard_keywords = [
        "FLAKY",
        "RACE",
        "DEADLOCK",
        "TIMEOUT",
        "LATENCY",
        "WEBSOCKET",
        "SDK",
        "API",
        "INVARIANT",
        "FAILURE TAIL",
        "SECOND EDIT",
        "SECOND PATCH",
        "SELF-HEAL",
    ]
    cross_module_keywords = ["CROSS-MODULE", "MULTI-MODULE", "COORDINATOR", "SWARM", "DRONE", "NIGHTSHIFT"]
    is_cross_module_task = "cross_module" in str(task_type).lower() or any(kw in task_upper for kw in cross_module_keywords)
    has_commercial_signal, has_strong_commercial_signal = classify_commercial_signal(
        task_type=task_type,
        task_desc=task_desc,
    )
    has_hard_signal = any(kw in task_upper for kw in hard_keywords) or is_cross_module_task or has_strong_commercial_signal

    return {
        "findings_hits": findings_hits,
        "memory_hits": memory_hits,
        "historical_hints": historical_hints,
        "adjusted_root_cause_confidence": adjusted_root_cause_confidence,
        "decision": decision,
        "is_doc_fix": is_doc_fix,
        "is_cross_module_task": is_cross_module_task,
        "has_commercial_signal": has_commercial_signal,
        "has_strong_commercial_signal": has_strong_commercial_signal,
        "has_hard_signal": has_hard_signal,
    }


def derive_findings_query(task_desc: str, target_file: str | None = None) -> str:
    text = " ".join((task_desc or "").split())
    if target_file:
        text = f"{text} {target_file}".strip()
    return text[:200]
