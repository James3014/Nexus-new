"""Follow-up RCA and candidate-pool contracts for skill-fit discovery."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

RESEARCH_CANDIDATE_V2_STRONG_SIGNALS = (
    "citation",
    "citations",
    "source",
    "sources",
    "source validation",
    "evidence",
    "raw source",
    "raw sources",
    "methodology",
    "replication",
    "conflict",
    "research",
    "retrieval",
    "synthesis",
    "semantic",
    "academic",
    "canonical tracker",
    "structured data",
    "perplexity",
)
RESEARCH_CANDIDATE_V2_PLATFORM_ONLY_SIGNALS = (
    "browserbase",
    "company",
    "sales",
    "icp",
    "deploy",
    "browser automation",
    "cookie",
    "event prospecting",
    "cli",
    "functions",
)
RESEARCH_CANDIDATE_V3_BEHAVIOR_GROUPS = {
    "citation_chain": (
        "citation chain",
        "citation-chain",
        "citation",
        "citations",
        "source refs",
        "source references",
        "references",
    ),
    "source_conflict": (
        "source conflict",
        "source-conflict",
        "conflicting sources",
        "conflict",
        "contradiction",
        "disagreement",
    ),
    "source_validation": (
        "source validation",
        "source-validation",
        "validate sources",
        "verify sources",
        "source verification",
        "raw source",
        "raw sources",
        "provenance",
    ),
}
RESEARCH_CANDIDATE_V3_GENERIC_SIGNALS = (
    "general research",
    "search the web",
    "browser automation",
    "company research",
    "sales",
    "icp",
    "blog",
    "seo",
    "summary",
    "summarize",
)
GOVERNANCE_CANDIDATE_V2_STRONG_SIGNALS = (
    "governance",
    "trust",
    "evidence",
    "claim",
    "audit",
    "policy",
    "fail-closed",
    "fail closed",
    "redaction",
    "secret",
    "authorization",
    "boundary",
    "scope",
    "risk",
    "security",
    "hardening",
    "root cause",
    "incident",
    "postincident",
)
GOVERNANCE_CANDIDATE_V2_PLATFORM_ONLY_SIGNALS = (
    "image",
    "creative",
    "browserbase",
    "company",
    "sales",
    "seo",
    "canvas",
    "airtable",
    "notebooklm",
)
GOVERNANCE_TASKSET_BUCKETS = {
    "audit": (
        "audit",
        "review",
        "ultra",
        "consensus",
        "finding",
    ),
    "claim_gate": (
        "claim",
        "receipt",
        "replay",
        "supported",
        "verified claims",
    ),
    "redaction": (
        "redaction",
        "credential",
        "secret",
        "scrubber",
    ),
    "auth": (
        "authorization",
        "deny",
        "scope",
        "allowed",
        "unsafe",
        "read-only",
        "operation",
    ),
    "evidence_review": (
        "evidence",
        "artifact",
        "source",
        "path",
        "report",
    ),
}


@dataclass(frozen=True)
class SkillFitRowIndex:
    """Pre-index skill-fit rows for RCA/cost contracts without policy decisions."""

    capability: str
    rows: tuple[Mapping[str, Any], ...]
    baseline_by_task: Mapping[str, Mapping[str, Any]]
    rows_by_skill: Mapping[str, tuple[Mapping[str, Any], ...]]
    catalog_by_skill: Mapping[str, Mapping[str, Any]]

    @classmethod
    def from_run_summary(
        cls,
        run_summary: Mapping[str, Any],
        catalog: Mapping[str, Any] | None = None,
        *,
        capability: str = "",
    ) -> "SkillFitRowIndex":
        results = tuple(row for row in run_summary.get("results", []) or [] if isinstance(row, Mapping))
        target_capability = capability or _first_catalog_capability(catalog) or str(run_summary.get("capability") or "")
        rows = tuple(
            row for row in results if not target_capability or str(row.get("capability") or "") == target_capability
        )
        baseline_by_task = {
            _row_task_key(row): row
            for row in rows
            if str(row.get("arm_type") or "") == "capability_only" and _row_task_key(row)
        }
        rows_by_skill: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            if str(row.get("arm_type") or "") != "skill_ablation":
                continue
            skill_id = str(row.get("skill_id") or "")
            if skill_id:
                rows_by_skill.setdefault(skill_id, []).append(row)
        catalog_by_skill = {
            str(item.get("skill_id") or ""): item
            for item in (catalog or {}).get("skill_verdicts", []) or []
            if isinstance(item, Mapping)
        }
        return cls(
            capability=target_capability,
            rows=rows,
            baseline_by_task=baseline_by_task,
            rows_by_skill={skill_id: tuple(skill_rows) for skill_id, skill_rows in sorted(rows_by_skill.items())},
            catalog_by_skill=dict(sorted(catalog_by_skill.items())),
        )

    @property
    def skill_ids(self) -> tuple[str, ...]:
        return tuple(self.rows_by_skill.keys())


def build_skill_fit_row_level_rca(
    run_summary: Mapping[str, Any],
    catalog: Mapping[str, Any] | None = None,
    *,
    capability: str = "",
    alternate_min_effective_rate: float = 0.6,
    promising_min_effective_rate: float = 0.4,
) -> dict[str, Any]:
    """Explain skill-fit outcomes at row granularity without changing promotion state."""

    row_index = SkillFitRowIndex.from_run_summary(run_summary, catalog, capability=capability)
    capability_results = row_index.rows
    baseline_by_task = row_index.baseline_by_task
    catalog_by_skill = row_index.catalog_by_skill

    skill_analyses = []
    for skill_id, rows in row_index.rows_by_skill.items():
        effective_rows = [_is_effective_skill_row(row) for row in rows]
        effective_count = sum(1 for item in effective_rows if item)
        tested_rows = len(rows)
        effective_rate = (effective_count / tested_rows) if tested_rows else 0.0
        verdict = str(catalog_by_skill.get(skill_id, {}).get("verdict") or "")
        bucket_counts: Counter[str] = Counter()
        effective_bucket_counts: Counter[str] = Counter()
        row_records = []
        for row, effective in zip(rows, effective_rows, strict=False):
            bucket = _catalog_task_bucket(row)
            if bucket:
                bucket_counts[bucket] += 1
                if effective:
                    effective_bucket_counts[bucket] += 1
            task_key = _row_task_key(row)
            baseline = baseline_by_task.get(task_key, {})
            gate_row = row.get("ablation_gate_row") if isinstance(row.get("ablation_gate_row"), Mapping) else {}
            row_records.append(
                {
                    "row_id": str(row.get("row_id") or ""),
                    "task_key": task_key,
                    "task_ref": row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {},
                    "task_bucket": bucket,
                    "baseline_status": str(baseline.get("status") or ""),
                    "skill_status": str(row.get("status") or ""),
                    "gate_status": _gate_status(row),
                    "gate_row_status": str(gate_row.get("status") or ""),
                    "effective": effective,
                    "missing_effective_fields": list(gate_row.get("missing_effective_fields", []) or []),
                    "trust_mismatch": bool(gate_row.get("trust_mismatch")),
                    "evidence_path": str(gate_row.get("evidence_path") or ""),
                    "receipt_path": str(gate_row.get("receipt_path") or ""),
                }
            )
        recommendation = "reject_or_replace_candidate"
        if verdict == "needs_more_data" and effective_rate >= alternate_min_effective_rate:
            recommendation = "eligible_for_threshold_review"
        elif verdict == "needs_more_data" and effective_rate >= promising_min_effective_rate:
            recommendation = "targeted_replay"
        elif verdict == "needs_more_data" and effective_count > 0:
            recommendation = "candidate_pool_v2_or_taskset_expansion"
        elif verdict == "reject":
            recommendation = "skip_until_candidate_or_taskset_changes"
        skill_analyses.append(
            {
                "skill_id": skill_id,
                "verdict": verdict,
                "tested_rows": tested_rows,
                "effective_rows": effective_count,
                "effective_rate": round(effective_rate, 4),
                "task_bucket_counts": dict(sorted(bucket_counts.items())),
                "effective_task_bucket_counts": dict(sorted(effective_bucket_counts.items())),
                "recommendation": recommendation,
                "targeted_replay_row_ids": [
                    record["row_id"]
                    for record in row_records
                    if recommendation in {"targeted_replay", "eligible_for_threshold_review"}
                ],
                "rows": row_records,
            }
        )

    ready_count = sum(1 for item in skill_analyses if item["recommendation"] == "eligible_for_threshold_review")
    targeted_count = sum(1 for item in skill_analyses if item["recommendation"] == "targeted_replay")
    return {
        "schema": "nexus.skill_fit_row_level_rca.v1",
        "status": "PASS" if capability_results else "RETURN",
        "capability": row_index.capability,
        "summary": {
            "row_count": len(capability_results),
            "baseline_task_count": len(baseline_by_task),
            "skill_count": len(skill_analyses),
            "eligible_for_threshold_review_count": ready_count,
            "targeted_replay_count": targeted_count,
            "runtime_update_allowed": False,
            "flash100_allowed": False,
        },
        "root_cause": "skill_outcome_contribution_below_threshold"
        if skill_analyses and ready_count == 0
        else "threshold_review_required",
        "skill_analyses": skill_analyses,
        "claim_boundary": [
            "Row-level RCA explains discovery evidence; it does not promote runtime defaults.",
            "Targeted replay is allowed only for receipt-backed needs_more_data skills.",
            "Flash100 remains blocked until a threshold contract reports alternate/default readiness.",
        ],
    }


def build_research_candidate_v2_report(
    candidate_pool: Mapping[str, Any],
    previous_catalog: Mapping[str, Any],
    *,
    capability: str = "research_and_source_discipline",
    max_candidates: int = 4,
) -> dict[str, Any]:
    """Select a safer research/source-discipline candidate v2 pool from audited candidates."""

    rejected = {
        str(item.get("skill_id") or "")
        for item in previous_catalog.get("skill_verdicts", []) or []
        if isinstance(item, Mapping)
        and str(item.get("capability") or "") == capability
        and str(item.get("verdict") or "") == "reject"
    }
    scored = []
    skipped = []
    seen: set[str] = set()
    for row in candidate_pool.get("candidates", []) or []:
        if not isinstance(row, Mapping):
            continue
        skill_id = str(row.get("skill_id") or "")
        canonical = _canonical_skill_id(row)
        if canonical in seen:
            continue
        seen.add(canonical)
        capability_candidates = {str(item) for item in row.get("capability_candidates", []) or []}
        if capability not in capability_candidates or row.get("ablation_eligible") is not True:
            continue
        if skill_id in rejected:
            skipped.append(_candidate_v2_decision(row, "skip_previously_rejected", 0, 0))
            continue
        score, penalty = _research_candidate_v2_score(row)
        if score <= 0:
            skipped.append(_candidate_v2_decision(row, "skip_no_source_discipline_signal", score, penalty))
            continue
        if penalty >= score:
            skipped.append(_candidate_v2_decision(row, "skip_platform_or_sales_heavy", score, penalty))
            continue
        scored.append(_candidate_v2_decision(row, "include_v2", score, penalty))

    selected = sorted(
        scored,
        key=lambda item: (
            -int(item["source_discipline_score"]),
            int(item["platform_only_penalty"]),
            str(item["skill_id"]),
            str(item["path"]),
        ),
    )[:max_candidates]
    selected_ids = {str(item["skill_id"]) for item in selected}
    v2_candidates = [
        row
        for row in candidate_pool.get("candidates", []) or []
        if isinstance(row, Mapping) and str(row.get("skill_id") or "") in selected_ids
    ]
    negative_control = _wrong_or_quarantined_candidate(candidate_pool, capability)
    if negative_control is not None:
        v2_candidates.append(negative_control)
    return {
        "schema": "nexus.research_candidate_v2_report.v1",
        "status": "PASS" if selected else "RETURN",
        "capability": capability,
        "runtime_update_allowed": False,
        "summary": {
            "previous_reject_count": len(rejected),
            "selected_candidate_count": len(selected),
            "skipped_count": len(skipped),
            "max_candidates": max_candidates,
        },
        "selection_policy": {
            "requires_ablation_eligible": True,
            "excludes_previous_rejects": True,
            "requires_source_discipline_score_gt_platform_penalty": True,
            "strong_signals": list(RESEARCH_CANDIDATE_V2_STRONG_SIGNALS),
            "platform_only_penalty_signals": list(RESEARCH_CANDIDATE_V2_PLATFORM_ONLY_SIGNALS),
        },
        "selected_candidates": selected,
        "skipped_candidates": skipped[:100],
        "candidate_pool_v2": {
            "schema": "nexus.fair_skill_candidate_pool.v2.slice",
            "status": "PASS" if selected else "RETURN",
            "source_status_report_schema": candidate_pool.get("source_status_report_schema", ""),
            "summary": {
                "total_candidates": len(v2_candidates),
                "selected_candidate_count": len(selected),
                "negative_control_count": 1 if negative_control is not None else 0,
                "capability": capability,
                "source_root_counts": dict(Counter(str(row.get("source_root") or "") for row in v2_candidates)),
            },
            "claim_boundary": [
                "This v2 pool is ablation-only and cannot update runtime policy.",
                "Rejected v1 candidates are excluded until source or taskset changes.",
            ],
            "candidates": v2_candidates,
        },
        "claim_boundary": [
            "Candidate v2 changes discovery inputs only; it does not prove skill value.",
            "Selected candidates still require live ablation, receipt paths, and threshold contracts.",
        ],
    }


def build_research_candidate_v3_report(
    candidate_pool: Mapping[str, Any],
    previous_catalog: Mapping[str, Any],
    *,
    capability: str = "research_and_source_discipline",
    max_candidates: int = 4,
    min_behavior_groups: int = 2,
) -> dict[str, Any]:
    """Select research candidates with observable source-discipline behavior."""

    rejected = {
        str(item.get("skill_id") or "")
        for item in previous_catalog.get("skill_verdicts", []) or []
        if isinstance(item, Mapping)
        and str(item.get("capability") or "") == capability
        and str(item.get("verdict") or "") == "reject"
    }
    scored = []
    skipped = []
    seen: set[str] = set()
    for row in candidate_pool.get("candidates", []) or []:
        if not isinstance(row, Mapping):
            continue
        skill_id = str(row.get("skill_id") or "")
        canonical = _canonical_skill_id(row)
        if canonical in seen:
            continue
        seen.add(canonical)
        capability_candidates = {str(item) for item in row.get("capability_candidates", []) or []}
        if capability not in capability_candidates or row.get("ablation_eligible") is not True:
            continue
        if skill_id in rejected:
            skipped.append(_research_candidate_v3_decision(row, "skip_previously_rejected", {}, 0))
            continue
        behavior_hits = _research_candidate_v3_behavior_hits(row)
        generic_penalty = _research_candidate_v3_generic_penalty(row)
        if len(behavior_hits) < min_behavior_groups:
            skipped.append(
                _research_candidate_v3_decision(
                    row,
                    "skip_missing_observable_source_discipline_behavior",
                    behavior_hits,
                    generic_penalty,
                )
            )
            continue
        if generic_penalty >= sum(len(values) for values in behavior_hits.values()):
            skipped.append(_research_candidate_v3_decision(row, "skip_generic_research_wrapper", behavior_hits, generic_penalty))
            continue
        scored.append(_research_candidate_v3_decision(row, "include_v3", behavior_hits, generic_penalty))

    selected = sorted(
        scored,
        key=lambda item: (
            -int(item["behavior_group_count"]),
            -int(item["behavior_signal_count"]),
            int(item["generic_penalty"]),
            str(item["skill_id"]),
        ),
    )[:max_candidates]
    selected_ids = {str(item["skill_id"]) for item in selected}
    v3_candidates = [
        row
        for row in candidate_pool.get("candidates", []) or []
        if isinstance(row, Mapping) and str(row.get("skill_id") or "") in selected_ids
    ]
    negative_control = _wrong_or_quarantined_candidate(candidate_pool, capability)
    if negative_control is not None:
        v3_candidates.append(negative_control)
    return {
        "schema": "nexus.research_candidate_v3_report.v1",
        "status": "PASS" if selected else "RETURN",
        "capability": capability,
        "runtime_update_allowed": False,
        "summary": {
            "previous_reject_count": len(rejected),
            "selected_candidate_count": len(selected),
            "skipped_count": len(skipped),
            "max_candidates": max_candidates,
            "min_behavior_groups": min_behavior_groups,
        },
        "selection_policy": {
            "requires_ablation_eligible": True,
            "excludes_previous_rejects": True,
            "requires_behavior_groups": sorted(RESEARCH_CANDIDATE_V3_BEHAVIOR_GROUPS),
            "min_behavior_groups": min_behavior_groups,
            "generic_penalty_signals": list(RESEARCH_CANDIDATE_V3_GENERIC_SIGNALS),
        },
        "selected_candidates": selected,
        "skipped_candidates": skipped[:100],
        "candidate_pool_v3": {
            "schema": "nexus.fair_skill_candidate_pool.v3.slice",
            "status": "PASS" if selected else "RETURN",
            "source_status_report_schema": candidate_pool.get("source_status_report_schema", ""),
            "summary": {
                "total_candidates": len(v3_candidates),
                "selected_candidate_count": len(selected),
                "negative_control_count": 1 if negative_control is not None else 0,
                "capability": capability,
                "source_root_counts": dict(Counter(str(row.get("source_root") or "") for row in v3_candidates)),
            },
            "claim_boundary": [
                "This v3 pool is ablation-only and cannot update runtime policy.",
                "Generic research wrappers are excluded until they expose observable source-discipline behavior.",
            ],
            "candidates": v3_candidates,
        },
        "claim_boundary": [
            "Candidate v3 changes discovery inputs only; it does not prove skill value.",
            "Selected candidates still require fixed-taskset live ablation, receipt paths, and threshold contracts.",
        ],
    }


def build_research_skill_supply_gap_contract(
    candidate_pool: Mapping[str, Any],
    previous_catalogs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    *,
    v3_report: Mapping[str, Any] | None = None,
    capability: str = "research_and_source_discipline",
    min_behavior_groups: int = 2,
) -> dict[str, Any]:
    """Explain why research needs new source-discipline skill supply before live spend."""

    rejected = _rejected_skill_ids(previous_catalogs, capability)
    candidate_rows = []
    seen: set[str] = set()
    for row in candidate_pool.get("candidates", []) or []:
        if not isinstance(row, Mapping):
            continue
        canonical = _canonical_skill_id(row)
        if canonical in seen:
            continue
        seen.add(canonical)
        if capability not in {str(item) for item in row.get("capability_candidates", []) or []}:
            continue
        if row.get("ablation_eligible") is not True:
            continue
        candidate_rows.append(row)
    reviewed = []
    for row in sorted(candidate_rows, key=lambda item: str(item.get("skill_id") or "")):
        skill_id = str(row.get("skill_id") or "")
        behavior_hits = _research_candidate_v3_behavior_hits(row)
        generic_penalty = _research_candidate_v3_generic_penalty(row)
        decision = "candidate_ready_for_v3_review"
        if skill_id in rejected:
            decision = "already_rejected_do_not_rerun"
        elif len(behavior_hits) < min_behavior_groups:
            decision = "supply_gap_missing_observable_source_discipline_behavior"
        elif generic_penalty >= sum(len(values) for values in behavior_hits.values()):
            decision = "supply_gap_generic_research_wrapper"
        reviewed.append(
            {
                "skill_id": skill_id,
                "source_root": str(row.get("source_root") or ""),
                "source_type": str(row.get("source_type") or ""),
                "path": str(row.get("path") or ""),
                "behavior_groups": sorted(behavior_hits),
                "behavior_group_count": len(behavior_hits),
                "generic_penalty": generic_penalty,
                "decision": decision,
                "prior_rejected": skill_id in rejected,
                "runtime_eligible": bool(row.get("runtime_eligible")),
                "ablation_eligible": bool(row.get("ablation_eligible")),
                "safety_status": str(row.get("safety_status") or ""),
            }
        )

    ready_candidates = [item for item in reviewed if item["decision"] == "candidate_ready_for_v3_review"]
    v3_summary = v3_report.get("summary", {}) if isinstance(v3_report, Mapping) else {}
    supply_gap = not ready_candidates
    return {
        "schema": "nexus.research_skill_supply_gap_contract.v1",
        "status": "PASS",
        "capability": capability,
        "runtime_update_allowed": False,
        "research_live_allowed": False if supply_gap else "PREFLIGHT_REQUIRED",
        "summary": {
            "candidate_count": len(candidate_rows),
            "prior_reject_count": len(rejected),
            "ready_candidate_count": len(ready_candidates),
            "supply_gap": supply_gap,
            "v3_selected_candidate_count": int(v3_summary.get("selected_candidate_count") or 0),
            "min_behavior_groups": min_behavior_groups,
        },
        "rejected_existing_candidate_ids": sorted(rejected),
        "candidate_decisions": reviewed[:100],
        "required_behavior_groups": sorted(RESEARCH_CANDIDATE_V3_BEHAVIOR_GROUPS),
        "creation_specs": _research_source_discipline_creation_specs(),
        "github_ingest_guard": {
            "lane": "external_candidate_pool_only",
            "runtime_mount_allowed": False,
            "required_fields": [
                "source_url",
                "repo",
                "commit_sha",
                "license",
                "skill_manifest_path",
                "ingest_receipt",
                "security_receipt",
            ],
            "required_checks": [
                "commit_sha_pinned",
                "license_allowlist_pass",
                "dependency_review_pass",
                "code_scanning_or_static_scan_pass",
                "workflow_scan_pass",
                "observable_source_discipline_behavior_present",
            ],
            "fail_fast": [
                "unversioned_external_source",
                "unknown_or_disallowed_license",
                "missing_security_receipt",
                "runtime_policy_update_attempt",
            ],
        },
        "next_actions": [
            "Do not rerun already rejected research v1/v2 candidates.",
            "Create or ingest source-discipline skills with at least two observable behavior groups.",
            "Regenerate the v3 candidate report before any Flash live spend.",
        ],
        "claim_boundary": [
            "This contract diagnoses research skill supply; it is not live skill-fit evidence.",
            "GitHub or external skills may enter only the candidate pool until safety and ablation receipts pass.",
        ],
    }


def build_governance_candidate_v2_report(
    candidate_pool: Mapping[str, Any],
    previous_catalog: Mapping[str, Any],
    *,
    capability: str = "governance_and_trust",
    max_candidates: int = 4,
) -> dict[str, Any]:
    """Select a governance/trust candidate v2 pool after low-yield targeted replay."""

    return _build_candidate_v2_report(
        candidate_pool,
        previous_catalog,
        capability=capability,
        max_candidates=max_candidates,
        schema="nexus.governance_candidate_v2_report.v1",
        strong_signals=GOVERNANCE_CANDIDATE_V2_STRONG_SIGNALS,
        penalty_signals=GOVERNANCE_CANDIDATE_V2_PLATFORM_ONLY_SIGNALS,
        kept_reason="governance_trust_signal",
    )


def write_skill_fit_row_level_rca(
    *,
    run_summary_path: str | Path,
    catalog_path: str | Path,
    output_path: str | Path,
    capability: str = "",
) -> dict[str, Any]:
    rca = build_skill_fit_row_level_rca(
        json.loads(Path(run_summary_path).read_text(encoding="utf-8")),
        json.loads(Path(catalog_path).read_text(encoding="utf-8")),
        capability=capability,
    )
    Path(output_path).write_text(json.dumps(rca, indent=2, ensure_ascii=False), encoding="utf-8")
    return rca


def write_research_candidate_v2_report(
    *,
    candidate_pool_path: str | Path,
    previous_catalog_path: str | Path,
    output_path: str | Path,
    candidate_pool_v2_path: str | Path | None = None,
    max_candidates: int = 4,
) -> dict[str, Any]:
    report = build_research_candidate_v2_report(
        json.loads(Path(candidate_pool_path).read_text(encoding="utf-8")),
        json.loads(Path(previous_catalog_path).read_text(encoding="utf-8")),
        max_candidates=max_candidates,
    )
    Path(output_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if candidate_pool_v2_path:
        Path(candidate_pool_v2_path).write_text(
            json.dumps(report["candidate_pool_v2"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return report


def write_research_candidate_v3_report(
    *,
    candidate_pool_path: str | Path,
    previous_catalog_path: str | Path,
    output_path: str | Path,
    candidate_pool_v3_path: str | Path | None = None,
    max_candidates: int = 4,
    min_behavior_groups: int = 2,
) -> dict[str, Any]:
    report = build_research_candidate_v3_report(
        json.loads(Path(candidate_pool_path).read_text(encoding="utf-8")),
        json.loads(Path(previous_catalog_path).read_text(encoding="utf-8")),
        max_candidates=max_candidates,
        min_behavior_groups=min_behavior_groups,
    )
    Path(output_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if candidate_pool_v3_path:
        Path(candidate_pool_v3_path).write_text(
            json.dumps(report["candidate_pool_v3"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return report


def write_research_skill_supply_gap_contract(
    *,
    candidate_pool_path: str | Path,
    previous_catalog_paths: list[str | Path],
    output_path: str | Path,
    v3_report_path: str | Path | None = None,
    min_behavior_groups: int = 2,
) -> dict[str, Any]:
    previous_catalogs = [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in previous_catalog_paths
        if Path(path).exists()
    ]
    v3_report = None
    if v3_report_path and Path(v3_report_path).exists():
        v3_report = json.loads(Path(v3_report_path).read_text(encoding="utf-8"))
    contract = build_research_skill_supply_gap_contract(
        json.loads(Path(candidate_pool_path).read_text(encoding="utf-8")),
        previous_catalogs,
        v3_report=v3_report,
        min_behavior_groups=min_behavior_groups,
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_governance_candidate_v2_report(
    *,
    candidate_pool_path: str | Path,
    previous_catalog_path: str | Path,
    output_path: str | Path,
    candidate_pool_v2_path: str | Path | None = None,
    max_candidates: int = 4,
) -> dict[str, Any]:
    report = build_governance_candidate_v2_report(
        json.loads(Path(candidate_pool_path).read_text(encoding="utf-8")),
        json.loads(Path(previous_catalog_path).read_text(encoding="utf-8")),
        max_candidates=max_candidates,
    )
    Path(output_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if candidate_pool_v2_path:
        Path(candidate_pool_v2_path).write_text(
            json.dumps(report["candidate_pool_v2"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return report


def build_skill_fit_cost_phase_contract(
    run_summary: Mapping[str, Any],
    catalog: Mapping[str, Any] | None = None,
    *,
    capability: str = "",
) -> dict[str, Any]:
    """Summarize skill-fit RCA cost and phase concentration without making delivery claims."""

    row_index = SkillFitRowIndex.from_run_summary(run_summary, catalog, capability=capability)
    rows = row_index.rows
    catalog_by_skill = row_index.catalog_by_skill
    skill_costs = []
    for skill_id, skill_rows in row_index.rows_by_skill.items():
        phase_totals: Counter[str] = Counter()
        row_costs = []
        effective_count = 0
        total_wall = 0.0
        total_tokens = 0
        total_model_calls = 0
        for row in skill_rows:
            benchmark = row.get("benchmark_row") if isinstance(row.get("benchmark_row"), Mapping) else {}
            effective = _is_effective_skill_row(row)
            effective_count += 1 if effective else 0
            wall = _number(benchmark.get("wall_duration_sec"), benchmark.get("duration_sec"), row.get("duration_sec"))
            tokens = int(_number(benchmark.get("total_tokens"), benchmark.get("model_total_tokens"), 0))
            model_calls = int(_number(benchmark.get("model_calls"), 0))
            total_wall += wall
            total_tokens += tokens
            total_model_calls += model_calls
            phase_costs = _phase_costs(benchmark)
            for phase, value in phase_costs.items():
                phase_totals[phase] += value
            row_costs.append(
                {
                    "row_id": str(row.get("row_id") or ""),
                    "task_ref": row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {},
                    "effective": effective,
                    "wall_sec": round(wall, 4),
                    "tokens": tokens,
                    "model_calls": model_calls,
                    "dominant_phase": _dominant_phase(phase_costs),
                }
            )
        tested_rows = len(skill_rows)
        dominant_phase = _dominant_phase(phase_totals)
        skill_costs.append(
                {
                    "capability": row_index.capability,
                "skill_id": skill_id,
                "verdict": str(catalog_by_skill.get(skill_id, {}).get("verdict") or ""),
                "tested_rows": tested_rows,
                "effective_rows": effective_count,
                "effective_rate": round(effective_count / tested_rows, 4) if tested_rows else 0.0,
                "wall_sec": round(total_wall, 4),
                "tokens": total_tokens,
                "model_calls": total_model_calls,
                "cost_per_effective_row": {
                    "wall_sec": round(total_wall / effective_count, 4) if effective_count else None,
                    "tokens": round(total_tokens / effective_count, 4) if effective_count else None,
                    "model_calls": round(total_model_calls / effective_count, 4) if effective_count else None,
                },
                "phase_cost_share": _phase_cost_share(phase_totals),
                "dominant_phase": dominant_phase,
                "top_wall_rows": sorted(row_costs, key=lambda item: float(item["wall_sec"]), reverse=True)[:5],
                "claim_boundary": "Cost RCA is diagnostic and must not be merged into delivery improvement claims.",
            }
        )
    return {
        "schema": "nexus.skill_fit_cost_phase_contract.v1",
        "status": "PASS" if row_index.rows_by_skill else "RETURN",
        "capability": row_index.capability,
        "runtime_update_allowed": False,
        "summary": {
            "row_count": len(rows),
            "skill_count": len(skill_costs),
            "total_wall_sec": round(sum(float(item["wall_sec"]) for item in skill_costs), 4),
            "total_tokens": sum(int(item["tokens"]) for item in skill_costs),
            "total_model_calls": sum(int(item["model_calls"]) for item in skill_costs),
            "skills_with_effective_rows": sum(1 for item in skill_costs if int(item["effective_rows"]) > 0),
        },
        "skill_costs": skill_costs,
        "claim_boundary": [
            "This contract explains cost and phase concentration only.",
            "Cost observations must not be merged into delivery improvement claims, promotion claims, or public cost-efficiency claims.",
        ],
    }


def build_skill_fit_redesign_contract(
    catalogs: Mapping[str, Mapping[str, Any]],
    *,
    min_unique_governance_tasks: int = 15,
) -> dict[str, Any]:
    """Decide whether the next move is more Flash, a candidate reset, or a taskset reset."""

    capability_actions = []
    for name, catalog in sorted(catalogs.items()):
        summary = catalog.get("summary") if isinstance(catalog.get("summary"), Mapping) else {}
        verdicts = [item for item in catalog.get("skill_verdicts", []) or [] if isinstance(item, Mapping)]
        capability = _first_catalog_capability(catalog) or str(name)
        positive_count = sum(1 for item in verdicts if str(item.get("verdict") or "") in {"keep", "replace_candidate"})
        needs_more_data_count = sum(1 for item in verdicts if str(item.get("verdict") or "") == "needs_more_data")
        reject_count = sum(1 for item in verdicts if str(item.get("verdict") or "") == "reject")
        task_count = int(summary.get("capability_only_rows") or summary.get("task_count") or 0)
        if positive_count:
            action = "allow_threshold_review"
        elif capability == "research_and_source_discipline" and reject_count == len(verdicts):
            action = "research_candidate_v3_required"
        elif capability == "governance_and_trust" and task_count < min_unique_governance_tasks:
            action = "governance_taskset_expansion_required"
        elif capability == "governance_and_trust":
            action = "governance_mutant_lane_required"
        elif needs_more_data_count:
            action = "candidate_or_taskset_redesign_required"
        else:
            action = "stop_flash_spend_until_candidate_source_changes"
        capability_actions.append(
            {
                "catalog": name,
                "capability": capability,
                "positive_count": positive_count,
                "needs_more_data_count": needs_more_data_count,
                "reject_count": reject_count,
                "task_count": task_count,
                "recommended_action": action,
                "flash_spend_allowed": action == "allow_threshold_review",
            }
        )
    return {
        "schema": "nexus.skill_fit_redesign_contract.v1",
        "status": "PASS" if capability_actions else "RETURN",
        "runtime_update_allowed": False,
        "flash100_allowed": any(item["flash_spend_allowed"] for item in capability_actions),
        "summary": {
            "capability_count": len(capability_actions),
            "blocked_capability_count": sum(1 for item in capability_actions if not item["flash_spend_allowed"]),
            "positive_capability_count": sum(1 for item in capability_actions if item["positive_count"] > 0),
        },
        "capability_actions": capability_actions,
        "claim_boundary": [
            "This contract redirects discovery; it does not lower promotion thresholds.",
            "More Flash spend is blocked for capabilities without positive receipt-backed skill verdicts.",
        ],
    }


def build_governance_taskset_expansion_contract(
    manifests: Mapping[str, Mapping[str, Any]],
    *,
    min_total_tasks: int = 15,
    max_total_tasks: int = 20,
    min_tasks_per_bucket: int = 3,
) -> dict[str, Any]:
    """Build a governance taskset expansion contract without spending model quota."""

    candidates = []
    seen: set[str] = set()
    for manifest_path, manifest in sorted(manifests.items()):
        for task in manifest.get("tasks", []) or []:
            if not isinstance(task, Mapping):
                continue
            task_id = str(task.get("id") or "")
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            buckets = _governance_task_buckets(task)
            if not buckets:
                continue
            candidates.append(
                {
                    "manifest": manifest_path,
                    "task_id": task_id,
                    "category": str(task.get("category") or ""),
                    "fixture_kind": str(task.get("fixture_kind") or ""),
                    "difficulty": str(task.get("difficulty") or ""),
                    "task_desc": str(task.get("task_desc") or ""),
                    "expected_capabilities": list(task.get("expected_capabilities") or []),
                    "governance_buckets": buckets,
                }
            )

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    bucket_counts: Counter[str] = Counter()
    for bucket in GOVERNANCE_TASKSET_BUCKETS:
        bucket_candidates = [item for item in candidates if bucket in item["governance_buckets"]]
        bucket_candidates.sort(key=lambda item: (len(item["governance_buckets"]), item["manifest"], item["task_id"]))
        for item in bucket_candidates:
            if bucket_counts[bucket] >= min_tasks_per_bucket:
                break
            if item["task_id"] in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item["task_id"])
            for item_bucket in item["governance_buckets"]:
                bucket_counts[item_bucket] += 1
    for item in candidates:
        if len(selected) >= max_total_tasks:
            break
        if len(selected) >= min_total_tasks and all(bucket_counts[bucket] >= min_tasks_per_bucket for bucket in GOVERNANCE_TASKSET_BUCKETS):
            break
        if item["task_id"] in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(item["task_id"])
        for item_bucket in item["governance_buckets"]:
            bucket_counts[item_bucket] += 1

    missing_specs = []
    for bucket in GOVERNANCE_TASKSET_BUCKETS:
        deficit = max(0, min_tasks_per_bucket - bucket_counts[bucket])
        for index in range(deficit):
            missing_specs.append(_governance_missing_task_spec(bucket, index + 1 + bucket_counts[bucket]))
    live_ready = not missing_specs and len(selected) >= min_total_tasks
    return {
        "schema": "nexus.governance_taskset_expansion_contract.v1",
        "status": "PASS",
        "capability": "governance_and_trust",
        "live_ready": live_ready,
        "summary": {
            "candidate_task_count": len(candidates),
            "selected_existing_task_count": len(selected),
            "proposed_new_task_count": len(missing_specs),
            "planned_total_task_count": len(selected) + len(missing_specs),
            "min_total_tasks": min_total_tasks,
            "max_total_tasks": max_total_tasks,
            "min_tasks_per_bucket": min_tasks_per_bucket,
            "bucket_counts": {bucket: bucket_counts[bucket] for bucket in GOVERNANCE_TASKSET_BUCKETS},
        },
        "selected_existing_tasks": selected,
        "proposed_new_task_specs": missing_specs,
        "preflight_status": "READY" if live_ready else "BLOCKED_UNTIL_TASKS_MATERIALIZED",
        "claim_boundary": [
            "This contract expands taskset design only; it does not create promotion evidence.",
            "Proposed tasks must be materialized with hidden verifiers before live Flash spend.",
        ],
    }


def build_governance_mutant_lane_contract(
    taskset_contract: Mapping[str, Any],
    *,
    min_mutants_per_bucket: int = 1,
) -> dict[str, Any]:
    """Generate fail-closed governance mutants from a live-ready taskset contract."""

    selected_tasks = [
        item for item in taskset_contract.get("selected_existing_tasks", []) or [] if isinstance(item, Mapping)
    ]
    summary = taskset_contract.get("summary", {}) if isinstance(taskset_contract.get("summary"), Mapping) else {}
    bucket_counts = summary.get("bucket_counts", {}) if isinstance(summary.get("bucket_counts"), Mapping) else {}
    live_ready = bool(taskset_contract.get("live_ready"))
    mutant_templates = {
        "audit": ("forged_pass_without_independent_audit", "Reject audit PASS when independent repro evidence is missing."),
        "claim_gate": ("unsupported_claim_with_green_status", "Reject claim PASS when artifact and replay causality are incomplete."),
        "redaction": ("secret_redaction_regression", "Reject output that exposes token or password while preserving ordinary fields."),
        "auth": ("deny_default_bypass", "Reject unknown roles, missing scopes, and unsafe operations."),
        "evidence_review": ("receipt_lite_incomplete", "Reject evidence summary without source refs, replay refs, or distinct roles."),
    }
    by_bucket: dict[str, list[Mapping[str, Any]]] = {bucket: [] for bucket in GOVERNANCE_TASKSET_BUCKETS}
    for task in selected_tasks:
        for bucket in _governance_task_buckets(task):
            by_bucket.setdefault(bucket, []).append(task)

    mutants = []
    for bucket, (mutant_kind, task_desc) in mutant_templates.items():
        for task in by_bucket.get(bucket, [])[:max(1, min_mutants_per_bucket)]:
            mutants.append(
                {
                    "mutant_id": f"{task.get('task_id') or task.get('id')}::{mutant_kind}",
                    "source_manifest": str(task.get("manifest") or ""),
                    "source_task_id": str(task.get("task_id") or task.get("id") or ""),
                    "bucket": bucket,
                    "mutant_kind": mutant_kind,
                    "task_desc": task_desc,
                    "expected_gate": "BLOCK_OR_RETURN",
                    "required_receipts": [
                        "mutant_source_task_ref",
                        "gate_decision",
                        "reason_code",
                        "evidence_path",
                    ],
                }
            )
    missing_buckets = [
        bucket
        for bucket in GOVERNANCE_TASKSET_BUCKETS
        if int(bucket_counts.get(bucket) or 0) < min_mutants_per_bucket or not by_bucket.get(bucket)
    ]
    return {
        "schema": "nexus.governance_mutant_lane_contract.v1",
        "status": "PASS" if live_ready and mutants and not missing_buckets else "RETURN",
        "capability": "governance_and_trust",
        "runtime_update_allowed": False,
        "live_ready": live_ready and not missing_buckets,
        "summary": {
            "selected_task_count": len(selected_tasks),
            "mutant_count": len(mutants),
            "bucket_counts": {str(key): int(value) for key, value in sorted(bucket_counts.items())},
            "missing_buckets": missing_buckets,
            "min_mutants_per_bucket": min_mutants_per_bucket,
        },
        "mutants": mutants,
        "promotion_rule": [
            "Governance skills cannot reach alternate/default if any mutant survives.",
            "Mutant kill evidence must be keyed by (capability, skill_id, mutant_id).",
            "Mutant lane is fail-closed and cannot update runtime policy directly.",
        ],
        "claim_boundary": [
            "This contract prepares governance anti-false-positive validation; it is not public benchmark evidence.",
            "A normal delivery PASS does not imply mutant kill PASS.",
        ],
    }


def write_skill_fit_cost_phase_contract(
    *,
    run_summary_path: str | Path,
    catalog_path: str | Path,
    output_path: str | Path,
    capability: str = "",
) -> dict[str, Any]:
    contract = build_skill_fit_cost_phase_contract(
        json.loads(Path(run_summary_path).read_text(encoding="utf-8")),
        json.loads(Path(catalog_path).read_text(encoding="utf-8")),
        capability=capability,
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_governance_taskset_expansion_contract(
    *,
    manifest_paths: list[str | Path],
    output_path: str | Path,
    min_total_tasks: int = 15,
    max_total_tasks: int = 20,
    min_tasks_per_bucket: int = 3,
) -> dict[str, Any]:
    manifests = {str(path): json.loads(Path(path).read_text(encoding="utf-8")) for path in manifest_paths}
    contract = build_governance_taskset_expansion_contract(
        manifests,
        min_total_tasks=min_total_tasks,
        max_total_tasks=max_total_tasks,
        min_tasks_per_bucket=min_tasks_per_bucket,
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_governance_mutant_lane_contract(
    *,
    taskset_contract_path: str | Path,
    output_path: str | Path,
    min_mutants_per_bucket: int = 1,
) -> dict[str, Any]:
    contract = build_governance_mutant_lane_contract(
        json.loads(Path(taskset_contract_path).read_text(encoding="utf-8")),
        min_mutants_per_bucket=min_mutants_per_bucket,
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_skill_fit_redesign_contract(
    *,
    catalog_paths: Mapping[str, str | Path],
    output_path: str | Path,
) -> dict[str, Any]:
    catalogs = {name: json.loads(Path(path).read_text(encoding="utf-8")) for name, path in catalog_paths.items()}
    contract = build_skill_fit_redesign_contract(catalogs)
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def _build_candidate_v2_report(
    candidate_pool: Mapping[str, Any],
    previous_catalog: Mapping[str, Any],
    *,
    capability: str,
    max_candidates: int,
    schema: str,
    strong_signals: tuple[str, ...],
    penalty_signals: tuple[str, ...],
    kept_reason: str,
) -> dict[str, Any]:
    rejected = {
        str(item.get("skill_id") or "")
        for item in previous_catalog.get("skill_verdicts", []) or []
        if isinstance(item, Mapping)
        and str(item.get("capability") or "") == capability
        and str(item.get("verdict") or "") == "reject"
    }
    scored = []
    skipped = []
    seen: set[str] = set()
    for row in candidate_pool.get("candidates", []) or []:
        if not isinstance(row, Mapping):
            continue
        skill_id = str(row.get("skill_id") or "")
        canonical = _canonical_skill_id(row)
        if canonical in seen:
            continue
        seen.add(canonical)
        capability_candidates = {str(item) for item in row.get("capability_candidates", []) or []}
        if capability not in capability_candidates or row.get("ablation_eligible") is not True:
            continue
        if skill_id in rejected:
            skipped.append(_candidate_v2_decision(row, "skip_previously_rejected", 0, 0, kept_reason=""))
            continue
        score, penalty = _candidate_v2_score(row, strong_signals, penalty_signals)
        if penalty >= score:
            skipped.append(_candidate_v2_decision(row, "skip_platform_or_unrelated_heavy", score, penalty, kept_reason=""))
            continue
        if score <= 0:
            skipped.append(_candidate_v2_decision(row, "skip_no_capability_signal", score, penalty, kept_reason=""))
            continue
        scored.append(_candidate_v2_decision(row, "include_v2", score, penalty, kept_reason=kept_reason))

    selected = sorted(
        scored,
        key=lambda item: (
            -int(item["source_discipline_score"]),
            int(item["platform_only_penalty"]),
            str(item["skill_id"]),
            str(item["path"]),
        ),
    )[:max_candidates]
    selected_ids = {str(item["skill_id"]) for item in selected}
    v2_candidates = [
        row
        for row in candidate_pool.get("candidates", []) or []
        if isinstance(row, Mapping) and str(row.get("skill_id") or "") in selected_ids
    ]
    negative_control = _wrong_or_quarantined_candidate(candidate_pool, capability)
    if negative_control is not None:
        v2_candidates.append(negative_control)
    return {
        "schema": schema,
        "status": "PASS" if selected else "RETURN",
        "capability": capability,
        "runtime_update_allowed": False,
        "summary": {
            "previous_reject_count": len(rejected),
            "selected_candidate_count": len(selected),
            "skipped_count": len(skipped),
            "max_candidates": max_candidates,
        },
        "selection_policy": {
            "requires_ablation_eligible": True,
            "excludes_previous_rejects": True,
            "requires_capability_signal_score_gt_platform_penalty": True,
            "strong_signals": list(strong_signals),
            "platform_only_penalty_signals": list(penalty_signals),
        },
        "selected_candidates": selected,
        "skipped_candidates": skipped[:100],
        "candidate_pool_v2": {
            "schema": "nexus.fair_skill_candidate_pool.v2.slice",
            "status": "PASS" if selected else "RETURN",
            "source_status_report_schema": candidate_pool.get("source_status_report_schema", ""),
            "summary": {
                "total_candidates": len(v2_candidates),
                "selected_candidate_count": len(selected),
                "negative_control_count": 1 if negative_control is not None else 0,
                "capability": capability,
                "source_root_counts": dict(Counter(str(row.get("source_root") or "") for row in v2_candidates)),
            },
            "claim_boundary": [
                "This v2 pool is ablation-only and cannot update runtime policy.",
                "Rejected candidates are excluded until source or taskset changes.",
            ],
            "candidates": v2_candidates,
        },
        "claim_boundary": [
            "Candidate v2 changes discovery inputs only; it does not prove skill value.",
            "Selected candidates still require live ablation, receipt paths, and threshold contracts.",
        ],
    }


def _first_catalog_capability(catalog: Mapping[str, Any] | None) -> str:
    if not catalog:
        return ""
    for item in catalog.get("skill_verdicts", []) or []:
        if isinstance(item, Mapping) and str(item.get("capability") or ""):
            return str(item.get("capability") or "")
    return ""


def _row_task_key(row: Mapping[str, Any]) -> str:
    task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
    manifest = str(task_ref.get("manifest") or "")
    task_id = str(task_ref.get("task_id") or "")
    return f"{manifest}::{task_id}" if manifest and task_id else task_id


def _is_effective_skill_row(row: Mapping[str, Any]) -> bool:
    gate = row.get("ablation_gate") if isinstance(row.get("ablation_gate"), Mapping) else {}
    gate_row = row.get("ablation_gate_row") if isinstance(row.get("ablation_gate_row"), Mapping) else {}
    return (
        str(row.get("status") or "") == "PASS"
        and str(gate.get("status") or "") == "PASS"
        and str(gate_row.get("status") or "") == "KEEP"
        and bool(gate_row.get("evidence_path"))
        and bool(gate_row.get("receipt_path"))
        and not bool(gate_row.get("trust_mismatch"))
    )


def _catalog_task_bucket(row: Mapping[str, Any]) -> str:
    task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
    task_id = str(task_ref.get("task_id") or "")
    benchmark_row = row.get("benchmark_row") if isinstance(row.get("benchmark_row"), Mapping) else {}
    bucket = str(benchmark_row.get("category") or benchmark_row.get("task_type") or "").strip()
    return bucket or (task_id.split("-")[0] if task_id else "")


def _gate_status(row: Mapping[str, Any]) -> str:
    gate = row.get("ablation_gate") if isinstance(row.get("ablation_gate"), Mapping) else {}
    return str(gate.get("status") or "")


def _governance_task_buckets(task: Mapping[str, Any]) -> list[str]:
    text = " ".join(
        [
            str(task.get("id") or ""),
            str(task.get("category") or ""),
            str(task.get("fixture_kind") or ""),
            str(task.get("task_desc") or ""),
            " ".join(str(item) for item in task.get("expected_capabilities", []) or []),
        ]
    ).lower()
    return [bucket for bucket, signals in GOVERNANCE_TASKSET_BUCKETS.items() if any(signal in text for signal in signals)]


def _governance_missing_task_spec(bucket: str, ordinal: int) -> dict[str, Any]:
    descriptions = {
        "audit": "Review a public claim bundle and reject findings without independent audit evidence.",
        "claim_gate": "Reject a passing status summary when claim, artifact, and replay causality diverge.",
        "redaction": "Preserve secret redaction while refactoring a credential or token scrubber.",
        "auth": "Enforce deny-by-default authorization for unknown roles, missing scopes, and unsafe operations.",
        "evidence_review": "Verify evidence paths, artifact ownership, and source references before accepting a report.",
    }
    return {
        "id": f"governance-expansion-{bucket}-{ordinal:03d}",
        "bucket": bucket,
        "category": "governance_taskset_expansion",
        "difficulty": "hard",
        "fixture_kind": f"nexus_governance_{bucket}_v1",
        "task_desc": descriptions[bucket],
        "expected_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"],
        "required_hidden_verifier": True,
        "materialization_status": "TODO",
    }


def _number(*values: object) -> float:
    for value in values:
        try:
            if value is not None and value != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _phase_costs(benchmark: Mapping[str, Any]) -> dict[str, float]:
    phases = {}
    for phase in ("p", "x", "d", "r", "a", "c"):
        phases[phase.upper()] = _number(benchmark.get(f"phase_wall_{phase}_sec"))
    return phases


def _dominant_phase(phase_costs: Mapping[str, float]) -> str:
    if not phase_costs:
        return ""
    phase, value = max(phase_costs.items(), key=lambda item: float(item[1]))
    return str(phase) if value > 0 else ""


def _phase_cost_share(phase_costs: Mapping[str, float]) -> dict[str, float]:
    total = sum(float(value) for value in phase_costs.values())
    if total <= 0:
        return {str(phase): 0.0 for phase in sorted(phase_costs)}
    return {str(phase): round(float(value) / total, 4) for phase, value in sorted(phase_costs.items())}


def _research_candidate_v2_score(row: Mapping[str, Any]) -> tuple[int, int]:
    return _candidate_v2_score(
        row,
        RESEARCH_CANDIDATE_V2_STRONG_SIGNALS,
        RESEARCH_CANDIDATE_V2_PLATFORM_ONLY_SIGNALS,
    )


def _candidate_v2_score(row: Mapping[str, Any], strong_signals: tuple[str, ...], penalty_signals: tuple[str, ...]) -> tuple[int, int]:
    text = " ".join(str(row.get(key) or "") for key in ("skill_id", "load_when", "path")).lower()
    score = sum(text.count(signal) for signal in strong_signals)
    penalty = sum(text.count(signal) for signal in penalty_signals)
    return score, penalty


def _candidate_v2_decision(
    row: Mapping[str, Any],
    decision: str,
    score: int,
    penalty: int,
    *,
    kept_reason: str = "source_discipline_signal",
) -> dict[str, Any]:
    return {
        "skill_id": str(row.get("skill_id") or ""),
        "source_root": str(row.get("source_root") or ""),
        "source_type": str(row.get("source_type") or ""),
        "path": str(row.get("path") or ""),
        "sha256": str(row.get("sha256") or ""),
        "runtime_eligible": bool(row.get("runtime_eligible")),
        "ablation_eligible": bool(row.get("ablation_eligible")),
        "safety_status": str(row.get("safety_status") or ""),
        "source_discipline_score": score,
        "platform_only_penalty": penalty,
        "candidate_decision": decision,
        "semantic_cluster_id": _canonical_skill_id(row),
        "dedup_similarity": 1.0,
        "kept_reason": kept_reason if decision == "include_v2" else "",
        "evidence_refs": [str(ref) for ref in row.get("evidence_refs", []) or [] if str(ref)],
    }


def _research_candidate_v3_text(row: Mapping[str, Any]) -> str:
    return " ".join(str(row.get(key) or "") for key in ("skill_id", "load_when", "path")).lower()


def _research_candidate_v3_behavior_hits(row: Mapping[str, Any]) -> dict[str, list[str]]:
    text = _research_candidate_v3_text(row)
    hits: dict[str, list[str]] = {}
    for group, signals in RESEARCH_CANDIDATE_V3_BEHAVIOR_GROUPS.items():
        matched = [signal for signal in signals if signal in text]
        if matched:
            hits[group] = matched
    return hits


def _research_candidate_v3_generic_penalty(row: Mapping[str, Any]) -> int:
    text = _research_candidate_v3_text(row)
    return sum(text.count(signal) for signal in RESEARCH_CANDIDATE_V3_GENERIC_SIGNALS)


def _research_candidate_v3_decision(
    row: Mapping[str, Any],
    decision: str,
    behavior_hits: Mapping[str, list[str]],
    generic_penalty: int,
) -> dict[str, Any]:
    behavior_signal_count = sum(len(values) for values in behavior_hits.values())
    return {
        "skill_id": str(row.get("skill_id") or ""),
        "source_root": str(row.get("source_root") or ""),
        "source_type": str(row.get("source_type") or ""),
        "path": str(row.get("path") or ""),
        "sha256": str(row.get("sha256") or ""),
        "runtime_eligible": bool(row.get("runtime_eligible")),
        "ablation_eligible": bool(row.get("ablation_eligible")),
        "safety_status": str(row.get("safety_status") or ""),
        "behavior_groups": sorted(behavior_hits),
        "behavior_group_count": len(behavior_hits),
        "behavior_signal_count": behavior_signal_count,
        "generic_penalty": generic_penalty,
        "candidate_decision": decision,
        "semantic_cluster_id": _canonical_skill_id(row),
        "dedup_similarity": 1.0,
        "kept_reason": "observable_source_discipline_behavior" if decision == "include_v3" else "",
        "evidence_refs": [str(ref) for ref in row.get("evidence_refs", []) or [] if str(ref)],
    }


def _rejected_skill_ids(catalogs: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...], capability: str) -> set[str]:
    rejected: set[str] = set()
    for catalog in catalogs:
        for item in catalog.get("skill_verdicts", []) or []:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("capability") or "") != capability:
                continue
            if str(item.get("verdict") or "") == "reject":
                rejected.add(str(item.get("skill_id") or ""))
    return {item for item in rejected if item}


def _research_source_discipline_creation_specs() -> list[dict[str, Any]]:
    return [
        {
            "skill_id": "research-citation-chain-verifier",
            "behavior_groups": ["citation_chain", "source_validation"],
            "load_when": "Load when research output must trace claims to stable source references and verify citation chains.",
            "required_receipts": ["claim_to_source_refs", "citation_chain_status", "source_validation_status"],
            "promotion_gate": "Must improve outcome_contributed rows without increasing trust mismatch.",
        },
        {
            "skill_id": "research-source-conflict-resolver",
            "behavior_groups": ["source_conflict", "source_validation"],
            "load_when": "Load when sources disagree and the answer must preserve conflict, confidence, and provenance.",
            "required_receipts": ["conflicting_source_refs", "resolution_reason", "source_validation_status"],
            "promotion_gate": "Must fail closed when source disagreement is unresolved.",
        },
        {
            "skill_id": "research-source-validation-auditor",
            "behavior_groups": ["citation_chain", "source_conflict", "source_validation"],
            "load_when": "Load when a research artifact needs an independent source-discipline audit before acceptance.",
            "required_receipts": ["audit_findings", "missing_source_refs", "source_validation_status"],
            "promotion_gate": "Must reject missing or circular evidence paths.",
        },
    ]


def build_research_source_discipline_skill_specs(
    supply_gap_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose research skill creation and external ingest as a standalone contract."""

    creation_specs = [
        spec for spec in supply_gap_contract.get("creation_specs", []) or [] if isinstance(spec, Mapping)
    ]
    ingest_guard = supply_gap_contract.get("github_ingest_guard", {})
    if not isinstance(ingest_guard, Mapping):
        ingest_guard = {}
    required_groups = sorted(
        {
            group
            for spec in creation_specs
            for group in spec.get("behavior_groups", [])
            if str(group)
        }
    )
    return {
        "schema": "nexus.research_source_discipline_skill_specs.v1",
        "status": "PASS" if creation_specs and ingest_guard else "RETURN",
        "capability": "research_and_source_discipline",
        "runtime_update_allowed": False,
        "research_live_allowed": False,
        "summary": {
            "creation_spec_count": len(creation_specs),
            "required_behavior_group_count": len(required_groups),
            "external_ingest_guard_present": bool(ingest_guard),
            "supply_gap": bool(supply_gap_contract.get("summary", {}).get("supply_gap"))
            if isinstance(supply_gap_contract.get("summary"), Mapping)
            else True,
        },
        "required_behavior_groups": required_groups,
        "creation_specs": creation_specs,
        "external_ingest_guard": ingest_guard,
        "promotion_boundary": [
            "Generated or ingested research skills may enter only the candidate pool.",
            "Research live remains blocked until a regenerated v3 report selects candidates with observable behavior receipts.",
        ],
    }


