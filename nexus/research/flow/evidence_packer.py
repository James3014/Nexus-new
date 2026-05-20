from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from nexus.engine.asi_constraints import ASIConstraintStore
from nexus.research.doc_scout_adapter import DocScoutAdapter, build_external_scout_providers_from_env
from nexus.research.flow.route_decider import task_body_only


def safe_trace_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(text or "task")).strip("-")
    return slug[:96] or "task"


def write_msa_receipt_reports(repo_root: Path, *, task_id: str | None, evidence: dict[str, Any]) -> dict[str, Any]:
    slug = safe_trace_slug(task_id or "task")
    report_root = repo_root / ".nexus" / "reports"
    updated = dict(evidence)

    swarm_report = dict(updated.get("swarm_report") or {})
    if updated.get("swarm_used") and int(swarm_report.get("evidence_count", 0) or 0) > 0:
        path = report_root / "swarm" / f"{slug}_receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        swarm_report["report_path"] = str(path)
        path.write_text(json.dumps(swarm_report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        updated["swarm_report"] = swarm_report
        updated["swarm_report_path"] = str(path)

    drone_report = dict(updated.get("drone_report") or {})
    if int(drone_report.get("artifact_count", 0) or 0) > 0:
        path = report_root / "drone" / f"{slug}_receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        drone_report["report_path"] = str(path)
        path.write_text(json.dumps(drone_report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        updated["drone_report"] = drone_report
        updated["drone_report_path"] = str(path)

    nightshift_report = dict(updated.get("nightshift_report") or {})
    if nightshift_report.get("invoked") and nightshift_report.get("recovered"):
        path = report_root / "nightshift" / f"{slug}_receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        nightshift_report["report_path"] = str(path)
        updated["nightshift_report_path"] = str(path)
        updated["nightshift_report"] = nightshift_report
        path.write_text(json.dumps(nightshift_report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return updated


def infer_research_role(*, task_desc: str, task_type: str, route_features: dict[str, Any]) -> str:
    task_lower = f"{task_body_only(task_desc)} {task_type}".lower()
    if bool(route_features.get("benchmark_hidden_contract_fast_path", False)):
        return "general"
    if any(token in task_lower for token in ("benchmark", "latency", "throughput", "public report", "solve rate", "p99")):
        return "benchmark_framer"
    if bool(route_features.get("claim_uncertainty", False)) or any(
        token in task_lower
        for token in ("api", "sdk", "parameter", "flag", "call site", "request header", "response schema")
    ):
        return "claim_scout"
    if bool(route_features.get("plateau_detected", False)) or bool(route_features.get("is_cross_module_task", False)):
        return "architecture_scout"
    if int(route_features.get("memory_hits", 0) or 0) > 0 or int(route_features.get("findings_hits", 0) or 0) > 0:
        return "failure_historian"
    return "general"


_CLAIM_GENERIC_TOKENS = {
    "api",
    "sdk",
    "parameter",
    "flag",
    "contract",
    "claim",
    "verify",
    "evidence",
    "before",
    "editing",
    "call",
    "site",
    "supports",
}


def doc_scout_supports_specific_claim(*, task_desc: str, doc_scout: dict[str, Any]) -> bool:
    hits = doc_scout.get("hits", []) if isinstance(doc_scout.get("hits"), list) else []
    if not hits:
        return False
    specific_tokens = [
        token
        for token in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{3,}", task_desc.lower())
        if token not in _CLAIM_GENERIC_TOKENS
    ][:4]
    if not specific_tokens:
        return True
    evidence_text = " ".join(
        f"{item.get('snippet', '')} {item.get('path', '')}"
        for item in hits
        if isinstance(item, dict)
    ).lower()
    return all(token in evidence_text for token in specific_tokens)


def build_research_context(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    route_features: dict[str, Any],
    historical_hints: list[str],
) -> dict[str, Any]:
    external_providers = build_external_scout_providers_from_env()
    include_external = bool(external_providers)
    doc_scout = DocScoutAdapter(repo_root, external_providers=external_providers).search(
        task_desc,
        limit=4,
        include_external=include_external,
    )
    doc_hits = int(doc_scout.get("hits_count", 0) or 0)
    task_lower = f"{task_body_only(task_desc)} {task_type}".lower()
    claim_like_task = any(
        token in task_lower
        for token in (
            "api",
            "sdk",
            "parameter",
            "flag",
            "call site",
            "request header",
            "response schema",
        )
    )
    doc_supports_claim = doc_scout_supports_specific_claim(task_desc=task_desc, doc_scout=doc_scout)
    claim_uncertainty = bool(
        claim_like_task
        and int(doc_scout.get("verified_source_count", 0) or 0) == 0
        and not doc_supports_claim
    )
    benchmark_required = bool(
        task_type.startswith("public_")
        or any(token in task_lower for token in ("benchmark", "latency", "throughput", "public report", "solve rate", "p99"))
    )
    enriched_features = dict(route_features)
    enriched_features["claim_uncertainty"] = claim_uncertainty
    enriched_features["benchmark_required"] = benchmark_required
    enriched_features["plateau_detected"] = bool(route_features.get("plateau_detected", False))
    enriched_features["doc_scout_hits"] = doc_hits
    role = infer_research_role(task_desc=task_desc, task_type=task_type, route_features=enriched_features)

    verified_claims = [
        {
            "claim": str(item.get("snippet", "") or ""),
            "evidence_refs": [str(item.get("path", "") or "")],
            "source": str(item.get("source", "") or ""),
        }
        for item in (doc_scout.get("hits", []) or [])[:2]
        if str(item.get("snippet", "") or "").strip()
    ]
    rejected_claims = []
    blocked_assumptions: list[str] = []
    constraint_store = ASIConstraintStore(repo_root)
    global_constraints = constraint_store.match(task_desc, limit=4)
    constraint_lookup_receipt = constraint_store.lookup_receipt(
        task_desc,
        matches=global_constraints,
        limit=4,
    )
    if claim_uncertainty:
        blocked_assumptions.append("api_contract_not_verified")
        rejected_claims.append(
            {
                "claim": "unverified_api_contract",
                "reason": "doc_scout_no_specific_support",
            }
        )
    for constraint in global_constraints:
        blocked = str(constraint.get("blocked_pattern") or "").strip()
        if blocked and blocked not in blocked_assumptions:
            blocked_assumptions.append(blocked)
            rejected_claims.append(
                {
                    "claim": f"reuse_blocked_pattern:{blocked}",
                    "reason": str(constraint.get("failure_signature") or "global_asi_constraint_match"),
                }
            )
    if bool(enriched_features.get("plateau_detected", False)):
        blocked_assumptions.append("local_micro_tuning_is_enough")
        rejected_claims.append(
            {
                "claim": "continue_same_family_patching",
                "reason": "plateau_detected",
            }
        )

    recommended_capabilities: list[str] = []
    if role in {"claim_scout", "architecture_scout"}:
        recommended_capabilities.extend(["research", "codeintel"])
    if role == "failure_historian":
        recommended_capabilities.extend(["autoreason", "research"])
    if role == "benchmark_framer":
        recommended_capabilities.extend(["benchmark", "acceptance_check"])
    if claim_uncertainty:
        recommended_capabilities.append("research")
    if bool(enriched_features.get("plateau_detected", False)):
        recommended_capabilities.extend(["research", "ultra_review"])
    recommended_capabilities = list(dict.fromkeys(recommended_capabilities))

    next_action_hint = historical_hints[0] if historical_hints else ""
    if bool(enriched_features.get("plateau_detected", False)):
        next_action_hint = "switch_to_architecture_scout_and_change_family"
    elif claim_uncertainty:
        next_action_hint = "verify_contract_before_editing"

    confidence = float(doc_scout.get("confidence", 0.0) or 0.0)
    if int(enriched_features.get("memory_hits", 0) or 0) > 0:
        confidence = max(confidence, 0.55)

    return {
        "schema": "nexus_research_context_v1",
        "role": role,
        "hypothesis": task_desc,
        "verified_claims": verified_claims,
        "rejected_claims": rejected_claims,
        "retrieval_refs": list(doc_scout.get("retrieval_hints", []) or []) + list(historical_hints or []),
        "risk_flags": [
            flag
            for flag, enabled in {
                "claim_uncertainty": claim_uncertainty,
                "plateau_detected": bool(enriched_features.get("plateau_detected", False)),
                "high_risk": int(enriched_features.get("risk_score", 0) or 0) >= 70,
            }.items()
            if enabled
        ],
        "recommended_capabilities": recommended_capabilities,
        "blocked_assumptions": blocked_assumptions,
        "global_constraints": global_constraints,
        "constraint_lookup_receipt": constraint_lookup_receipt,
        "next_action_hint": next_action_hint,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "doc_scout": doc_scout,
    }


_write_msa_receipt_reports = write_msa_receipt_reports
_infer_research_role = infer_research_role
_doc_scout_supports_specific_claim = doc_scout_supports_specific_claim
_build_research_context = build_research_context
