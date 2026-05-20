from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypedDict

from nexus.engine.local_reflex import assess_local_reflex
from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.research.findings_memory import FindingsMemoryStore


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


class RouteHistoryPayload(TypedDict):
    findings_hits: int
    memory_hits: int
    hints_count: int


class RouteExplainPayload(TypedDict):
    task_type: str
    risk: str
    files: list[str]
    history: RouteHistoryPayload
    confidence: float
    reasoning: str


class RouteFeatures(TypedDict):
    task_type: str
    has_hard_signal: bool
    has_commercial_signal: bool
    has_strong_commercial_signal: bool
    is_cross_module_task: bool
    is_doc_fix: bool
    candidate_count: int
    findings_hits: int
    memory_hits: int
    adjusted_root_cause_confidence: float
    risk_score: int
    research_role: str
    claim_uncertainty: bool
    benchmark_required: bool
    plateau_detected: bool
    doc_scout_hits: int
    blocked_assumptions_count: int


class RouteConsensusPayload(TypedDict):
    votes: dict[str, int]
    reasons: list[str]
    winner: str


class RouteDecisionPayload(TypedDict):
    should_research: bool
    mode: str
    reason: str
    recommended_flow: str
    recommended_reason: str
    risk_score: int
    route_features: RouteFeatures
    explain_payload: RouteExplainPayload
    consensus: RouteConsensusPayload


def derive_findings_query(task_desc: str, target_file: str | None = None) -> str:
    text = " ".join((task_desc or "").split())
    if target_file:
        text = f"{text} {target_file}".strip()
    return text[:200]


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
    history_path = (repo_root / ".nexus" / "reports" / "research" / "auto-flow-history.json").resolve()
    if not history_path.exists():
        return {"memory_hits": 0, "memory_hints": []}
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return {"memory_hits": 0, "memory_hints": []}
    if not isinstance(payload, dict):
        return {"memory_hits": 0, "memory_hints": []}

    task_keywords = set(extract_keywords(task_desc))
    memory_hits = 0
    memory_hints: list[str] = []
    for entries in payload.values():
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            if str(item.get("status", "")) != "SUCCESS":
                continue
            hist_task = str(item.get("task_desc", ""))
            hist_type = str(item.get("task_type", ""))
            hist_keywords = set(extract_keywords(hist_task))
            keyword_overlap = len(task_keywords & hist_keywords)
            type_match = bool(task_type and hist_type and task_type == hist_type)
            if keyword_overlap >= 2 and (type_match or keyword_overlap >= 3):
                memory_hits += 1
                if str(item.get("flow", "")):
                    memory_hints.append(f"flow:{item['flow']}")
                if str(item.get("reason", "")):
                    memory_hints.append(f"reason:{item['reason']}")
    uniq_hints = list(dict.fromkeys(memory_hints))[:4]
    return {"memory_hits": memory_hits, "memory_hints": uniq_hints}


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


