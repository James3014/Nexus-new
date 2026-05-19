"""Route-capability taxonomy and skill reclassification for SF-v2."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class RouteCapability:
    capability_id: str
    group: str
    pillar: str
    phases: tuple[str, ...]
    role: str
    keywords: tuple[str, ...]
    legacy_hints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "group": self.group,
            "pillar": self.pillar,
            "phases": list(self.phases),
            "role": self.role,
            "keywords": list(self.keywords),
            "legacy_hints": list(self.legacy_hints),
        }


ROUTE_CAPABILITIES: tuple[RouteCapability, ...] = (
    RouteCapability(
        "direct_master_loop",
        "primary_execution",
        "artifact",
        ("S", "P", "X", "D", "R", "A", "C"),
        "default execution loop and content/rewrite control",
        ("direct", "master loop", "rewrite", "content", "execute", "task"),
    ),
    RouteCapability(
        "repair_loop",
        "primary_execution",
        "artifact",
        ("D", "R", "A", "C"),
        "coding, debugging, refactor, and repair execution",
        ("repair", "debug", "tdd", "test", "refactor", "code quality", "fix", "python", "java"),
        ("repair_and_coding",),
    ),
    RouteCapability(
        "hyper_sprint",
        "primary_execution",
        "belief",
        ("P", "X", "D", "R"),
        "fast multi-candidate local repair and sprint execution",
        ("hyper", "sprint", "multi-candidate", "quick fix", "fast path"),
    ),
    RouteCapability(
        "nightshift",
        "primary_execution",
        "memory",
        ("D", "R", "A", "C"),
        "long-running recovery after normal repair fails",
        (
            "nightshift",
            "night shift",
            "longrun",
            "long-running",
            "recovery",
            "emergency recovery",
            "autonomous task",
            "continuous optimization",
        ),
    ),
    RouteCapability(
        "codeintel",
        "scout_context",
        "artifact",
        ("S", "P", "X"),
        "code graph, impact analysis, and repository context",
        (
            "codeintel",
            "code scan",
            "impact",
            "symbol",
            "ast",
            "repo graph",
            "dependency graph",
            "architecture",
            "api",
            "interface",
            "schema-analysis",
            "code simplification",
        ),
    ),
    RouteCapability(
        "research",
        "scout_context",
        "lancedb",
        ("S", "P", "X", "R"),
        "source discovery, citation, claim tracing, and research routes",
        ("research", "source", "citation", "arxiv", "paper", "browse", "web", "perplexity", "search"),
        ("research_and_source_discipline",),
    ),
    RouteCapability(
        "research_control_plane",
        "scout_context",
        "claim",
        ("S", "P", "X", "R", "C"),
        "research planning, source conflict handling, and research gates",
        ("source conflict", "source validation", "citation chain", "claim verification", "academic verify"),
        ("research_and_source_discipline",),
    ),
    RouteCapability(
        "xray",
        "scout_context",
        "artifact",
        ("S", "X", "R"),
        "deep inspection and hidden-state diagnostics",
        ("xray", "inspect", "diagnose", "root cause", "probe", "investigate"),
    ),
    RouteCapability(
        "learn_ask",
        "scout_context",
        "memory",
        ("S", "P", "R", "C"),
        "learn, ask, ingest, and report workflows",
        ("learn", "ingest", "ask", "report", "knowledge", "notebook"),
        ("notebook_and_knowledge_injection",),
    ),
    RouteCapability(
        "lancedb",
        "scout_context",
        "lancedb",
        ("S", "X", "R"),
        "vector search, semantic retrieval, and findings lookup",
        ("lancedb", "vector", "embedding", "semantic", "rag", "retrieval"),
    ),
    RouteCapability(
        "memory",
        "memory_learning",
        "memory",
        ("S", "P", "R", "C"),
        "long-term memory and durable experience reuse",
        ("memory", "findings", "remember", "recall", "experience", "vault"),
    ),
    RouteCapability(
        "learning_closure",
        "memory_learning",
        "memory",
        ("R", "A", "C"),
        "lesson writeback, closure matrices, and learning KPI/SLO",
        (
            "learning closure",
            "lesson",
            "writeback",
            "slo",
            "kpi",
            "closure matrix",
            "goal closure",
            "closure executor",
            "continuous optimization",
            "autotune",
        ),
    ),
    RouteCapability(
        "autoreason",
        "reasoning_acceleration",
        "belief",
        ("P", "X", "D", "R"),
        "candidate evaluation, semantic confidence, and reasoned selection",
        ("autoreason", "reason", "judge", "confidence", "semantic"),
    ),
    RouteCapability(
        "ddtree",
        "reasoning_acceleration",
        "belief",
        ("P", "X", "D"),
        "candidate pruning and decision-tree acceleration",
        ("ddtree", "decision tree", "prune", "candidate selection"),
    ),
    RouteCapability(
        "belief",
        "reasoning_acceleration",
        "belief",
        ("P", "X", "D", "R"),
        "belief state, subjective confidence, and route priors",
        ("belief", "confidence", "prior", "budget", "doubt", "careful", "strategy", "strategic"),
    ),
    RouteCapability(
        "autonomic_router",
        "reasoning_acceleration",
        "belief",
        ("S", "P", "X"),
        "autonomic route selection and route evolution",
        ("autonomic", "router", "routing", "route"),
    ),
    RouteCapability(
        "forecast_pregate",
        "reasoning_acceleration",
        "belief",
        ("S", "P"),
        "forecast, pregate, plan quality, and risk prediction",
        ("forecast", "pregate", "plan quality", "risk", "planner"),
        ("planning_and_handoff",),
    ),
    RouteCapability(
        "swarm_multi_agent",
        "collaboration",
        "artifact",
        ("P", "X", "D", "A", "C"),
        "swarm, multi-agent, worktree, submit, verify, integrate",
        ("swarm", "multi-agent", "worktree", "fleet", "integrate", "submit"),
    ),
    RouteCapability(
        "drone",
        "collaboration",
        "artifact",
        ("X", "D", "R"),
        "delegated worker tactical execution and HUD monitoring",
        ("drone", "hud", "delegate", "worker"),
    ),
    RouteCapability(
        "file_lock_security_gate",
        "collaboration",
        "mempalace",
        ("P", "D", "A"),
        "file-lock and delegated execution safety boundaries",
        ("file lock", "lock", "security gate", "permission", "sandbox permission"),
    ),
    RouteCapability(
        "mempalace",
        "governance_risk",
        "mempalace",
        ("S", "P", "A", "C"),
        "ethical boundary, memory palace, and forbidden action constraints",
        ("mempalace", "ethic", "policy", "guardrail", "safety", "boundary"),
    ),
    RouteCapability(
        "policy_capability_gate",
        "governance_risk",
        "mempalace",
        ("S", "P", "A", "C"),
        "policy, capability, and learning gates",
        ("policy gate", "capability gate", "learning gate", "governance", "trust"),
        ("governance_and_trust",),
    ),
    RouteCapability(
        "ultra_review",
        "governance_risk",
        "artifact",
        ("A", "C"),
        "fleet review, security, logic, and regression review",
        ("ultra review", "review", "audit", "security", "regression"),
        ("governance_and_trust",),
    ),
    RouteCapability(
        "artifact_gate",
        "delivery_validation",
        "artifact",
        ("A", "C"),
        "objective evidence and artifact validation",
        ("artifact", "evidence", "verifier", "receipt"),
        ("governance_and_trust",),
    ),
    RouteCapability(
        "claim_gate",
        "delivery_validation",
        "claim",
        ("A", "C"),
        "claim checks, public claims, and mismatch prevention",
        ("claim", "public claim", "assertion", "source refs"),
        ("governance_and_trust",),
    ),
    RouteCapability(
        "delivery_acceptance_gate",
        "delivery_validation",
        "artifact",
        ("A", "C"),
        "delivery gate, acceptance check, and contract checks",
        ("delivery", "acceptance", "contract", "done criteria"),
    ),
    RouteCapability(
        "sandbox_replay",
        "delivery_validation",
        "artifact",
        ("D", "R", "A"),
        "sandboxed execution and replay validation",
        ("sandbox", "replay", "isolation", "rerun", "browser testing", "e2e", "unittest", "test runner"),
    ),
    RouteCapability(
        "benchmark_meta_opt",
        "self_evolution",
        "claim",
        ("R", "A", "C"),
        "benchmark, meta optimization, ROI, and route cost validation",
        ("benchmark", "eval", "meta-opt", "roi", "cost", "performance"),
        ("benchmark_and_promotion",),
    ),
    RouteCapability(
        "regression_guard",
        "self_evolution",
        "artifact",
        ("R", "A", "C"),
        "regression guard, stress, and continuity checks",
        ("regression", "stress", "load test", "performance test", "guard"),
        ("benchmark_and_promotion",),
    ),
    RouteCapability(
        "registry_skills_sync",
        "productization",
        "artifact",
        ("S", "C"),
        "skill registry, plugin sync, and catalog maintenance",
        ("skill registry", "registry", "plugin", "install", "catalog", "sync"),
    ),
    RouteCapability(
        "metabolism_resume",
        "productization",
        "memory",
        ("R", "C"),
        "metabolism, distill, resume, and handoff continuity",
        ("metabolism", "distill", "resume", "handoff", "context"),
        ("planning_and_handoff",),
    ),
    RouteCapability(
        "ui_validator",
        "productization",
        "artifact",
        ("D", "A", "C"),
        "UI validation and browser-driven checks",
        ("ui", "browser", "frontend", "visual", "playwright"),
    ),
    RouteCapability(
        "external_productivity",
        "productization",
        "artifact",
        ("S", "D"),
        "documents, calendars, sheets, email, creative and productivity tools",
        ("gmail", "calendar", "sheets", "docs", "slides", "airtable", "creative", "image", "video"),
    ),
)


CAPABILITY_BY_ID = {capability.capability_id: capability for capability in ROUTE_CAPABILITIES}


def build_route_capability_taxonomy() -> dict[str, Any]:
    groups = Counter(capability.group for capability in ROUTE_CAPABILITIES)
    pillars = Counter(capability.pillar for capability in ROUTE_CAPABILITIES)
    phases = Counter(phase for capability in ROUTE_CAPABILITIES for phase in capability.phases)
    return {
        "schema": "nexus.sf2_route_capability_taxonomy.v1",
        "status": "PASS",
        "summary": {
            "capability_count": len(ROUTE_CAPABILITIES),
            "group_counts": dict(sorted(groups.items())),
            "pillar_counts": dict(sorted(pillars.items())),
            "phase_counts": dict(sorted(phases.items())),
        },
        "capabilities": [capability.to_dict() for capability in ROUTE_CAPABILITIES],
        "claim_boundary": [
            "This taxonomy classifies skill-fit candidates for SF-v2; it does not mount skills at runtime.",
            "Capability routing remains the primary router; skills are subordinate capability-local modules.",
        ],
    }


def _candidate_text(candidate: Mapping[str, Any]) -> str:
    parts = [
        candidate.get("skill_id"),
        candidate.get("name"),
        candidate.get("dir_name"),
        candidate.get("source_root"),
        candidate.get("source_type"),
        candidate.get("load_when"),
        candidate.get("description"),
        candidate.get("path"),
        candidate.get("family"),
        " ".join(str(item) for item in candidate.get("capability_candidates", []) or []),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _keyword_score(text: str, keywords: Iterable[str]) -> int:
    score = 0
    for keyword in keywords:
        normalized = keyword.lower()
        if not normalized:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text):
            score += 3 if " " in normalized else 1
    return score


def classify_skill_for_route_capabilities(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    text = _candidate_text(candidate)
    legacy_hints = {str(item) for item in candidate.get("capability_candidates", []) or []}
    scored: list[tuple[int, RouteCapability, list[str]]] = []
    for capability in ROUTE_CAPABILITIES:
        reasons: list[str] = []
        capability_id_score = 0
        if capability.capability_id in text:
            capability_id_score = 12
            reasons.append(f"capability_id_match:{capability.capability_id}")
        keyword_score = _keyword_score(text, capability.keywords)
        score = capability_id_score + keyword_score
        if keyword_score:
            reasons.append(f"route_keyword_score:{keyword_score}")
        matched_legacy = sorted(legacy_hints.intersection(capability.legacy_hints))
        if matched_legacy:
            score += 8
            reasons.extend(f"legacy_hint:{item}" for item in matched_legacy)
        if score:
            scored.append((score, capability, reasons))
    if not scored:
        fallback = CAPABILITY_BY_ID["external_productivity"]
        return [
            {
                "capability_id": fallback.capability_id,
                "group": fallback.group,
                "pillar": fallback.pillar,
                "phases": list(fallback.phases),
                "confidence": "low",
                "score": 0,
                "reasons": ["fallback:no_route_keyword_match"],
            }
        ]
    selected = sorted(scored, key=lambda item: (-item[0], item[1].capability_id))[:5]
    return [
        {
            "capability_id": capability.capability_id,
            "group": capability.group,
            "pillar": capability.pillar,
            "phases": list(capability.phases),
            "confidence": "high" if score >= 8 else "medium" if score >= 3 else "low",
            "score": score,
            "reasons": reasons,
        }
        for score, capability, reasons in selected
    ]


def build_skill_route_reclassification(candidate_pool: Mapping[str, Any]) -> dict[str, Any]:
    candidates = [item for item in candidate_pool.get("candidates", []) if isinstance(item, Mapping)]
    reclassified = []
    capability_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    safety_counts: Counter[str] = Counter()
    unmapped_low_confidence = 0
    for candidate in candidates:
        route_capabilities = classify_skill_for_route_capabilities(candidate)
        for route_capability in route_capabilities:
            capability_counts[route_capability["capability_id"]] += 1
            confidence_counts[route_capability["confidence"]] += 1
        safety_counts[str(candidate.get("safety_status") or "")] += 1
        if route_capabilities[0]["confidence"] == "low":
            unmapped_low_confidence += 1
        reclassified.append(
            {
                "skill_id": candidate.get("skill_id", ""),
                "path": candidate.get("path", ""),
                "source_root": candidate.get("source_root", ""),
                "source_type": candidate.get("source_type", ""),
                "safety_status": candidate.get("safety_status", ""),
                "ablation_eligible": bool(candidate.get("ablation_eligible")),
                "runtime_eligible": bool(candidate.get("runtime_eligible")),
                "legacy_capability_candidates": list(candidate.get("capability_candidates", []) or []),
                "load_when": candidate.get("load_when", ""),
                "metadata_quality": candidate.get("metadata_quality", ""),
                "route_capability_candidates": route_capabilities,
            }
        )
    return {
        "schema": "nexus.sf2_skill_route_reclassification.v1",
        "status": "PASS",
        "source_candidate_pool_schema": candidate_pool.get("schema", ""),
        "summary": {
            "skill_count": len(reclassified),
            "classified_skill_count": len(reclassified),
            "low_confidence_primary_count": unmapped_low_confidence,
            "capability_coverage_count": len(capability_counts),
            "capability_counts": dict(sorted(capability_counts.items())),
            "confidence_counts": dict(sorted(confidence_counts.items())),
            "safety_status_counts": dict(sorted(safety_counts.items())),
        },
        "claim_boundary": [
            "Reclassification is candidate routing metadata, not skill effectiveness evidence.",
            "Low-confidence fallback classifications require review before ablation.",
        ],
        "skills": reclassified,
    }


def _selection_score(skill: Mapping[str, Any], capability_id: str) -> int:
    score = 0
    if skill.get("runtime_eligible"):
        score += 100
    if skill.get("ablation_eligible"):
        score += 40
    if skill.get("source_root") == "nexus_repo":
        score += 25
    if skill.get("source_root") == "sf2_spec_overlay":
        score += 200
    if skill.get("safety_status") == "runtime_reviewed":
        score += 25
    for candidate in skill.get("route_capability_candidates", []) or []:
        if candidate.get("capability_id") == capability_id:
            score += int(candidate.get("score") or 0)
            confidence = candidate.get("confidence")
            if confidence == "high":
                score += 20
            elif confidence == "medium":
                score += 10
    return score


def build_sf2_capability_candidate_selection(
    reclassification: Mapping[str, Any],
    *,
    max_candidates_per_capability: int = 8,
) -> dict[str, Any]:
    by_capability: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    repairable_by_capability: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for skill in reclassification.get("skills", []) or []:
        if not isinstance(skill, Mapping):
            continue
        if skill.get("safety_status") == "quarantined":
            continue
        for capability in skill.get("route_capability_candidates", []) or []:
            capability_id = str(capability.get("capability_id") or "")
            if not capability_id:
                continue
            if skill.get("ablation_eligible") or skill.get("runtime_eligible"):
                by_capability[capability_id].append(skill)
            else:
                repairable_by_capability[capability_id].append(skill)

    selections = []
    gaps = []
    for capability in ROUTE_CAPABILITIES:
        seen = set()
        ranked = []
        for skill in sorted(
            by_capability.get(capability.capability_id, []),
            key=lambda item: (-_selection_score(item, capability.capability_id), str(item.get("skill_id") or "")),
        ):
            skill_id = str(skill.get("skill_id") or "")
            if not skill_id or skill_id in seen:
                continue
            seen.add(skill_id)
            ranked.append(
                {
                    "skill_id": skill_id,
                    "path": skill.get("path", ""),
                    "source_root": skill.get("source_root", ""),
                    "source_type": skill.get("source_type", ""),
                    "safety_status": skill.get("safety_status", ""),
                    "runtime_eligible": bool(skill.get("runtime_eligible")),
                    "ablation_eligible": bool(skill.get("ablation_eligible")),
                    "metadata_quality": skill.get("metadata_quality", ""),
                    "selection_score": _selection_score(skill, capability.capability_id),
                }
            )
            if len(ranked) >= max_candidates_per_capability:
                break
        if not ranked:
            repairable = []
            seen_repairable = set()
            for skill in sorted(
                repairable_by_capability.get(capability.capability_id, []),
                key=lambda item: (-_selection_score(item, capability.capability_id), str(item.get("skill_id") or "")),
            ):
                skill_id = str(skill.get("skill_id") or "")
                if not skill_id or skill_id in seen_repairable:
                    continue
                seen_repairable.add(skill_id)
                repairable.append(
                    {
                        "skill_id": skill_id,
                        "path": skill.get("path", ""),
                        "source_root": skill.get("source_root", ""),
                        "source_type": skill.get("source_type", ""),
                        "safety_status": skill.get("safety_status", ""),
                        "runtime_eligible": bool(skill.get("runtime_eligible")),
                        "ablation_eligible": bool(skill.get("ablation_eligible")),
                        "metadata_quality": skill.get("metadata_quality", ""),
                        "selection_score": _selection_score(skill, capability.capability_id),
                    }
                )
                if len(repairable) >= max_candidates_per_capability:
                    break
        else:
            repairable = []
        if not ranked and not repairable:
            gaps.append(f"{capability.capability_id}:no_candidate_supply")
        selections.append(
            {
                "capability_id": capability.capability_id,
                "group": capability.group,
                "pillar": capability.pillar,
                "phases": list(capability.phases),
                "candidate_count": len(ranked),
                "candidates": ranked,
                "metadata_repair_candidate_count": len(repairable),
                "metadata_repair_candidates": repairable,
                "next_action": "ablation_plan_ready"
                if ranked
                else "metadata_repair_required"
                if repairable
                else "candidate_supply_gap",
            }
        )
    return {
        "schema": "nexus.sf2_capability_candidate_selection.v1",
        "status": "PASS",
        "summary": {
            "capability_count": len(selections),
            "capabilities_with_candidates": sum(1 for item in selections if item["candidate_count"]),
            "capabilities_with_metadata_repair_candidates": sum(
                1 for item in selections if not item["candidate_count"] and item["metadata_repair_candidate_count"]
            ),
            "capabilities_without_candidates": sum(
                1
                for item in selections
                if not item["candidate_count"] and not item["metadata_repair_candidate_count"]
            ),
            "capabilities_without_ablation_candidates": sum(1 for item in selections if not item["candidate_count"]),
            "candidate_gap_count": len(gaps),
        },
        "gaps": gaps,
        "selections": selections,
        "claim_boundary": [
            "Candidate selection prepares SF-v2 ablation. It is not benchmark evidence.",
            "Runtime promotion remains blocked until per-capability ablation and runtime review pass.",
        ],
    }


def build_sf2_metadata_repair_plan(selection: Mapping[str, Any]) -> dict[str, Any]:
    """Build a bounded metadata repair plan without changing runtime eligibility."""

    repair_items = []
    for item in selection.get("selections", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        if item.get("candidate_count"):
            continue
        for candidate in item.get("metadata_repair_candidates", []) or []:
            if not isinstance(candidate, Mapping):
                continue
            repair_items.append(
                {
                    "capability_id": capability_id,
                    "skill_id": candidate.get("skill_id", ""),
                    "path": candidate.get("path", ""),
                    "source_root": candidate.get("source_root", ""),
                    "source_type": candidate.get("source_type", ""),
                    "safety_status": candidate.get("safety_status", ""),
                    "current_metadata_quality": candidate.get("metadata_quality", ""),
                    "required_metadata_fields": [
                        "capability_mount",
                        "load_when",
                        "do_not_load_when",
                        "evidence_required",
                    ],
                    "proposed_capability_mount": f"reference:{capability_id}",
                    "post_repair_ablation_eligible": True,
                    "post_repair_runtime_eligible": False,
                    "runtime_policy": "blocked_from_runtime_until_curated_review",
                }
            )

    capabilities = sorted({item["capability_id"] for item in repair_items})
    return {
        "schema": "nexus.sf2_metadata_repair_plan.v1",
        "status": "PASS",
        "summary": {
            "repair_capability_count": len(capabilities),
            "repair_item_count": len(repair_items),
            "runtime_update_allowed": False,
            "ablation_after_repair_allowed": bool(repair_items),
        },
        "repair_capabilities": capabilities,
        "repair_items": repair_items,
        "claim_boundary": [
            "Metadata repair only makes a candidate eligible for SF-v2 ablation review.",
            "Metadata repair never promotes external or local candidate skills into runtime defaults.",
        ],
    }


def build_sf2_ablation_matrix_plan(
    selection: Mapping[str, Any],
    *,
    max_skill_arms_per_capability: int = 4,
    allow_metadata_repair_overlay: bool = False,
) -> dict[str, Any]:
    """Build a route-capability ablation matrix plan without running live benchmarks."""

    plans = []
    planned_rows = []
    blocked = []
    for item in selection.get("selections", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        candidates = list(item.get("candidates", []) or [])[:max_skill_arms_per_capability]
        metadata_repair_candidates = list(item.get("metadata_repair_candidates", []) or [])
        if not candidates and allow_metadata_repair_overlay and metadata_repair_candidates:
            candidates = [
                {
                    **dict(candidate),
                    "runtime_eligible": False,
                    "ablation_eligible": True,
                    "safety_status": candidate.get("safety_status") or "ablation_only",
                    "metadata_repaired_overlay": True,
                }
                for candidate in metadata_repair_candidates[:max_skill_arms_per_capability]
            ]
        if not candidates:
            reason = "metadata_repair_required" if metadata_repair_candidates else "candidate_supply_gap"
            blocked.append({"capability_id": capability_id, "reason": reason})
            plans.append(
                {
                    "capability_id": capability_id,
                    "status": "BLOCKED",
                    "reason": reason,
                    "candidate_count": 0,
                    "planned_row_count": 0,
                    "rows": [],
                }
            )
            continue

        rows = [
            {
                "row_id": f"{capability_id}::capability_only",
                "capability_id": capability_id,
                "arm_type": "capability_only",
                "skill_id": None,
                "expected_verdict": "baseline",
            }
        ]
        for index, candidate in enumerate(candidates, start=1):
            skill_id = str(candidate.get("skill_id") or "")
            rows.append(
                {
                    "row_id": f"{capability_id}::skill_arm_{index:03d}::{skill_id}",
                    "capability_id": capability_id,
                    "arm_type": "skill_arm",
                    "skill_id": skill_id,
                    "expected_verdict": "measure_outcome_contribution",
                    "runtime_eligible": bool(candidate.get("runtime_eligible")),
                    "ablation_eligible": bool(candidate.get("ablation_eligible")),
                    "safety_status": candidate.get("safety_status", ""),
                    "metadata_repaired_overlay": bool(candidate.get("metadata_repaired_overlay")),
                }
            )
        rows.append(
            {
                "row_id": f"{capability_id}::negative_control",
                "capability_id": capability_id,
                "arm_type": "negative_control",
                "skill_id": "wrong_or_quarantined_skill",
                "expected_verdict": "BLOCK_OR_RETURN",
            }
        )
        planned_rows.extend(rows)
        plans.append(
            {
                "capability_id": capability_id,
                "status": "READY",
                "candidate_count": len(candidates),
                "planned_row_count": len(rows),
                "rows": rows,
            }
        )

    return {
        "schema": "nexus.sf2_ablation_matrix_plan.v1",
        "status": "PASS" if not blocked else "PARTIAL",
        "summary": {
            "capability_count": len(plans),
            "ready_capability_count": sum(1 for item in plans if item["status"] == "READY"),
            "blocked_capability_count": len(blocked),
            "planned_row_count": len(planned_rows),
            "negative_control_count": sum(1 for row in planned_rows if row["arm_type"] == "negative_control"),
            "metadata_repair_overlay_allowed": allow_metadata_repair_overlay,
            "metadata_repair_overlay_row_count": sum(
                1 for row in planned_rows if row.get("metadata_repaired_overlay")
            ),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blocked_capabilities": blocked,
        "plans": plans,
        "claim_boundary": [
            "This matrix is a preflight contract for SF-v2 skill-fit ablation, not a live benchmark result.",
            "Each READY capability still requires capability-only, skill-arm, and negative-control evidence before catalog update.",
        ],
    }


def _route_match_for_capability(skill: Mapping[str, Any], capability_id: str) -> Mapping[str, Any]:
    for route_candidate in skill.get("route_capability_candidates", []) or []:
        if route_candidate.get("capability_id") == capability_id:
            return route_candidate
    return {}


def _route_keyword_score(reasons: Iterable[Any]) -> int:
    for reason in reasons:
        text = str(reason)
        if text.startswith("route_keyword_score:"):
            return int(text.split(":", 1)[1] or 0)
    return 0


def build_sf2_candidate_quality_screen(
    reclassification: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    """Screen selected SF-v2 candidates for weak route-fit before live ablation."""

    skills_by_id = {
        str(skill.get("skill_id") or ""): skill
        for skill in reclassification.get("skills", []) or []
        if isinstance(skill, Mapping)
    }
    screened_candidates = []
    clean_shortlists: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_selection_capabilities: set[str] = set()
    review_capabilities: set[str] = set()
    for item in selection.get("selections", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        if capability_id:
            all_selection_capabilities.add(capability_id)
        for candidate in item.get("candidates", []) or []:
            if not isinstance(candidate, Mapping):
                continue
            skill_id = str(candidate.get("skill_id") or "")
            skill = skills_by_id.get(skill_id, {})
            match = _route_match_for_capability(skill, capability_id)
            confidence = str(match.get("confidence") or "missing")
            score = int(match.get("score") or 0)
            reasons = list(match.get("reasons", []) or [])
            route_keyword_score = _route_keyword_score(reasons)
            review_reasons = []
            if confidence in {"low", "missing"}:
                review_reasons.append(f"weak_match_confidence:{confidence}")
            if score < 3:
                review_reasons.append(f"weak_match_score:{score}")
            if route_keyword_score == 0:
                review_reasons.append(f"insufficient_route_keyword_score:{route_keyword_score}")
            if not candidate.get("ablation_eligible") and not candidate.get("runtime_eligible"):
                review_reasons.append("not_ablation_or_runtime_eligible")
            status = "REVIEW_REQUIRED" if review_reasons else "PASS"
            if status != "PASS":
                review_capabilities.add(capability_id)
            else:
                clean_shortlists[capability_id].append(
                    {
                        "skill_id": skill_id,
                        "confidence": confidence,
                        "score": score,
                        "route_keyword_score": route_keyword_score,
                        "selection_score": candidate.get("selection_score", 0),
                        "runtime_eligible": bool(candidate.get("runtime_eligible")),
                        "ablation_eligible": bool(candidate.get("ablation_eligible")),
                        "safety_status": candidate.get("safety_status", ""),
                    }
                )
            screened_candidates.append(
                {
                    "capability_id": capability_id,
                    "skill_id": skill_id,
                    "status": status,
                    "confidence": confidence,
                    "score": score,
                    "route_keyword_score": route_keyword_score,
                    "match_reasons": reasons,
                    "review_reasons": review_reasons,
                    "selection_score": candidate.get("selection_score", 0),
                    "runtime_eligible": bool(candidate.get("runtime_eligible")),
                    "ablation_eligible": bool(candidate.get("ablation_eligible")),
                    "safety_status": candidate.get("safety_status", ""),
                }
            )
    review_candidates = [item for item in screened_candidates if item["status"] != "PASS"]
    capabilities_without_clean_candidates = sorted(all_selection_capabilities - set(clean_shortlists))
    return {
        "schema": "nexus.sf2_candidate_quality_screen.v1",
        "status": "PASS" if not capabilities_without_clean_candidates else "REVIEW_REQUIRED",
        "summary": {
            "screened_candidate_count": len(screened_candidates),
            "pass_candidate_count": len(screened_candidates) - len(review_candidates),
            "review_candidate_count": len(review_candidates),
            "capabilities_with_review_candidates": len(review_capabilities),
            "capabilities_with_clean_candidates": len(clean_shortlists),
            "capabilities_without_clean_candidates": len(capabilities_without_clean_candidates),
            "sf2_live_probe_allowed": not capabilities_without_clean_candidates,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "review_capabilities": sorted(review_capabilities),
        "capabilities_without_clean_candidates": capabilities_without_clean_candidates,
        "clean_shortlists": [
            {
                "capability_id": capability_id,
                "candidate_count": len(candidates),
                "candidates": candidates,
                "next_action": "sf2_bounded_probe_ready",
            }
            for capability_id, candidates in sorted(clean_shortlists.items())
        ],
        "blocked_shortlists": [
            {
                "capability_id": capability_id,
                "group": CAPABILITY_BY_ID[capability_id].group,
                "pillar": CAPABILITY_BY_ID[capability_id].pillar,
                "phases": list(CAPABILITY_BY_ID[capability_id].phases),
                "required_behavior": CAPABILITY_BY_ID[capability_id].role,
                "required_route_terms": list(CAPABILITY_BY_ID[capability_id].keywords),
                "next_action": "candidate_spec_or_metadata_repair_required",
            }
            for capability_id in capabilities_without_clean_candidates
        ],
        "candidates": screened_candidates,
        "claim_boundary": [
            "Quality screen checks route-fit metadata before live skill-fit ablation.",
            "A PASS candidate is only allowed into SF-v2 ablation; it is not a runtime recommendation.",
        ],
    }


def build_sf2_candidate_spec_overlay(quality_screen: Mapping[str, Any]) -> dict[str, Any]:
    """Create spec-only candidates for capabilities that have no clean live-probe candidate."""

    spec_candidates = []
    for item in quality_screen.get("blocked_shortlists", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        capability = CAPABILITY_BY_ID.get(capability_id)
        if capability is None:
            continue
        terms = list(capability.keywords)
        skill_id = f"sf2-{capability_id}-route-fit-spec"
        spec_candidates.append(
            {
                "skill_id": skill_id,
                "source_root": "sf2_spec_overlay",
                "source_type": "sf2_spec_candidate",
                "path": f"virtual://sf2/spec-candidates/{skill_id}/SKILL.md",
                "sha256": "",
                "capability_candidates": [],
                "load_when": (
                    f"SF2 spec candidate for {capability_id}: {capability.role}. "
                    f"Use when route capability is {capability_id}. "
                    f"Required route terms: {', '.join(terms)}."
                ),
                "forbidden_when": [
                    "runtime_mount",
                    "public_benchmark",
                    "production_policy_update",
                ],
                "metadata_quality": "SPEC_ONLY",
                "safety_status": "ablation_only",
                "ablation_eligible": True,
                "runtime_eligible": False,
                "evidence_required": [
                    "capability_only_baseline",
                    "skill_arm_outcome_contribution",
                    "negative_control_block_or_return",
                    "runtime_receipt_required_before_promotion",
                ],
                "sf2_overlay": {
                    "capability_id": capability_id,
                    "group": capability.group,
                    "pillar": capability.pillar,
                    "phases": list(capability.phases),
                    "required_behavior": capability.role,
                    "materialization_required": True,
                },
            }
        )

    return {
        "schema": "nexus.sf2_candidate_spec_overlay.v1",
        "status": "PASS",
        "summary": {
            "spec_candidate_count": len(spec_candidates),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "materialization_required_before_live": True,
        },
        "spec_candidates": spec_candidates,
        "claim_boundary": [
            "Spec candidates close route-fit supply gaps for planning only.",
            "Spec candidates are not runtime skills until materialized, reviewed, and receipt-backed.",
        ],
    }


def build_sf2_spec_repaired_candidate_pool(
    candidate_pool: Mapping[str, Any],
    spec_overlay: Mapping[str, Any],
) -> dict[str, Any]:
    """Append SF2 spec-only candidates to the candidate pool for planning reports."""

    base_candidates = [item for item in candidate_pool.get("candidates", []) if isinstance(item, Mapping)]
    spec_candidates = [item for item in spec_overlay.get("spec_candidates", []) if isinstance(item, Mapping)]
    return {
        "schema": "nexus.sf2_spec_repaired_candidate_pool.v1",
        "status": "PASS",
        "source_candidate_pool_schema": candidate_pool.get("schema", ""),
        "summary": {
            "base_candidate_count": len(base_candidates),
            "spec_candidate_count": len(spec_candidates),
            "candidate_count": len(base_candidates) + len(spec_candidates),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "candidates": base_candidates + spec_candidates,
        "claim_boundary": [
            "This pool is for SF2 planning and bounded probes only.",
            "Spec-only candidates require materialized skill assets before any runtime promotion review.",
        ],
    }


def build_sf2_candidate_materialization_bundle(spec_overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Build candidate-only SKILL.md materialization specs for SF2 overlay candidates."""

    assets = []
    for candidate in spec_overlay.get("spec_candidates", []) or []:
        if not isinstance(candidate, Mapping):
            continue
        skill_id = str(candidate.get("skill_id") or "")
        overlay = candidate.get("sf2_overlay", {}) if isinstance(candidate.get("sf2_overlay"), Mapping) else {}
        capability_id = str(overlay.get("capability_id") or "")
        capability = CAPABILITY_BY_ID.get(capability_id)
        phases = set(capability.phases) if capability else set()
        target_path = f".agents/skills/sf2/{skill_id}/SKILL.md"
        skill_md = "\n".join(
            [
                "---",
                f"name: {skill_id}",
                f"description: Candidate-only SF2 route-fit skill for {capability_id}.",
                "metadata:",
                f"  capability_id: {capability_id}",
                "  sf2_candidate_only: true",
                "  runtime_eligible: false",
                "  public_benchmark_allowed: false",
                "---",
                "",
                f"# {skill_id}",
                "",
                "## Load when",
                str(candidate.get("load_when") or ""),
                "",
                "## Do not load when",
                "- Runtime default mounting is requested.",
                "- Public benchmark or production policy update is requested.",
                "- The task does not match the declared capability_id.",
                "",
                "## Evidence required",
                "- Capability-only baseline row.",
                "- Skill-arm row with selected/injected/used/evidence/outcome receipt.",
                "- Negative-control row that BLOCKs or RETURNs.",
                "- Runtime promotion review after SF2 verdict.",
                "",
                "## Boundary",
                "This asset is candidate-only. It may be used for SF2 ablation planning, but it must not be treated as a runtime skill default.",
                "",
            ]
        )
        assets.append(
            {
                "skill_id": skill_id,
                "capability_id": capability_id,
                "target_path": target_path,
                "node_layer": "agent_extending",
                "dependencies": [],
                "parallelizable_with": [
                    other.capability_id
                    for other in ROUTE_CAPABILITIES
                    if other.capability_id != capability_id and set(other.phases).isdisjoint(phases)
                ][:5],
                "runtime_eligible": False,
                "ablation_eligible_after_materialization": True,
                "public_benchmark_allowed": False,
                "evidence_outputs_required": [
                    "capability_only_baseline",
                    "skill_arm_receipt",
                    "negative_control_verdict",
                    "prompt_hashes",
                    "forbidden_literal_hits",
                ],
                "retry_policy": {
                    "max_attempts": 1,
                    "fallback": "human_review_or_lite_mode",
                    "budget_safety_floor_preserved": True,
                },
                "context_policy": {
                    "format": "json_ld_ready",
                    "requires_context_compactor_when_cnr_gt": 0.6,
                },
                "skill_md": skill_md,
            }
        )

    return {
        "schema": "nexus.sf2_candidate_materialization_bundle.v1",
        "status": "PASS",
        "summary": {
            "asset_count": len(assets),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "ready_to_write_candidate_assets": bool(assets),
        },
        "assets": assets,
        "claim_boundary": [
            "Materialization bundle is a write plan for candidate-only skill assets.",
            "Writing these assets does not promote them to runtime defaults.",
        ],
    }