def build_research_external_ingest_guard(
    source_specs_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the external research-skill ingest guard without fetching network sources."""

    guard = source_specs_contract.get("external_ingest_guard", {})
    if not isinstance(guard, Mapping):
        guard = {}
    required_fields = [str(item) for item in guard.get("required_fields", []) or [] if str(item)]
    required_checks = [str(item) for item in guard.get("required_checks", []) or [] if str(item)]
    return {
        "schema": "nexus.research_external_ingest_guard.v1",
        "status": "PASS" if required_fields and required_checks else "RETURN",
        "capability": "research_and_source_discipline",
        "runtime_update_allowed": False,
        "candidate_pool_update_allowed": True,
        "network_fetch_performed": False,
        "summary": {
            "required_field_count": len(required_fields),
            "required_check_count": len(required_checks),
            "ingested_candidate_count": 0,
            "runtime_mount_allowed": bool(guard.get("runtime_mount_allowed")) is True,
        },
        "candidate_schema": {
            "required_fields": required_fields,
            "required_checks": required_checks,
            "required_behavior_groups": list(source_specs_contract.get("required_behavior_groups", []) or []),
        },
        "allowlist_policy": {
            "source_url_required": True,
            "commit_sha_required": True,
            "license_status_required": True,
            "security_receipt_required": True,
            "workflow_scan_status_required": True,
        },
        "fail_fast": list(guard.get("fail_fast", []) or []),
        "claim_boundary": [
            "This guard validates external candidate metadata only; it does not fetch or mount skills.",
            "External candidates remain candidate-pool-only until source, license, security, workflow, and behavior receipts pass.",
        ],
    }


def build_research_external_candidate_pool(
    source_specs_contract: Mapping[str, Any],
    *,
    source_specs_ref: str = "docs/reports/NEXUS_RESEARCH_SOURCE_DISCIPLINE_SKILL_SPECS_2026-05-17.json",
) -> dict[str, Any]:
    """Create candidate-pool-only research skill entries from guarded source specs."""

    specs = [item for item in source_specs_contract.get("creation_specs", []) or [] if isinstance(item, Mapping)]
    candidates = []
    for spec in specs:
        skill_id = str(spec.get("skill_id") or "")
        behavior_groups = [str(item) for item in spec.get("behavior_groups", []) or [] if str(item)]
        behavior_text = " ".join(group.replace("_", "-") for group in behavior_groups)
        candidates.append(
            {
                "skill_id": skill_id,
                "source_root": "external_research_guard",
                "source_type": "generated_source_discipline_spec",
                "path": f"external-candidate://research/{skill_id}",
                "sha256": _stable_spec_sha(skill_id, behavior_text),
                "capability_candidates": ["research_and_source_discipline"],
                "runtime_eligible": False,
                "ablation_eligible": True,
                "safety_status": "external_candidate_pool_only",
                "source_url": f"local-spec://{source_specs_ref}#{skill_id}",
                "repo": "local-spec",
                "commit_sha": _stable_spec_sha("commit", skill_id, behavior_text),
                "license_status": "local_spec_only",
                "security_receipt": "metadata_only_no_code_execution",
                "workflow_scan_status": "not_applicable_no_workflow",
                "load_when": f"{spec.get('load_when', '')} Requires {behavior_text}; source refs, conflicting sources, source validation, provenance, and citation chain receipts.",
                "evidence_refs": [str(item) for item in spec.get("required_receipts", []) or [] if str(item)],
            }
        )
    return {
        "schema": "nexus.research_external_candidate_pool.v1",
        "status": "PASS" if candidates else "RETURN",
        "capability": "research_and_source_discipline",
        "runtime_update_allowed": False,
        "summary": {
            "candidate_count": len(candidates),
            "runtime_eligible_count": 0,
            "ablation_eligible_count": len(candidates),
        },
        "candidates": candidates,
        "claim_boundary": [
            "Generated research candidates are metadata-only and candidate-pool-only.",
            "They must pass v3 selection and live receipts before any runtime policy update.",
        ],
    }


def write_research_external_candidate_pool(
    *,
    source_specs_contract_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    source_specs_path = Path(source_specs_contract_path)
    contract = build_research_external_candidate_pool(
        json.loads(source_specs_path.read_text(encoding="utf-8")),
        source_specs_ref=str(source_specs_path),
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def write_research_external_ingest_guard(
    *,
    source_specs_contract_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    contract = build_research_external_ingest_guard(
        json.loads(Path(source_specs_contract_path).read_text(encoding="utf-8"))
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def _stable_spec_sha(*parts: str) -> str:
    import hashlib

    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def write_research_source_discipline_skill_specs(
    *,
    supply_gap_contract_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    contract = build_research_source_discipline_skill_specs(
        json.loads(Path(supply_gap_contract_path).read_text(encoding="utf-8"))
    )
    Path(output_path).write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    return contract


def _canonical_skill_id(row: Mapping[str, Any]) -> str:
    return str(row.get("skill_id") or "").strip().removeprefix("gstack-")


def _wrong_or_quarantined_candidate(candidate_pool: Mapping[str, Any], capability: str) -> Mapping[str, Any] | None:
    candidates = [row for row in candidate_pool.get("candidates", []) if isinstance(row, Mapping)]
    quarantined = [
        row
        for row in candidates
        if str(row.get("safety_status") or "") == "quarantined"
        and capability not in {str(item) for item in row.get("capability_candidates", [])}
    ]
    wrong_capability = [
        row
        for row in candidates
        if row.get("ablation_eligible") is True
        and capability not in {str(item) for item in row.get("capability_candidates", [])}
    ]
    choices = quarantined or wrong_capability
    if not choices:
        return None
    return sorted(choices, key=lambda row: (str(row.get("sha256") or ""), str(row.get("path") or "")))[0]