def decide_flow(
    *,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    target_file: str | None,
    signals: RouteSignals,
    routing_hint: dict[str, Any] | None = None,
) -> RouteDecisionPayload:
    task_body = task_body_only(task_desc)
    task_body_lower = task_body.lower()
    contract_suffix_detected = task_body != (task_desc or "")
    task_type_lower = str(task_type).lower()
    task_type_base = task_type_lower.removeprefix("public_")
    findings_hits = signals["findings_hits"]
    memory_hits = signals["memory_hits"]
    adjusted_root_cause_confidence = signals["adjusted_root_cause_confidence"]
    decision = signals["decision"]
    is_doc_fix = signals["is_doc_fix"]
    is_cross_module_task = signals["is_cross_module_task"]
    has_commercial_signal = signals["has_commercial_signal"]
    has_strong_commercial_signal = signals["has_strong_commercial_signal"]
    has_hard_signal = signals["has_hard_signal"]

    known_benchmark_hidden_contract = bool(
        "verification test" in task_body_lower
        or (
            task_type_base in {"bugfix", "docs_code_sync"}
            and "renamed public field" in task_body_lower
            and "canonical field" in task_body_lower
        )
    )
    benchmark_hidden_contract_fast_path = bool(
        contract_suffix_detected
        and task_type_base in {"bugfix", "docs_code_sync"}
        and findings_hits == 0
        and not has_hard_signal
        and adjusted_root_cause_confidence >= 0.5
        and known_benchmark_hidden_contract
    )
    if is_doc_fix:
        recommended_flow = "baseline"
        recommended_reason = "Matched Doc-Fix Rule"
    elif benchmark_hidden_contract_fast_path:
        recommended_flow = "baseline"
        recommended_reason = "benchmark_hidden_contract_fast_path"
    elif has_strong_commercial_signal:
        recommended_flow = "hyper_sprint"
        recommended_reason = "commercial_public_task_prefers_hyper"
    elif task_type in ["feature", "refactor"]:
        recommended_flow = "baseline"
        recommended_reason = f"structural_task_type_{task_type}_prefer_baseline"
    else:
        is_public_task = str(task_type).startswith("public_")
        is_non_strong_public_task = is_public_task and not has_strong_commercial_signal
        is_risky_bug = findings_hits > 0 or memory_hits > 0 or has_hard_signal
        if not is_non_strong_public_task:
            is_risky_bug = (
                is_risky_bug
                or decision.should_research
                or candidate_count > 1
                or adjusted_root_cause_confidence < 0.75
            )
        recommended_flow = "hyper_sprint" if is_risky_bug else "baseline"
        recommended_reason = "complex_bug_prefer_hyper" if is_risky_bug else "simple_bug_prefer_baseline"

    hint = routing_hint if isinstance(routing_hint, dict) else {}
    hint_mode = str(hint.get("mode", "") or "").strip().lower()
    hint_complexity_raw = hint.get("complexity", "")
    hint_complexity = str(hint_complexity_raw or "").strip().lower()
    hint_should_research = hint.get("should_research", None)
    hint_recommended_flow = str(hint.get("recommended_flow", "") or "").strip().lower()
    hint_confidence_raw = hint.get("confidence", None)
    hint_confidence: float | None = None
    if hint_confidence_raw is not None:
        try:
            hint_confidence = min(1.0, max(0.0, float(hint_confidence_raw)))
        except Exception:
            hint_confidence = None
    hint_complexity_hard = (
        hint_complexity in {"hard", "very_hard", "critical", "high", "p1", "p0"}
        or hint_complexity.startswith("hard_")
    )
    if not hint_complexity_hard:
        try:
            hint_complexity_hard = float(hint_complexity_raw) >= 8.0
        except Exception:
            hint_complexity_hard = False
    router_hint_applied = False
    if hint_recommended_flow in {"baseline", "hyper_sprint"} and not is_doc_fix:
        recommended_flow = hint_recommended_flow
        recommended_reason = f"router_hint_recommended_flow:{hint_recommended_flow}"
        router_hint_applied = True
    elif not is_doc_fix:
        if hint_mode == "research_first" or hint_complexity_hard or hint_should_research is True:
            recommended_flow = "hyper_sprint"
            recommended_reason = "router_hint_forced_hyper"
            router_hint_applied = True
        elif hint_should_research is False and hint_mode == "standard" and task_type not in {"feature", "refactor"}:
            recommended_flow = "baseline"
            recommended_reason = "router_hint_forced_baseline"
            router_hint_applied = True

    consensus_votes = {
        "baseline": 0,
        "hyper_sprint": 0,
    }
    vote_reasons: list[str] = []
    if is_doc_fix:
        consensus_votes["baseline"] += 2
        vote_reasons.append("doc_fix_prefers_baseline")
    if has_hard_signal:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("hard_signal_prefers_hyper")
    if has_strong_commercial_signal:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("commercial_public_task_prefers_hyper")
    if adjusted_root_cause_confidence < 0.75:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("low_confidence_prefers_hyper")
    if findings_hits > 0:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("history_hits_prefers_hyper")
    if memory_hits > 0:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("memory_hits_prefers_hyper")
    if task_type in {"feature", "refactor"}:
        consensus_votes["baseline"] += 1
        vote_reasons.append("structural_task_prefers_baseline")
    if router_hint_applied:
        if recommended_flow == "hyper_sprint":
            consensus_votes["hyper_sprint"] += 1
        else:
            consensus_votes["baseline"] += 1
        vote_reasons.append("router_hint_applied")

    bounded_repair_can_skip_research = bool(
        "repair" in task_type.lower()
        and findings_hits == 0
        and memory_hits == 0
        and not is_cross_module_task
        and adjusted_root_cause_confidence >= 0.75
    )
    benchmark_bounded_repair_contract = bool(
        contract_suffix_detected
        and "repair" in task_type_base
        and findings_hits == 0
        and memory_hits == 0
        and not is_cross_module_task
        and adjusted_root_cause_confidence >= 0.5
        and (
            "behavioral contract" in task_body_lower
            or "failing branch" in task_body_lower
            or "second edit" in task_body_lower
        )
    )
    hyper_research_needed = False if (bounded_repair_can_skip_research or benchmark_bounded_repair_contract) else bool(
        decision.should_research
        or findings_hits > 0
        or memory_hits > 0
        or is_cross_module_task
        or has_strong_commercial_signal
        or adjusted_root_cause_confidence < 0.6
    )
    if recommended_flow == "hyper_sprint":
        should_research = hyper_research_needed
        if should_research:
            mode = decision.mode if decision.mode != "skip" else "external"
            reason = decision.reason if decision.reason != "clear_root_cause" else recommended_reason
        else:
            mode = "skip"
            reason = recommended_reason
    else:
        should_research = False
        mode = "skip"
        reason = recommended_reason if is_doc_fix else "clear_root_cause"

    risk_level = "HIGH" if (has_hard_signal or task_type == "feature") else "LOW"
    if adjusted_root_cause_confidence < 0.5:
        risk_level = "CRITICAL"

    risk_score = 0
    risk_score += 30 if has_hard_signal else 0
    risk_score += 25 if task_type in {"feature", "refactor"} else 10
    risk_score += 25 if adjusted_root_cause_confidence < 0.7 else 0
    risk_score += 15 if findings_hits > 0 else 0
    risk_score += 12 if memory_hits > 0 else 0
    risk_score += 10 if candidate_count > 1 else 0
    risk_score += 20 if is_cross_module_task else 0
    risk_score += 15 if has_commercial_signal else 0
    if benchmark_hidden_contract_fast_path:
        risk_score = min(risk_score, 20)
    elif benchmark_bounded_repair_contract:
        risk_score = min(risk_score, 55)
    risk_score = min(100, risk_score)
    route_features = {
        "task_type": task_type,
        "has_hard_signal": has_hard_signal,
        "has_commercial_signal": has_commercial_signal,
        "has_strong_commercial_signal": has_strong_commercial_signal,
        "is_cross_module_task": is_cross_module_task,
        "is_doc_fix": is_doc_fix,
        "candidate_count": int(candidate_count),
        "findings_hits": findings_hits,
        "memory_hits": memory_hits,
        "adjusted_root_cause_confidence": round(adjusted_root_cause_confidence, 4),
        "risk_score": risk_score,
        "router_hint_applied": router_hint_applied,
        "router_hint_mode": hint_mode,
        "router_hint_complexity": hint_complexity,
        "router_hint_confidence": hint_confidence,
        "research_role": "general",
        "claim_uncertainty": False,
        "benchmark_required": False,
        "plateau_detected": False,
        "benchmark_hidden_contract_fast_path": benchmark_hidden_contract_fast_path,
        "doc_scout_hits": 0,
        "blocked_assumptions_count": 0,
    }
    route_features.update(
        assess_local_reflex(
            task_desc=task_desc,
            task_type=task_type,
            difficulty="hard" if has_hard_signal else "unknown",
            category="",
            repo_kind="",
            fixture_kind="",
        ).to_route_features()
    )
    candidate_factory_ready = int(candidate_count) >= 2
    route_features["candidate_factory_readiness_estimate"] = {
        "ready": candidate_factory_ready,
        "status": "READY" if candidate_factory_ready else "SKIPPED",
        "reason": "route_candidate_count_estimate" if candidate_factory_ready else "single_candidate_route_estimate",
        "estimated_candidates": int(candidate_count),
    }

    explain = {
        "task_type": task_type,
        "risk": risk_level,
        "files": [target_file] if target_file else [],
        "history": {
            "findings_hits": findings_hits,
            "memory_hits": memory_hits,
            "hints_count": len(signals["historical_hints"]),
        },
        "confidence": round(adjusted_root_cause_confidence, 2),
        "reasoning": f"Flow '{recommended_flow}' chosen due to {recommended_reason}. TaskType: {task_type}.",
    }
    return {
        "should_research": should_research,
        "mode": mode,
        "reason": reason,
        "recommended_flow": recommended_flow,
        "recommended_reason": recommended_reason,
        "risk_score": risk_score,
        "route_features": route_features,
        "explain_payload": explain,
        "consensus": {
            "votes": consensus_votes,
            "reasons": vote_reasons,
            "winner": recommended_flow,
        },
    }


_derive_findings_query = derive_findings_query
_task_body_only = task_body_only
_classify_commercial_signal = classify_commercial_signal
_extract_keywords = extract_keywords
_load_history_memory_signal = load_history_memory_signal
_collect_route_signals = collect_route_signals
_decide_flow = decide_flow
