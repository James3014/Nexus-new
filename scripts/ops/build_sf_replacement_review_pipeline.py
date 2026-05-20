#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_SFV2 = PROJECT_ROOT / "docs/reports/NEXUS_SFV2_SKILL_SELECTION_PIPELINE_2026-05-20.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs/reports/NEXUS_SF_REPLACEMENT_REVIEW_PIPELINE_2026-05-21.json"

DECISION_KEEP_CURRENT = "KEEP_CURRENT"
DECISION_REPLACE_PRIMARY = "REPLACE_PRIMARY"
DECISION_ADD_TO_MULTI = "ADD_TO_MULTI"
DECISION_REJECT = "REJECT"
DECISION_HOLD_MORE_DATA = "HOLD_MORE_DATA"

SAFE_SOURCE_TIERS = {
    "nexus_curated_candidate",
    "repo_local_curated",
    "current_best",
    "approved_external_reference",
    "safe_candidate",
}
RUNTIME_ELIGIBLE_TIERS = {"nexus_curated_candidate", "repo_local_curated", "current_best"}
QUARANTINE_MARKERS = (
    "candidate-skill-from-",
    "auto-gen-",
    ".codexworktrees",
    ".codex/worktrees",
    "worktree",
    "archive",
    "vendor",
)


def build_sf_replacement_review_pipeline(
    *,
    sfv2_pipeline: Mapping[str, Any],
    candidate_intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current_rows = [_current_capability_state(row) for row in sfv2_pipeline.get("rows", []) if isinstance(row, Mapping)]
    baselines = {row["capability"]: row for row in current_rows}
    intake_rows = [_candidate_intake_row(row, baselines) for row in _candidate_rows(candidate_intake)]
    comparison_rows = [_comparison_queue_row(row, baselines) for row in intake_rows if row["intake_status"] == "PASS"]
    candidate_decisions = [_candidate_decision(row, baselines) for row in intake_rows]
    baseline_decisions = [_baseline_decision(row) for row in current_rows]
    all_decisions = baseline_decisions + candidate_decisions
    blockers = _pipeline_blockers(current_rows, intake_rows, comparison_rows)
    return {
        "schema": "nexus.sf_replacement_review_pipeline.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": _summary(
            current_rows=current_rows,
            intake_rows=intake_rows,
            comparison_rows=comparison_rows,
            decisions=all_decisions,
        ),
        "sf_r_taskcards": _taskcards(blockers),
        "current_capability_baselines": current_rows,
        "candidate_intake": intake_rows,
        "comparison_queue": comparison_rows,
        "decision_ledger": all_decisions,
        "catalog_update_packet": _catalog_update_packet(all_decisions),
        "runtime_apply_review_packet": _runtime_apply_review_packet(all_decisions),
        "automation_hook": _automation_hook(),
        "claim_boundary": [
            "SF-R compares manually or automatically added skills against the current capability baseline.",
            "A candidate can update catalog/review packets only after safety tiering, capability classification, receipt-backed comparison, and decision normalization.",
            "SF-R does not directly update runtime defaults and does not unlock public benchmark claims.",
        ],
        "blockers": blockers,
    }


def _current_capability_state(row: Mapping[str, Any]) -> dict[str, Any]:
    mat_b = _mapping(row.get("m6_mat_b_decision"))
    catalog = _mapping(row.get("m7_catalog_update"))
    runtime = _mapping(row.get("m8_runtime_apply_review"))
    intake = _mapping(row.get("m1_intake"))
    shortlist = _mapping(row.get("m2_shortlist"))
    assembly = _mapping(row.get("m4_multi_skill_assembly"))
    capability = str(row.get("capability") or "")
    primary = str(shortlist.get("current_primary") or intake.get("primary_skill_id") or "")
    return {
        "capability": capability,
        "current_primary_skill_id": primary,
        "current_selected_skill_ids": [str(item) for item in catalog.get("selected_skill_ids", []) or [] if str(item)],
        "current_mode": str(assembly.get("mode") or "Mode A (Solo)"),
        "source_class": str(intake.get("source_class") or "unknown_reference"),
        "mat_b_state": str(mat_b.get("decision_state") or "NEEDS_MORE_CANDIDATES"),
        "mat_b_verdict": str(mat_b.get("verdict") or ""),
        "runtime_review_state": str(runtime.get("review_state") or ""),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _candidate_rows(candidate_intake: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(candidate_intake, Mapping):
        return []
    rows = candidate_intake.get("skills", candidate_intake.get("rows", []))
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _candidate_intake_row(row: Mapping[str, Any], baselines: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    skill_id = str(row.get("skill_id") or row.get("id") or "")
    source_path = str(row.get("source_path") or row.get("path") or "")
    source_url = str(row.get("source_url") or "")
    source_tier = str(row.get("source_tier") or row.get("tier") or _infer_source_tier(skill_id, source_path))
    safety_status = str(row.get("safety_status") or row.get("security_status") or "UNKNOWN")
    license_status = str(row.get("license_status") or "UNKNOWN")
    capability = _classify_capability(row, baselines)
    blockers = _intake_blockers(
        skill_id=skill_id,
        source_path=source_path,
        source_tier=source_tier,
        safety_status=safety_status,
        license_status=license_status,
        capability=capability,
        baselines=baselines,
    )
    return {
        "skill_id": skill_id,
        "source_path": source_path,
        "source_url": source_url,
        "source_tier": source_tier,
        "safety_status": safety_status,
        "license_status": license_status,
        "capability": capability,
        "role": str(row.get("role") or _infer_role(skill_id)),
        "intended_action": str(row.get("intended_action") or ""),
        "comparison_result": _mapping(row.get("comparison_result") or row.get("mat_b_result")),
        "intake_status": "PASS" if not blockers else "RETURN",
        "blockers": blockers,
        "eligible_for_runtime_direct_mount": source_tier in RUNTIME_ELIGIBLE_TIERS and not blockers,
    }


def _comparison_queue_row(row: Mapping[str, Any], baselines: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    baseline = baselines[str(row["capability"])]
    candidate_skill = str(row["skill_id"])
    return {
        "capability": row["capability"],
        "baseline_arm": {
            "mode": "Mode A (current primary)",
            "skill_ids": [baseline["current_primary_skill_id"]],
        },
        "challenger_arm": _challenger_arm(row, baseline),
        "required_receipt_chain": ["selected", "injected", "used", "evidence", "gate", "outcome"],
        "gate": "Flash+Nexus internal compare before catalog/runtime review",
        "public_benchmark_allowed": False,
        "queue_state": "READY_FOR_COMPARISON" if not row["comparison_result"] else "COMPARISON_RESULT_ATTACHED",
        "candidate_skill_id": candidate_skill,
    }


def _candidate_decision(row: Mapping[str, Any], baselines: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    blockers = [str(item) for item in row.get("blockers", []) or []]
    comparison = _mapping(row.get("comparison_result"))
    if blockers:
        decision = DECISION_REJECT
        reason = blockers[0]
    elif not comparison:
        decision = DECISION_HOLD_MORE_DATA
        reason = "needs_flash_nexus_compare"
    else:
        compare_blockers = _comparison_blockers(comparison)
        if compare_blockers:
            decision = DECISION_HOLD_MORE_DATA if _is_more_data_blocker(compare_blockers) else DECISION_REJECT
            reason = compare_blockers[0]
            blockers = compare_blockers
        elif _should_replace_primary(row, comparison):
            decision = DECISION_REPLACE_PRIMARY
            reason = "candidate_beats_current_primary_with_clean_receipts"
        elif _should_add_to_multi(row, comparison):
            decision = DECISION_ADD_TO_MULTI
            reason = "candidate_adds_complementary_role_with_clean_receipts"
        else:
            decision = DECISION_KEEP_CURRENT
            reason = "candidate_does_not_beat_current_baseline"
    capability = str(row.get("capability") or "")
    baseline = baselines.get(capability, {})
    return {
        "entry_type": "candidate",
        "capability": capability,
        "current_skill_ids": baseline.get("current_selected_skill_ids", []),
        "candidate_skill_id": str(row.get("skill_id") or ""),
        "decision": decision,
        "reason": reason,
        "blockers": sorted(set(blockers)),
        "catalog_update_allowed": decision in {DECISION_REPLACE_PRIMARY, DECISION_ADD_TO_MULTI, DECISION_KEEP_CURRENT},
        "runtime_apply_review_allowed": decision in {DECISION_REPLACE_PRIMARY, DECISION_ADD_TO_MULTI},
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _baseline_decision(row: Mapping[str, Any]) -> dict[str, Any]:
    state = str(row.get("mat_b_state") or "")
    if state == "APPROVE_MULTI_ASSEMBLY":
        decision = DECISION_ADD_TO_MULTI
        reason = "existing_heep_mat_b_approved_multi_assembly"
    elif state in {"KEEP_SINGLE_PRIMARY", "REJECT_CANDIDATE"}:
        decision = DECISION_KEEP_CURRENT
        reason = "existing_baseline_remains_best"
    elif state.startswith("HOLD_"):
        decision = DECISION_HOLD_MORE_DATA
        reason = state.lower()
    else:
        decision = DECISION_HOLD_MORE_DATA
        reason = "needs_more_candidates"
    return {
        "entry_type": "current_baseline",
        "capability": row["capability"],
        "current_skill_ids": row["current_selected_skill_ids"] or [row["current_primary_skill_id"]],
        "candidate_skill_id": "",
        "decision": decision,
        "reason": reason,
        "blockers": [] if decision != DECISION_HOLD_MORE_DATA else [reason],
        "catalog_update_allowed": True,
        "runtime_apply_review_allowed": decision == DECISION_ADD_TO_MULTI,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _catalog_update_packet(decisions: list[Mapping[str, Any]]) -> dict[str, Any]:
    updates = [
        decision
        for decision in decisions
        if decision["decision"] in {DECISION_KEEP_CURRENT, DECISION_REPLACE_PRIMARY, DECISION_ADD_TO_MULTI}
    ]
    return {
        "schema": "nexus.sf_replacement_catalog_update_packet.v1",
        "status": "PASS",
        "update_count": len(updates),
        "updates": updates,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _runtime_apply_review_packet(decisions: list[Mapping[str, Any]]) -> dict[str, Any]:
    review_items = [decision for decision in decisions if decision["runtime_apply_review_allowed"]]
    return {
        "schema": "nexus.sf_replacement_runtime_apply_review_packet.v1",
        "status": "PASS",
        "review_item_count": len(review_items),
        "review_items": review_items,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "gate": "manual/runtime apply review must rerun post-apply smoke before default changes",
    }


def _automation_hook() -> dict[str, Any]:
    return {
        "schema": "nexus.sf_replacement_automation_hook.v1",
        "hook_name": "sf_new_skill_replacement_review",
        "triggers": ["manual_skill_added", "source_refresh_new_skill_detected"],
        "steps": [
            "source_tier_and_safety_screen",
            "capability_classification",
            "baseline_resolution",
            "flash_nexus_compare_queue",
            "receipt_and_token_truth_gate",
            "decision_ledger_writeback",
            "catalog_update_packet",
            "runtime_apply_review_packet",
        ],
        "forbidden_actions": ["runtime_default_auto_apply", "public_benchmark_unlock", "quarantine_skill_mount"],
    }


def _summary(
    *,
    current_rows: list[Mapping[str, Any]],
    intake_rows: list[Mapping[str, Any]],
    comparison_rows: list[Mapping[str, Any]],
    decisions: list[Mapping[str, Any]],
) -> dict[str, Any]:
    decision_counts = _counts(str(row["decision"]) for row in decisions)
    return {
        "capability_count": len(current_rows),
        "candidate_intake_count": len(intake_rows),
        "candidate_intake_pass_count": sum(1 for row in intake_rows if row["intake_status"] == "PASS"),
        "comparison_queue_count": len(comparison_rows),
        "decision_counts": decision_counts,
        "all_capabilities_have_baseline": all(bool(row["current_primary_skill_id"]) for row in current_rows),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _taskcards(blockers: list[str]) -> dict[str, Any]:
    status = "PASS" if not blockers else "RETURN"
    return {
        "SF-R0_source_tier_screen": {"status": status, "exit": "candidate tiers and quarantine blockers are explicit"},
        "SF-R1_capability_classifier": {"status": status, "exit": "each accepted candidate maps to a known capability"},
        "SF-R2_baseline_resolver": {"status": status, "exit": "each capability resolves current primary and selected skills"},
        "SF-R3_compare_matrix_builder": {"status": status, "exit": "accepted candidates produce Flash+Nexus compare rows"},
        "SF-R4_decision_schema": {
            "status": status,
            "exit": "decisions normalize to KEEP_CURRENT/REPLACE_PRIMARY/ADD_TO_MULTI/REJECT/HOLD_MORE_DATA",
        },
        "SF-R5_catalog_ledger_packet": {"status": status, "exit": "catalog update packet is generated"},
        "SF-R6_runtime_review_packet": {"status": status, "exit": "runtime apply review remains gated and non-public"},
        "SF-R7_automation_hook": {"status": status, "exit": "manual and automatic new-skill triggers share one hook contract"},
    }


def _pipeline_blockers(
    current_rows: list[Mapping[str, Any]],
    intake_rows: list[Mapping[str, Any]],
    comparison_rows: list[Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if not current_rows:
        blockers.append("missing_current_capability_baselines")
    for row in current_rows:
        if not row["current_primary_skill_id"]:
            blockers.append(f"{row['capability']}:missing_current_primary_skill")
    for row in intake_rows:
        if row["intake_status"] == "PASS" and row["capability"] and not any(
            item["capability"] == row["capability"] for item in comparison_rows
        ):
            blockers.append(f"{row['skill_id']}:missing_compare_queue_row")
    return sorted(set(blockers))


def _intake_blockers(
    *,
    skill_id: str,
    source_path: str,
    source_tier: str,
    safety_status: str,
    license_status: str,
    capability: str,
    baselines: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    blob = f"{skill_id} {source_path} {source_tier}".lower()
    blockers: list[str] = []
    if not skill_id:
        blockers.append("missing_skill_id")
    if any(marker in blob for marker in QUARANTINE_MARKERS):
        blockers.append("quarantine_tier_blocked")
    if source_tier not in SAFE_SOURCE_TIERS:
        blockers.append("unsafe_source_tier")
    if safety_status not in {"PASS", "REVIEWED_PASS"}:
        blockers.append("safety_status_not_pass")
    if license_status not in {"PASS", "COMPATIBLE", "REVIEWED_PASS"}:
        blockers.append("license_status_not_pass")
    if not capability:
        blockers.append("capability_unclassified")
    elif capability not in baselines:
        blockers.append("capability_not_in_current_route_map")
    return sorted(set(blockers))


def _comparison_blockers(comparison: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(comparison.get("status") or "PASS") not in {"PASS", "SUCCESS"}:
        blockers.append("comparison_row_not_pass")
    if not bool(comparison.get("receipt_chain_pass", False)):
        blockers.append("receipt_chain_not_pass")
    if bool(comparison.get("trust_mismatch", False)):
        blockers.append("trust_mismatch")
    if str(comparison.get("provider_token_cleanliness") or "MEASURED") not in {"MEASURED", "NOT_APPLICABLE"}:
        blockers.append("provider_token_truth_not_clean")
    if float(comparison.get("success_rate_delta") or 0.0) < 0:
        blockers.append("reliability_regressed")
    if float(comparison.get("pollution_pct_delta") or 0.0) > 0:
        blockers.append("pollution_regressed")
    if float(comparison.get("reopen_rate_delta") or 0.0) > 0:
        blockers.append("reopen_regressed")
    return sorted(set(blockers))


def _is_more_data_blocker(blockers: list[str]) -> bool:
    more_data = {"receipt_chain_not_pass", "provider_token_truth_not_clean", "comparison_row_not_pass"}
    return any(blocker in more_data for blocker in blockers)


def _should_replace_primary(row: Mapping[str, Any], comparison: Mapping[str, Any]) -> bool:
    if str(row.get("intended_action") or "").lower() == "add_to_multi":
        return False
    return _cost_better(comparison) and int(comparison.get("evidence_seal_count_delta") or 0) >= 0


def _should_add_to_multi(row: Mapping[str, Any], comparison: Mapping[str, Any]) -> bool:
    if str(row.get("intended_action") or "").lower() == "replace_primary":
        return False
    evidence_delta = int(comparison.get("evidence_seal_count_delta") or 0)
    if evidence_delta <= 0:
        return False
    return str(row.get("role") or "").lower() in {"scout", "logic", "audit", "guard"}


def _cost_better(comparison: Mapping[str, Any]) -> bool:
    return int(comparison.get("token_delta") or 0) < 0 and float(comparison.get("wall_delta") or 0.0) <= 0


def _challenger_arm(row: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    candidate = str(row["skill_id"])
    if str(row.get("intended_action") or "").lower() == "add_to_multi":
        skill_ids = list(baseline.get("current_selected_skill_ids") or [baseline["current_primary_skill_id"]])
        if candidate not in skill_ids:
            skill_ids.append(candidate)
        return {"mode": "candidate_multi_skill", "skill_ids": skill_ids}
    return {"mode": "candidate_single_skill", "skill_ids": [candidate]}


def _classify_capability(row: Mapping[str, Any], baselines: Mapping[str, Mapping[str, Any]]) -> str:
    for value in row.get("capability_hints", []) or []:
        if str(value) in baselines:
            return str(value)
    explicit = str(row.get("capability") or row.get("capability_id") or "")
    if explicit in baselines:
        return explicit
    blob = f"{row.get('skill_id', '')} {row.get('name', '')} {row.get('description', '')}".lower()
    for capability in sorted(baselines, key=len, reverse=True):
        if capability.lower() in blob:
            return capability
    return ""


def _infer_source_tier(skill_id: str, source_path: str) -> str:
    blob = f"{skill_id} {source_path}".lower()
    if any(marker in blob for marker in QUARANTINE_MARKERS):
        return "quarantine"
    if ".agents/skills" in source_path or source_path.startswith("skills/"):
        return "repo_local_curated"
    return "approved_external_reference"


def _infer_role(skill_id: str) -> str:
    text = skill_id.lower()
    if any(term in text for term in ("audit", "security", "guard", "gate", "review")):
        return "Audit"
    if any(term in text for term in ("scan", "index", "research", "scout", "browser", "lookup")):
        return "Scout"
    return "Logic"


def _counts(values: Any) -> dict[str, int]:
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
    parser = argparse.ArgumentParser(description="Build SF-R new-skill replacement review pipeline artifact.")
    parser.add_argument("--sfv2", type=Path, default=DEFAULT_SFV2)
    parser.add_argument("--candidate-intake", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    candidate_intake = _read_json(args.candidate_intake) if args.candidate_intake else None
    payload = build_sf_replacement_review_pipeline(
        sfv2_pipeline=_read_json(args.sfv2),
        candidate_intake=candidate_intake,
    )
    if not args.dry_run:
        _write_json(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "capability_count": payload["summary"]["capability_count"],
                "candidate_intake_count": payload["summary"]["candidate_intake_count"],
                "comparison_queue_count": payload["summary"]["comparison_queue_count"],
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