def build_sf2_materialization_batch_plan(
    materialization_bundle: Mapping[str, Any],
    *,
    max_assets_per_batch: int = 8,
) -> dict[str, Any]:
    """Split SF2 candidate asset writes into bounded batches."""

    assets = [asset for asset in materialization_bundle.get("assets", []) or [] if isinstance(asset, Mapping)]
    batches = []
    for index in range(0, len(assets), max_assets_per_batch):
        batch_assets = assets[index : index + max_assets_per_batch]
        batch_id = f"SF2-H{len(batches) + 1}"
        batches.append(
            {
                "batch_id": batch_id,
                "status": "READY",
                "asset_count": len(batch_assets),
                "target_paths": [str(asset.get("target_path") or "") for asset in batch_assets],
                "skill_ids": [str(asset.get("skill_id") or "") for asset in batch_assets],
                "exit": "All listed candidate-only SKILL.md assets exist and keep runtime_eligible=false.",
            }
        )

    return {
        "schema": "nexus.sf2_materialization_batch_plan.v1",
        "status": "PASS" if assets else "BLOCKED",
        "summary": {
            "asset_count": len(assets),
            "batch_count": len(batches),
            "max_assets_per_batch": max_assets_per_batch,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "batches": batches,
        "claim_boundary": [
            "Batching exists only to satisfy file-touch and review boundaries.",
            "A completed batch still creates candidate-only assets, not runtime defaults.",
        ],
    }


def build_sf2_closure_gate(
    quality_screen: Mapping[str, Any],
    ablation_matrix: Mapping[str, Any],
    materialization_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Decide whether SF2 can move to bounded probe without opening benchmark/runtime lanes."""

    quality_ready = bool(quality_screen.get("summary", {}).get("sf2_live_probe_allowed"))
    matrix_ready = int(ablation_matrix.get("summary", {}).get("ready_capability_count") or 0) == int(
        ablation_matrix.get("summary", {}).get("capability_count") or -1
    )
    materialization_ready = bool(materialization_bundle.get("summary", {}).get("ready_to_write_candidate_assets"))
    blockers = []
    if not quality_ready:
        blockers.append("quality_screen_not_clean")
    if not matrix_ready:
        blockers.append("ablation_matrix_not_ready")
    if not materialization_ready:
        blockers.append("candidate_materialization_not_ready")
    return {
        "schema": "nexus.sf2_closure_gate.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "quality_ready": quality_ready,
            "matrix_ready": matrix_ready,
            "materialization_ready": materialization_ready,
            "bounded_probe_allowed": not blockers,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "next_task_cards": [
            {
                "id": "SF2-H",
                "title": "Materialize Candidate-Only Skill Assets",
                "status": "READY" if not blockers else "BLOCKED",
                "exit": "17 candidate-only SKILL.md assets exist under .agents/skills/sf2 with runtime_eligible=false.",
            },
            {
                "id": "SF2-I",
                "title": "Bounded SF2 Probe",
                "status": "READY_AFTER_SF2_H" if not blockers else "BLOCKED",
                "exit": "33 route capabilities have capability-only, skill-arm, and negative-control evidence.",
            },
        ],
        "claim_boundary": [
            "SF2 closure gate only allows bounded skill-fit probes.",
            "Runtime promotion and public benchmark remain blocked.",
        ],
    }


def build_sf2_bounded_probe_plan(
    ablation_matrix: Mapping[str, Any],
    asset_status: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the SF2 bounded-probe execution gate from matrix and asset-status reports."""

    matrix_summary = ablation_matrix.get("summary", {}) if isinstance(ablation_matrix.get("summary"), Mapping) else {}
    asset_summary = asset_status.get("summary", {}) if isinstance(asset_status.get("summary"), Mapping) else {}
    capability_count = int(matrix_summary.get("capability_count") or 0)
    ready_capability_count = int(matrix_summary.get("ready_capability_count") or 0)
    asset_count = int(asset_summary.get("asset_count") or 0)
    visible_asset_count = int(asset_summary.get("status_visible_asset_count") or 0)
    blockers = []
    if capability_count == 0 or ready_capability_count != capability_count:
        blockers.append("sf2_matrix_not_fully_ready")
    if asset_count == 0 or visible_asset_count != asset_count:
        blockers.append("sf2_candidate_assets_not_status_visible")

    capability_cards = []
    for plan in ablation_matrix.get("plans", []) or []:
        if not isinstance(plan, Mapping):
            continue
        rows = [row for row in plan.get("rows", []) or [] if isinstance(row, Mapping)]
        capability_cards.append(
            {
                "capability_id": str(plan.get("capability_id") or ""),
                "status": str(plan.get("status") or ""),
                "row_count": len(rows),
                "capability_only_count": sum(1 for row in rows if row.get("arm_type") == "capability_only"),
                "skill_arm_count": sum(1 for row in rows if row.get("arm_type") == "skill_arm"),
                "negative_control_count": sum(1 for row in rows if row.get("arm_type") == "negative_control"),
            }
        )

    return {
        "schema": "nexus.sf2_bounded_probe_plan.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "capability_count": capability_count,
            "ready_capability_count": ready_capability_count,
            "planned_row_count": int(matrix_summary.get("planned_row_count") or 0),
            "status_visible_asset_count": visible_asset_count,
            "asset_count": asset_count,
            "bounded_probe_allowed": not blockers,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "capabilities": capability_cards,
        "next_task_cards": [
            {
                "id": "SF2-I2",
                "title": "Execute Bounded Probe",
                "status": "READY" if not blockers else "BLOCKED",
                "exit": "Each route capability has capability-only, skill-arm, and negative-control evidence.",
            },
            {
                "id": "SF2-J",
                "title": "Route-Skill Verdict Catalog",
                "status": "READY_AFTER_SF2-I2" if not blockers else "BLOCKED",
                "exit": "Capability-to-skill verdicts are generated without opening runtime/public benchmark lanes.",
            },
        ],
        "claim_boundary": [
            "This is a bounded skill-fit probe plan, not a public benchmark plan.",
            "Runtime promotion remains blocked until receipt-backed verdicts are reviewed.",
        ],
    }


def build_sf2_bounded_probe_preflight(
    ablation_matrix: Mapping[str, Any],
    asset_status: Mapping[str, Any],
) -> dict[str, Any]:
    """Check SF2 bounded-probe rows before any live outcome evidence is generated."""

    visible_assets = {
        str(asset.get("skill_id") or "")
        for asset in asset_status.get("assets", []) or []
        if isinstance(asset, Mapping) and asset.get("status") == "PASS"
    }
    row_results = []
    blockers = []
    for plan in ablation_matrix.get("plans", []) or []:
        if not isinstance(plan, Mapping):
            continue
        capability_id = str(plan.get("capability_id") or "")
        if plan.get("status") != "READY":
            blockers.append(f"{capability_id}:plan_not_ready")
            continue
        for row in plan.get("rows", []) or []:
            if not isinstance(row, Mapping):
                continue
            row_id = str(row.get("row_id") or "")
            arm_type = str(row.get("arm_type") or "")
            skill_id = str(row.get("skill_id") or "")
            reason = ""
            if arm_type == "capability_only":
                status = "PASS"
            elif arm_type == "negative_control":
                status = "PASS"
            elif arm_type == "skill_arm":
                if skill_id.startswith("sf2-") and skill_id not in visible_assets:
                    status = "BLOCKED"
                    reason = "sf2_candidate_asset_not_status_visible"
                elif not bool(row.get("ablation_eligible")) and not bool(row.get("runtime_eligible")):
                    status = "BLOCKED"
                    reason = "skill_arm_not_ablation_or_runtime_eligible"
                else:
                    status = "PASS"
            else:
                status = "BLOCKED"
                reason = "unknown_arm_type"
            if status != "PASS":
                blockers.append(f"{row_id}:{reason}")
            row_results.append(
                {
                    "row_id": row_id,
                    "capability_id": capability_id,
                    "arm_type": arm_type,
                    "skill_id": skill_id or None,
                    "status": status,
                    "reason": reason,
                    "runtime_update_allowed": False,
                    "public_benchmark_allowed": False,
                    "outcome_contribution_claimed": False,
                }
            )

    return {
        "schema": "nexus.sf2_bounded_probe_preflight.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "row_count": len(row_results),
            "pass_count": sum(1 for row in row_results if row["status"] == "PASS"),
            "blocker_count": len(blockers),
            "bounded_probe_live_allowed": not blockers,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "outcome_contribution_claimed": False,
        },
        "blockers": blockers,
        "rows": row_results,
        "claim_boundary": [
            "Preflight proves rows are safe to execute; it does not claim skill value.",
            "Outcome contribution requires live bounded-probe evidence after this gate.",
        ],
    }


def build_sf2_bounded_probe_task_manifest(
    taxonomy: Mapping[str, Any],
) -> dict[str, Any]:
    """Create deterministic SF2 capability tasks for bounded probe setup."""

    tasks = []
    for item in taxonomy.get("capabilities", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        task_id = f"sf2-route-fit-{capability_id}-001"
        task_desc = (
            f"Exercise route capability {capability_id} using its declared role, "
            "then require skill-fit receipt evidence without runtime promotion."
        )
        tasks.append(
            {
                "id": task_id,
                "task_id": task_id,
                "capability_id": capability_id,
                "group": str(item.get("group") or ""),
                "pillar": str(item.get("pillar") or ""),
                "phases": list(item.get("phases") or []),
                "difficulty": "medium",
                "task_type": "sf2_route_fit",
                "task_desc": task_desc,
                "prompt": task_desc,
                "target_file": "unused",
                "test_file": "unused",
                "success_criteria": "sf2_bounded_probe_receipt_chain_complete",
                "category": capability_id,
                "repo_kind": "neutral_fixture",
                "fixture_kind": "sf2_route_fit",
                "expected_capabilities": [capability_id],
                "capability_activation_contract": "sf2_bounded_probe",
                "eligibility_class": "sf2_internal",
                "expected_evidence": [
                    "capability_only_baseline",
                    "skill_arm_receipt",
                    "negative_control_block_or_return",
                    "outcome_contribution_decision",
                ],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    return {
        "schema": "nexus.sf2_bounded_probe_task_manifest.v1",
        "status": "PASS" if tasks else "BLOCKED",
        "summary": {
            "task_count": len(tasks),
            "capability_count": len({task["capability_id"] for task in tasks}),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "tasks": tasks,
        "claim_boundary": [
            "These are SF2 bounded-probe tasks, not public benchmark tasks.",
            "They only establish a fixed denominator for route-skill fit evidence.",
        ],
    }


def build_sf2_bounded_probe_execution_manifest(
    ablation_matrix: Mapping[str, Any],
    task_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach one bounded-probe task to each SF2 capability/arm row."""

    tasks_by_capability = {
        str(task.get("capability_id") or ""): task
        for task in task_manifest.get("tasks", []) or []
        if isinstance(task, Mapping)
    }
    rows = []
    blockers = []
    for plan in ablation_matrix.get("plans", []) or []:
        if not isinstance(plan, Mapping):
            continue
        capability_id = str(plan.get("capability_id") or "")
        task = tasks_by_capability.get(capability_id)
        if not task:
            blockers.append(f"{capability_id}:missing_probe_task")
            continue
        for row in plan.get("rows", []) or []:
            if not isinstance(row, Mapping):
                continue
            task_id = str(task.get("task_id") or task.get("id") or "")
            skill_id = str(row.get("skill_id") or "")
            arm_type = str(row.get("arm_type") or "")
            runner_env: dict[str, str] = {
                "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
                "NEXUS_SF2_BOUNDED_PROBE": "1",
                "NEXUS_SF2_ROUTE_CAPABILITY": capability_id,
            }
            if arm_type == "skill_arm" and skill_id:
                runner_env["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"] = skill_id
            elif arm_type == "negative_control":
                runner_env["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"] = f"sf2-negative-control::{capability_id}"
            rows.append(
                {
                    **dict(row),
                    "capability": capability_id,
                    "task_ref": {
                        "manifest": "docs/reports/NEXUS_SF2_BOUNDED_PROBE_TASK_MANIFEST_2026-05-18.json",
                        "task_id": task_id,
                    },
                    "runner_args": [
                        "uv",
                        "run",
                        "python",
                        "scripts/bench/capability_ab_runner.py",
                        "--tasks-file",
                        "docs/reports/NEXUS_SF2_BOUNDED_PROBE_TASK_MANIFEST_2026-05-18.json",
                        "--task-id-filter",
                        task_id,
                        "--max-tasks",
                        "1",
                        "--nexus-only",
                        "--with-llm-mode",
                        "off",
                        "--timeout-sec",
                        "30",
                        "--per-task-stop-loss-sec",
                        "120",
                        "--stop-loss-sec",
                        "180",
                        "--no-progress-log",
                    ],
                    "runner_env": runner_env,
                    "execution_mode": "sf2_bounded_probe",
                    "runtime_update_allowed": False,
                    "public_benchmark_allowed": False,
                }
            )

    return {
        "schema": "nexus.sf2_bounded_probe_execution_manifest.v1",
        "status": "PASS" if rows and not blockers else "BLOCKED",
        "summary": {
            "row_count": len(rows),
            "capability_count": len({str(row.get("capability_id") or "") for row in rows}),
            "blocker_count": len(blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "ready_for_sf2_live_probe": bool(rows and not blockers),
        },
        "blockers": blockers,
        "rows": rows,
        "claim_boundary": [
            "Execution manifest schedules bounded skill-fit probe rows only.",
            "It is not outcome evidence until live receipts are produced.",
        ],
    }


def build_sf2_bounded_probe_chunk_plan(
    execution_manifest: Mapping[str, Any],
    *,
    max_rows_per_chunk: int = 24,
) -> dict[str, Any]:
    """Split SF2 bounded-probe execution rows into continuation chunks."""

    rows = [row for row in execution_manifest.get("rows", []) or [] if isinstance(row, Mapping)]
    chunks = []
    for index in range(0, len(rows), max_rows_per_chunk):
        chunk_rows = rows[index : index + max_rows_per_chunk]
        chunk_id = f"SF2-I3-{len(chunks) + 1:02d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "status": "READY",
                "row_count": len(chunk_rows),
                "row_ids": [str(row.get("row_id") or "") for row in chunk_rows],
                "capability_ids": sorted({str(row.get("capability_id") or "") for row in chunk_rows}),
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
                "exit": "Chunk rows produce bounded-probe receipts or fail closed with a reason code.",
            }
        )

    return {
        "schema": "nexus.sf2_bounded_probe_chunk_plan.v1",
        "status": "PASS" if rows else "BLOCKED",
        "summary": {
            "row_count": len(rows),
            "chunk_count": len(chunks),
            "max_rows_per_chunk": max_rows_per_chunk,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "chunks": chunks,
        "claim_boundary": [
            "Chunks are continuation units for SF2 bounded probe only.",
            "Chunk completion is not public benchmark or runtime promotion evidence.",
        ],
    }


def write_json_report(report: Mapping[str, Any], output_path: str | Path) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dict(report)
