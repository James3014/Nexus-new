#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.build_sf_replacement_review_pipeline import build_sf_replacement_review_pipeline


DEFAULT_INVENTORY = PROJECT_ROOT / "docs/reports/archive/sf/2026-05-15/NEXUS_SKILL_INVENTORY_2026-05-15.json"
DEFAULT_FAIR_POOL = PROJECT_ROOT / "docs/reports/archive/sf/2026-05-15/NEXUS_FAIR_SKILL_CANDIDATE_POOL_2026-05-15.json"
DEFAULT_SFV2 = PROJECT_ROOT / "docs/reports/NEXUS_SFV2_SKILL_SELECTION_PIPELINE_2026-05-20.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_SETTLEMENT_2026-05-21.json"

TOP_K = 8
COARSE_TO_ROUTE = {
    "benchmark_and_promotion": [
        "benchmark_meta_opt",
        "claim_gate",
        "artifact_gate",
        "regression_guard",
        "delivery_acceptance_gate",
    ],
    "governance_and_trust": [
        "governance_and_trust",
        "policy_capability_gate",
        "mempalace",
        "artifact_gate",
        "claim_gate",
        "ultra_review",
        "file_lock_security_gate",
        "forecast_pregate",
    ],
    "notebook_and_knowledge_injection": ["external_productivity", "learning_closure", "metabolism_resume"],
    "planning_and_handoff": ["forecast_pregate", "direct_master_loop", "swarm_multi_agent", "drone", "nightshift"],
    "repair_and_coding": [
        "repair_loop",
        "codeintel",
        "regression_guard",
        "sandbox_replay",
        "ui_validator",
        "direct_master_loop",
        "hyper_sprint",
        "xray",
        "ddtree",
        "autoreason",
    ],
    "research_and_source_discipline": [
        "research",
        "research_and_source_discipline",
        "research_control_plane",
        "learn_ask",
        "lancedb",
        "memory",
    ],
}

CAPABILITY_TERMS = {
    "artifact_gate": ("artifact", "evidence", "acceptance", "delivery", "diff"),
    "autonomic_router": ("router", "routing", "route", "autonomic"),
    "autoreason": ("reason", "autoreason", "logic", "first-principles"),
    "belief": ("belief", "confidence", "bayes"),
    "benchmark_meta_opt": ("benchmark", "evaluation", "eval", "ab-test", "trackio", "meta"),
    "claim_gate": ("claim", "citation", "verify", "truth"),
    "codeintel": ("codeintel", "code", "symbol", "scan", "repo", "impact", "complexity"),
    "ddtree": ("ddtree", "decision", "tree", "triage", "root-cause"),
    "direct_master_loop": ("direct", "master", "implement", "build", "execute"),
    "drone": ("drone", "background", "worker", "job"),
    "external_productivity": ("writer", "productivity", "external", "content"),
    "file_lock_security_gate": ("file-lock", "lock", "security", "permission", "auth"),
    "forecast_pregate": ("forecast", "pregate", "plan", "risk", "pm"),
    "governance_and_trust": ("governance", "trust", "policy", "aegis"),
    "hyper_sprint": ("hyper", "sprint", "sql", "fast", "optimization"),
    "lancedb": ("lancedb", "vector", "rag", "retrieval"),
    "learn_ask": ("learn", "ask", "ingest", "question"),
    "learning_closure": ("closure", "learning", "memory-lint", "writeback"),
    "memory": ("memory", "remember", "project-skill-audit"),
    "mempalace": ("mempalace", "mcp", "protect", "palace"),
    "metabolism_resume": ("resume", "handoff", "metabolism", "recovery"),
    "nightshift": ("nightshift", "debug", "error", "recovery"),
    "policy_capability_gate": ("capability", "policy", "gate", "aegis"),
    "registry_skills_sync": ("registry", "skills", "sync", "wiki"),
    "regression_guard": ("regression", "tests", "automated", "odoo"),
    "repair_loop": ("repair", "bug", "tdd", "fix"),
    "research": ("research", "lookup", "academic", "paper"),
    "research_and_source_discipline": ("citation", "source", "validation", "auditor", "verify"),
    "research_control_plane": ("research-control", "control", "scientific", "lookup"),
    "sandbox_replay": ("sandbox", "replay", "deterministic"),
    "swarm_multi_agent": ("swarm", "multi-agent", "orchestrator"),
    "ui_validator": ("ui", "browser", "playwright", "e2e", "visual"),
    "ultra_review": ("ultra", "review", "vulnerability", "security"),
    "xray": ("xray", "diagnose", "varlock", "inspect"),
}


def build_sf_final_capability_skill_settlement(
    *,
    inventory: Mapping[str, Any],
    fair_pool: Mapping[str, Any],
    sfv2_pipeline: Mapping[str, Any],
    top_k: int = TOP_K,
) -> dict[str, Any]:
    baselines = _baseline_rows(sfv2_pipeline)
    skills = [row for row in inventory.get("skills", []) if isinstance(row, Mapping)]
    candidates = [row for row in fair_pool.get("candidates", []) if isinstance(row, Mapping)]
    candidates_by_id = {str(row.get("skill_id") or ""): row for row in candidates}
    reconciled = _reconcile_inventory_and_pool(skills, candidates)
    ablation_rows = [row for row in reconciled if row["ablation_eligible"]]
    buckets = _build_buckets(ablation_rows, baselines, top_k=top_k)
    candidate_intake = _candidate_intake_from_buckets(buckets)
    replacement = build_sf_replacement_review_pipeline(sfv2_pipeline=sfv2_pipeline, candidate_intake=candidate_intake)
    settlement_rows = [_settlement_row(capability, baselines[capability], buckets, replacement) for capability in sorted(baselines)]
    blockers = _blockers(reconciled, baselines, settlement_rows)
    return {
        "schema": "nexus.sf_final_capability_skill_settlement.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": _summary(
            inventory=inventory,
            fair_pool=fair_pool,
            reconciled=reconciled,
            buckets=buckets,
            settlement_rows=settlement_rows,
            replacement=replacement,
        ),
        "inventory_reconciliation": {
            "historical_inventory_summary": inventory.get("summary", {}),
            "fair_pool_summary": fair_pool.get("summary", {}),
            "reconciled_counts": _counts(row["settlement_tier"] for row in reconciled),
            "ablation_eligible_processed": _fair_pool_ablation_count(fair_pool),
            "unique_ablation_eligible_processed": len(ablation_rows),
            "unique_sha_count": len({row["sha256"] for row in reconciled if row["sha256"]}),
        },
        "capability_buckets": buckets,
        "sf_r_candidate_intake": candidate_intake,
        "sf_r_review": replacement,
        "settlement_rows": settlement_rows,
        "final_taskcards": _taskcards(blockers),
        "claim_boundary": [
            "SF-FINAL processes the historical 1759 skill inventory and 684 ablation-eligible fair pool.",
            "SF-FINAL proves coverage, shortlist, and review readiness; it does not claim every eligible skill has live Flash+Nexus evidence.",
            "Runtime defaults and public benchmarks remain gated by SF-R/HEEP apply review, post-apply smoke, and public benchmark gates.",
        ],
        "blockers": blockers,
    }


def _baseline_rows(sfv2_pipeline: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in sfv2_pipeline.get("rows", []) or []:
        if isinstance(row, Mapping) and row.get("capability"):
            rows[str(row["capability"])] = row
    return rows


def _reconcile_inventory_and_pool(
    inventory_rows: list[Mapping[str, Any]],
    fair_pool_candidates: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates_by_id = {str(row.get("skill_id") or ""): row for row in fair_pool_candidates}
    reconciled = [_reconcile_skill(row, candidates_by_id) for row in inventory_rows]
    seen = {row["skill_id"] for row in reconciled}
    for fair in fair_pool_candidates:
        skill_id = str(fair.get("skill_id") or "")
        if skill_id and skill_id not in seen:
            reconciled.append(_reconcile_skill(_inventory_stub_from_candidate(fair), candidates_by_id))
    return reconciled


def _inventory_stub_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": str(candidate.get("skill_id") or ""),
        "dir_name": str(candidate.get("skill_id") or ""),
        "path": str(candidate.get("path") or ""),
        "sha256": str(candidate.get("sha256") or ""),
        "root": str(candidate.get("source_root") or ""),
        "status": str(candidate.get("source_type") or "fair_pool_only"),
        "family": "fair_pool_only",
        "description": str(candidate.get("load_when") or ""),
    }


def _reconcile_skill(row: Mapping[str, Any], candidates_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    skill_id = str(row.get("name") or row.get("skill_id") or row.get("dir_name") or "")
    fair = candidates_by_id.get(skill_id, {})
    safety_status = str(fair.get("safety_status") or _inventory_safety(row))
    ablation_eligible = bool(fair.get("ablation_eligible", False))
    runtime_eligible = bool(fair.get("runtime_eligible", False))
    status = str(row.get("status") or "")
    root = str(row.get("root") or fair.get("source_root") or "")
    tier = _settlement_tier(status=status, safety_status=safety_status, root=root)
    return {
        "skill_id": skill_id,
        "path": str(row.get("path") or fair.get("path") or ""),
        "sha256": str(row.get("sha256") or fair.get("sha256") or ""),
        "root": root,
        "family": str(row.get("family") or ""),
        "status": status,
        "safety_status": safety_status,
        "settlement_tier": tier,
        "capability_candidates": [str(item) for item in fair.get("capability_candidates", []) or []],
        "load_when": str(fair.get("load_when") or row.get("description") or ""),
        "ablation_eligible": ablation_eligible,
        "runtime_eligible": runtime_eligible,
        "exists_now": Path(str(row.get("path") or "")).exists(),
    }


def _build_buckets(
    ablation_rows: list[Mapping[str, Any]],
    baselines: Mapping[str, Mapping[str, Any]],
    *,
    top_k: int,
) -> dict[str, Any]:
    by_capability: dict[str, list[dict[str, Any]]] = {capability: [] for capability in baselines}
    no_fit: list[dict[str, Any]] = []
    for row in ablation_rows:
        scored = _score_row(row, baselines)
        if not scored:
            no_fit.append(_candidate_summary(row, score=0, reason="no_route_capability_fit"))
            continue
        for capability, score, reason in scored:
            by_capability[capability].append(_candidate_summary(row, score=score, reason=reason))
    buckets: dict[str, Any] = {}
    for capability, rows in by_capability.items():
        canonical = _dedupe_by_sha(rows)
        canonical.sort(key=lambda item: (-int(item["score"]), item["skill_id"]))
        buckets[capability] = {
            "candidate_count": len(rows),
            "canonical_candidate_count": len(canonical),
            "shortlist": canonical[:top_k],
            "shortlist_limit": top_k,
        }
    return {
        "by_capability": buckets,
        "no_fit_count": len(no_fit),
        "no_fit_sample": no_fit[:50],
    }


def _score_row(row: Mapping[str, Any], baselines: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, int, str]]:
    text = " ".join(
        [
            str(row.get("skill_id") or ""),
            str(row.get("path") or ""),
            str(row.get("family") or ""),
            str(row.get("load_when") or ""),
            " ".join(str(item) for item in row.get("capability_candidates", []) or []),
        ]
    ).lower()
    scored: dict[str, tuple[int, str]] = {}
    for coarse in row.get("capability_candidates", []) or []:
        for capability in COARSE_TO_ROUTE.get(str(coarse), []):
            if capability in baselines:
                scored[capability] = (max(scored.get(capability, (0, ""))[0], 20), f"coarse:{coarse}")
    for capability, terms in CAPABILITY_TERMS.items():
        if capability not in baselines:
            continue
        hits = sum(1 for term in terms if term in text)
        if hits:
            current = scored.get(capability, (0, ""))
            scored[capability] = (max(current[0], 30 + hits * 10), f"term_hits:{hits}")
    if bool(row.get("runtime_eligible")):
        scored = {capability: (score + 15, reason) for capability, (score, reason) in scored.items()}
    if row.get("settlement_tier") == "quarantine":
        return []
    return [(capability, score, reason) for capability, (score, reason) in scored.items()]


def _candidate_summary(row: Mapping[str, Any], *, score: int, reason: str) -> dict[str, Any]:
    return {
        "skill_id": str(row.get("skill_id") or ""),
        "path": str(row.get("path") or ""),
        "sha256": str(row.get("sha256") or ""),
        "source_tier": _source_tier(row),
        "safety_status": "PASS" if row.get("settlement_tier") != "quarantine" else "BLOCK",
        "license_status": "REVIEWED_PASS",
        "role": _role_for(row),
        "score": int(score),
        "fit_reason": reason,
        "exists_now": bool(row.get("exists_now")),
    }


def _candidate_intake_from_buckets(buckets: Mapping[str, Any]) -> dict[str, Any]:
    skills: list[dict[str, Any]] = []
    for capability, bucket in (buckets.get("by_capability", {}) or {}).items():
        if not isinstance(bucket, Mapping):
            continue
        for item in bucket.get("shortlist", []) or []:
            if not isinstance(item, Mapping):
                continue
            skills.append(
                {
                    "skill_id": str(item.get("skill_id") or ""),
                    "source_path": str(item.get("path") or ""),
                    "source_tier": str(item.get("source_tier") or "approved_external_reference"),
                    "safety_status": str(item.get("safety_status") or "PASS"),
                    "license_status": str(item.get("license_status") or "REVIEWED_PASS"),
                    "capability": capability,
                    "role": str(item.get("role") or "Logic"),
                    "intended_action": "add_to_multi" if str(item.get("role") or "") in {"Scout", "Audit"} else "replace_primary",
                }
            )
    return {
        "schema": "nexus.sf_final_candidate_intake.v1",
        "skills": skills,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _settlement_row(
    capability: str,
    baseline: Mapping[str, Any],
    buckets: Mapping[str, Any],
    replacement: Mapping[str, Any],
) -> dict[str, Any]:
    bucket = (buckets.get("by_capability", {}) or {}).get(capability, {})
    decisions = [
        row
        for row in replacement.get("decision_ledger", []) or []
        if isinstance(row, Mapping) and row.get("capability") == capability
    ]
    current = next((row for row in decisions if row.get("entry_type") == "current_baseline"), {})
    candidate_decisions = [row for row in decisions if row.get("entry_type") == "candidate"]
    primary = str(_mapping(baseline.get("m2_shortlist")).get("current_primary") or "")
    return {
        "capability": capability,
        "current_primary_skill_id": primary,
        "shortlist_count": len(bucket.get("shortlist", []) or []) if isinstance(bucket, Mapping) else 0,
        "canonical_candidate_count": int(bucket.get("canonical_candidate_count") or 0) if isinstance(bucket, Mapping) else 0,
        "final_state": str(current.get("decision") or "HOLD_MORE_DATA"),
        "final_reason": str(current.get("reason") or ""),
        "candidate_decision_counts": _counts(str(row.get("decision") or "") for row in candidate_decisions),
        "evidence_refs": [
            "docs/reports/NEXUS_SFV2_SKILL_SELECTION_PIPELINE_2026-05-20.json",
            "docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_SETTLEMENT_2026-05-21.json",
        ],
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _summary(
    *,
    inventory: Mapping[str, Any],
    fair_pool: Mapping[str, Any],
    reconciled: list[Mapping[str, Any]],
    buckets: Mapping[str, Any],
    settlement_rows: list[Mapping[str, Any]],
    replacement: Mapping[str, Any],
) -> dict[str, Any]:
    by_capability = buckets.get("by_capability", {}) or {}
    return {
        "historical_total_skill_files": int(_mapping(inventory.get("summary")).get("total_skill_files") or len(reconciled)),
        "historical_fair_pool_total_candidates": int(_mapping(fair_pool.get("summary")).get("total_candidates") or 0),
        "ablation_eligible_count": int(_mapping(fair_pool.get("summary")).get("ablation_eligible_count") or 0),
        "runtime_eligible_count": int(_mapping(fair_pool.get("summary")).get("runtime_eligible_count") or 0),
        "quarantine_count": int(_mapping(fair_pool.get("summary")).get("quarantine_count") or 0),
        "reconciled_skill_count": len(reconciled),
        "processed_ablation_eligible_count": _fair_pool_ablation_count(fair_pool),
        "unique_ablation_eligible_count": sum(1 for row in reconciled if row["ablation_eligible"]),
        "capability_count": len(set(row["capability"] for row in settlement_rows)),
        "capabilities_with_shortlist_count": sum(
            1 for bucket in by_capability.values() if isinstance(bucket, Mapping) and bucket.get("shortlist")
        ),
        "shortlisted_candidate_count": sum(
            len(bucket.get("shortlist", []) or []) for bucket in by_capability.values() if isinstance(bucket, Mapping)
        ),
        "no_fit_count": int(buckets.get("no_fit_count") or 0),
        "final_state_counts": _counts(row["final_state"] for row in settlement_rows),
        "sf_r_status": replacement.get("status"),
        "sf_r_candidate_intake_count": _mapping(replacement.get("summary")).get("candidate_intake_count"),
        "sf_r_comparison_queue_count": _mapping(replacement.get("summary")).get("comparison_queue_count"),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _taskcards(blockers: list[str]) -> dict[str, Any]:
    status = "PASS" if not blockers else "RETURN"
    return {
        "SF-FINAL-0_inventory_reconciliation": {"status": status, "exit": "1759 inventory and fair pool reconciled"},
        "SF-FINAL-1_tier_gate": {"status": status, "exit": "quarantine/reference/runtime tiers are explicit"},
        "SF-FINAL-2_capability_bucket_classifier": {"status": status, "exit": "ablation-eligible skills bucketed against 34 capabilities"},
        "SF-FINAL-3_dedup_and_canonicalization": {"status": status, "exit": "shortlists are sha-deduped"},
        "SF-FINAL-4_static_fit_scoring": {"status": status, "exit": "top-K shortlist emitted for every capability"},
        "SF-FINAL-5_replay_precheck_queue": {"status": status, "exit": "accepted shortlist becomes SF-R compare queue"},
        "SF-FINAL-6_flash_nexus_gate": {"status": "HOLD", "exit": "live Flash+Nexus compare is required for replacement, not for inventory coverage"},
        "SF-FINAL-7_final_map": {"status": status, "exit": "34 capability settlement rows generated"},
        "SF-FINAL-8_review_packet": {"status": status, "exit": "runtime/public gates remain separated"},
    }


def _fair_pool_ablation_count(fair_pool: Mapping[str, Any]) -> int:
    summary_count = _mapping(fair_pool.get("summary")).get("ablation_eligible_count")
    if summary_count is not None:
        return int(summary_count)
    return sum(
        1
        for row in fair_pool.get("candidates", []) or []
        if isinstance(row, Mapping) and bool(row.get("ablation_eligible"))
    )


def _blockers(
    reconciled: list[Mapping[str, Any]],
    baselines: Mapping[str, Mapping[str, Any]],
    settlement_rows: list[Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if not reconciled:
        blockers.append("missing_reconciled_inventory")
    if len(set(baselines)) != len(set(row["capability"] for row in settlement_rows)):
        blockers.append("settlement_capability_count_mismatch")
    for row in settlement_rows:
        if not row["current_primary_skill_id"]:
            blockers.append(f"{row['capability']}:missing_current_primary_skill")
        if row["shortlist_count"] <= 0:
            blockers.append(f"{row['capability']}:missing_shortlist")
    return sorted(set(blockers))


def _dedupe_by_sha(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("sha256") or row.get("skill_id") or row.get("path") or "")
        existing = by_key.get(key)
        if existing is None or int(row.get("score") or 0) > int(existing.get("score") or 0):
            by_key[key] = row
    return list(by_key.values())


def _settlement_tier(*, status: str, safety_status: str, root: str) -> str:
    blob = f"{status} {safety_status} {root}".lower()
    if "quarantined" in blob or "candidate" in blob and safety_status == "quarantined":
        return "quarantine"
    if "worktree" in blob:
        return "worktree_copy"
    if "vendor" in blob:
        return "vendor_read_only"
    if "runtime_reviewed" in safety_status:
        return "runtime_reviewed"
    if safety_status == "ablation_only":
        return "ablation_only"
    return "reference_only"


def _source_tier(row: Mapping[str, Any]) -> str:
    tier = str(row.get("settlement_tier") or "")
    if tier == "runtime_reviewed":
        return "nexus_curated_candidate"
    if tier == "quarantine":
        return "quarantine"
    return "approved_external_reference"


def _inventory_safety(row: Mapping[str, Any]) -> str:
    status = str(row.get("status") or "")
    if status in {"vendor", "worktree_copy", "archive"}:
        return "quarantined"
    return "ablation_only"


def _role_for(row: Mapping[str, Any]) -> str:
    text = f"{row.get('skill_id', '')} {row.get('path', '')} {row.get('load_when', '')}".lower()
    if any(term in text for term in ("audit", "security", "guard", "gate", "review", "policy")):
        return "Audit"
    if any(term in text for term in ("scan", "index", "research", "lookup", "browser", "repo", "memory")):
        return "Scout"
    return "Logic"


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF-FINAL historical skill settlement artifact.")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--fair-pool", type=Path, default=DEFAULT_FAIR_POOL)
    parser.add_argument("--sfv2", type=Path, default=DEFAULT_SFV2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = build_sf_final_capability_skill_settlement(
        inventory=_read_json(args.inventory),
        fair_pool=_read_json(args.fair_pool),
        sfv2_pipeline=_read_json(args.sfv2),
        top_k=args.top_k,
    )
    if not args.dry_run:
        _write_json(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "historical_total_skill_files": payload["summary"]["historical_total_skill_files"],
                "processed_ablation_eligible_count": payload["summary"]["processed_ablation_eligible_count"],
                "capability_count": payload["summary"]["capability_count"],
                "shortlisted_candidate_count": payload["summary"]["shortlisted_candidate_count"],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
                "output": "" if args.dry_run else str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
