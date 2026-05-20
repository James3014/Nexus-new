#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORIGINAL_MAP = PROJECT_ROOT / "docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.json"
DEFAULT_ASSEMBLY = PROJECT_ROOT / "docs/reports/NEXUS_HEEP_ASSEMBLY_CATALOG_2026-05-20.json"
DEFAULT_MAT_B = PROJECT_ROOT / "docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json"
DEFAULT_QUEUE = PROJECT_ROOT / "docs/reports/NEXUS_HEEP_FLASH_NEXUS_LIVE_COMPARE_QUEUE_2026-05-20.json"
DEFAULT_RUNTIME_OVERLAY = PROJECT_ROOT / "docs/reports/NEXUS_HEEP_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-20.json"
DEFAULT_POST_APPLY_SMOKE = PROJECT_ROOT / "docs/reports/NEXUS_HEEP_RUNTIME_POST_APPLY_SMOKE_2026-05-20.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs/reports/NEXUS_SFV2_SKILL_SELECTION_PIPELINE_2026-05-20.json"

MODE_A = "Mode A (Solo)"
MODE_B = "Mode B (Guard)"
MODE_C = "Mode C (Swarm)"

RECEIPT_KEYS = (
    "selected",
    "injected",
    "used",
    "evidence_present",
    "gate_passed",
    "outcome_contributed",
)


def build_sfv2_skill_selection_pipeline(
    *,
    original_map: Mapping[str, Any],
    assembly_catalog: Mapping[str, Any],
    mat_b_report: Mapping[str, Any],
    compare_queue: Mapping[str, Any],
    runtime_overlay: Mapping[str, Any],
    post_apply_smoke: Mapping[str, Any],
) -> dict[str, Any]:
    original_rows = _index_by(original_map.get("rows", []), "capability")
    assembly_rows = _index_by(assembly_catalog.get("rows", []), "capability")
    mat_b_rows = _index_by(mat_b_report.get("comparisons", []), "capability")
    queue_rows = _index_by(compare_queue.get("rows", []), "capability")
    smoke_rows = _index_by(post_apply_smoke.get("cases", []), "capability")

    capability_ids = sorted(set(original_rows) | set(assembly_rows) | set(mat_b_rows) | set(queue_rows))
    rows = [
        _capability_row(
            capability=capability,
            original=original_rows.get(capability, {}),
            assembly=assembly_rows.get(capability, {}),
            mat_b=mat_b_rows.get(capability, {}),
            queue=queue_rows.get(capability, {}),
            runtime_overlay=runtime_overlay,
            post_apply_smoke=smoke_rows.get(capability, {}),
        )
        for capability in capability_ids
    ]
    blockers = _pipeline_blockers(rows)
    return {
        "schema": "nexus.sfv2_skill_selection_pipeline.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": _summary(rows),
        "milestones": _milestones(rows, blockers),
        "rows": rows,
        "blockers": blockers,
        "claim_boundary": [
            "SFV2 automates skill intake, shortlist, single-vs-multi decision, role-ablation queue, catalog writeback candidates, and runtime apply review packets.",
            "SFV2 does not turn internal HEEP/MAT-B evidence into public benchmark or publication-ready claims.",
            "Runtime defaults remain gated by runtime-confirmed selected/injected/used/evidence/gate/outcome receipts and provider-token truth.",
        ],
    }


def _capability_row(
    *,
    capability: str,
    original: Mapping[str, Any],
    assembly: Mapping[str, Any],
    mat_b: Mapping[str, Any],
    queue: Mapping[str, Any],
    runtime_overlay: Mapping[str, Any],
    post_apply_smoke: Mapping[str, Any],
) -> dict[str, Any]:
    primary = str(original.get("primary_skill_id") or assembly.get("primary_skill_id") or "")
    mode = str(assembly.get("recommended_mode") or queue.get("challenger_arm", {}).get("mode") or MODE_A)
    assembly_items = _assembly_items(assembly, queue, primary)
    source_class = _source_class(original)
    mat_b_decision = _mat_b_decision(mat_b)
    role_ablation = _role_ablation(capability=capability, mode=mode, assembly_items=assembly_items, mat_b_decision=mat_b_decision)
    runtime_review = _runtime_review(
        capability=capability,
        mat_b_decision=mat_b_decision,
        runtime_overlay=runtime_overlay,
        post_apply_smoke=post_apply_smoke,
    )
    return {
        "capability": capability,
        "m1_intake": {
            "primary_skill_id": primary,
            "original_skill_name": str(original.get("original_skill_name") or primary),
            "source_class": source_class,
            "source_path": str(original.get("original_source_path") or ""),
            "eligible_for_discovery": source_class != "quarantine",
            "eligible_for_runtime_direct_mount": source_class in {"repo_local_curated", "current_best"},
        },
        "m2_shortlist": _shortlist(primary, assembly_items),
        "m3_single_skill_tournament": _single_skill_decision(mat_b_decision),
        "m4_multi_skill_assembly": {
            "mode": mode,
            "assembly": assembly_items,
            "assembly_kind": _assembly_kind(mode),
        },
        "m5_role_ablation": role_ablation,
        "m6_mat_b_decision": mat_b_decision,
        "m7_catalog_update": _catalog_update(capability, primary, assembly_items, mat_b_decision),
        "m8_runtime_apply_review": runtime_review,
    }


def _source_class(original: Mapping[str, Any]) -> str:
    skill_id = str(original.get("primary_skill_id") or "")
    source_path = str(original.get("original_source_path") or "")
    source_root = str(original.get("source_round_or_root") or "")
    blob = f"{skill_id} {source_path} {source_root}".lower()
    if any(term in blob for term in ("candidate-skill-from-", "auto-gen-", ".codexworktrees", "worktree", "archive")):
        return "quarantine"
    if source_root.startswith("round") or source_path.startswith("/private/tmp/"):
        return "approved_external_reference"
    if source_root in {"current_best", "repo_local", "nexus_curated"}:
        return "current_best"
    if ".agents/skills" in source_path or source_path.startswith("skills/"):
        return "repo_local_curated"
    return "unknown_reference"


def _assembly_items(assembly: Mapping[str, Any], queue: Mapping[str, Any], primary: str) -> list[dict[str, str]]:
    items = assembly.get("assembly")
    if isinstance(items, list) and items:
        return [
            {"role": str(item.get("role") or "skill"), "skill_id": str(item.get("skill_id") or "")}
            for item in items
            if isinstance(item, Mapping) and str(item.get("skill_id") or "")
        ]
    challenger = queue.get("challenger_arm", {}) if isinstance(queue.get("challenger_arm"), Mapping) else {}
    skill_ids = [str(item) for item in challenger.get("skill_ids", []) or [] if str(item)]
    if not skill_ids and primary:
        skill_ids = [primary]
    return [{"role": f"skill_{index + 1}", "skill_id": skill_id} for index, skill_id in enumerate(skill_ids)]


def _shortlist(primary: str, assembly_items: list[dict[str, str]]) -> dict[str, Any]:
    challenger_ids = [item["skill_id"] for item in assembly_items if item["skill_id"] and item["skill_id"] != primary]
    return {
        "current_primary": primary,
        "single_challengers": _dedupe(challenger_ids),
        "multi_role_candidates": assembly_items,
        "negative_control_required": True,
        "shortlist_complete": bool(primary),
    }


def _single_skill_decision(mat_b_decision: Mapping[str, Any]) -> dict[str, Any]:
    state = str(mat_b_decision.get("decision_state") or "")
    if state == "KEEP_SINGLE_PRIMARY":
        decision = "KEEP_SINGLE_PRIMARY"
    elif state == "REJECT_CANDIDATE":
        decision = "KEEP_SINGLE_PRIMARY_REJECT_MULTI"
    elif state == "APPROVE_MULTI_ASSEMBLY":
        decision = "NO_SINGLE_REPLACEMENT_MULTI_ASSEMBLY_WINS"
    elif state.startswith("HOLD_"):
        decision = state
    else:
        decision = "NEEDS_MORE_CANDIDATES"
    return {
        "decision": decision,
        "cost_read_after_correctness_only": True,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _role_ablation(
    *,
    capability: str,
    mode: str,
    assembly_items: list[dict[str, str]],
    mat_b_decision: Mapping[str, Any],
) -> dict[str, Any]:
    if mode == MODE_A or len(assembly_items) <= 1:
        return {
            "status": "NOT_REQUIRED_FOR_SOLO",
            "matrix": [],
            "contribution_gate": "solo_mode",
        }
    full_skills = [item["skill_id"] for item in assembly_items]
    matrix = [
        {
            "arm_id": "full_assembly",
            "dropped_role": "",
            "skill_ids": full_skills,
        }
    ]
    for item in assembly_items:
        matrix.append(
            {
                "arm_id": f"minus_{_slug(item['role'])}",
                "dropped_role": item["role"],
                "skill_ids": [skill["skill_id"] for skill in assembly_items if skill["skill_id"] != item["skill_id"]],
            }
        )
    state = str(mat_b_decision.get("decision_state") or "")
    if state == "APPROVE_MULTI_ASSEMBLY":
        status = "READY_FOR_ROLE_CONTRIBUTION_REPLAY"
    elif state.startswith("HOLD_"):
        status = "BLOCKED_UNTIL_MAT_B_CLEAN"
    else:
        status = "MATRIX_GENERATED_NOT_SELECTED"
    return {
        "status": status,
        "matrix": matrix,
        "contribution_gate": "full assembly must beat every minus-role arm before public/default claims",
        "capability": capability,
    }


def _mat_b_decision(mat_b: Mapping[str, Any]) -> dict[str, Any]:
    verdict = str(mat_b.get("verdict") or "MISSING_MAT_B")
    reasons = [str(item) for item in mat_b.get("reason_codes", []) or []]
    if verdict == "APPROVE_HEEP_MODE_CANDIDATE":
        state = "APPROVE_MULTI_ASSEMBLY"
    elif verdict == "KEEP_SINGLE_PRIMARY":
        state = "KEEP_SINGLE_PRIMARY"
    elif verdict == "REJECT_MULTI_SKILL":
        state = "REJECT_CANDIDATE"
    elif "PROVIDER_TOKEN" in verdict or any("model_call_without_tokens" in item for item in reasons):
        state = "HOLD_PROVIDER_TOKEN_TRUTH"
    elif "RECEIPT" in verdict or any("receipt_data_contract" in item for item in reasons):
        state = "HOLD_RECEIPT_CHAIN"
    elif verdict == "MISSING_MAT_B":
        state = "NEEDS_MORE_CANDIDATES"
    else:
        state = "NEEDS_MORE_CANDIDATES"
    return {
        "verdict": verdict,
        "reason_codes": reasons,
        "decision_state": state,
        "correctness_before_cost": True,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "baseline": mat_b.get("baseline", {}) if isinstance(mat_b.get("baseline"), Mapping) else {},
        "challenger": mat_b.get("challenger", {}) if isinstance(mat_b.get("challenger"), Mapping) else {},
        "delta": mat_b.get("delta", {}) if isinstance(mat_b.get("delta"), Mapping) else {},
    }


def _catalog_update(
    capability: str,
    primary: str,
    assembly_items: list[dict[str, str]],
    mat_b_decision: Mapping[str, Any],
) -> dict[str, Any]:
    state = str(mat_b_decision.get("decision_state") or "")
    if state == "APPROVE_MULTI_ASSEMBLY":
        selected = [item["skill_id"] for item in assembly_items]
        action = "set_capability_multi_skill_candidate"
    elif state in {"KEEP_SINGLE_PRIMARY", "REJECT_CANDIDATE"}:
        selected = [primary] if primary else []
        action = "retain_single_primary"
    elif state.startswith("HOLD_"):
        selected = [primary] if primary else []
        action = "write_hold_and_replay_queue"
    else:
        selected = [primary] if primary else []
        action = "request_more_candidates"
    return {
        "capability": capability,
        "planned_action": action,
        "selected_skill_ids": selected,
        "catalog_update_allowed": True,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _runtime_review(
    *,
    capability: str,
    mat_b_decision: Mapping[str, Any],
    runtime_overlay: Mapping[str, Any],
    post_apply_smoke: Mapping[str, Any],
) -> dict[str, Any]:
    state = str(mat_b_decision.get("decision_state") or "")
    applied = capability in (runtime_overlay.get("skill_assembly_by_capability") or {})
    smoke_status = str(post_apply_smoke.get("status") or "")
    if state == "APPROVE_MULTI_ASSEMBLY" and applied and smoke_status == "PASS":
        review_state = "RUNTIME_OVERLAY_SMOKE_PASS"
    elif state == "APPROVE_MULTI_ASSEMBLY":
        review_state = "READY_FOR_RUNTIME_APPLY_REVIEW"
    elif state.startswith("HOLD_"):
        review_state = "BLOCKED"
    else:
        review_state = "NO_RUNTIME_APPLY_NEEDED"
    return {
        "review_state": review_state,
        "overlay_applied": applied,
        "post_apply_smoke_status": smoke_status,
        "runtime_update_allowed": state == "APPROVE_MULTI_ASSEMBLY" and applied and smoke_status == "PASS",
        "public_benchmark_allowed": False,
    }


def _assembly_kind(mode: str) -> str:
    if mode == MODE_B:
        return "primary_plus_guard"
    if mode == MODE_C:
        return "scout_logic_audit"
    return "single_primary"


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    decisions = [str(row["m6_mat_b_decision"]["decision_state"]) for row in rows]
    source_classes: dict[str, int] = {}
    for row in rows:
        source_class = str(row["m1_intake"]["source_class"])
        source_classes[source_class] = source_classes.get(source_class, 0) + 1
    return {
        "capability_count": len(rows),
        "source_class_counts": source_classes,
        "approve_multi_assembly_count": decisions.count("APPROVE_MULTI_ASSEMBLY"),
        "keep_single_primary_count": decisions.count("KEEP_SINGLE_PRIMARY"),
        "reject_candidate_count": decisions.count("REJECT_CANDIDATE"),
        "hold_provider_token_truth_count": decisions.count("HOLD_PROVIDER_TOKEN_TRUTH"),
        "hold_receipt_chain_count": decisions.count("HOLD_RECEIPT_CHAIN"),
        "needs_more_candidates_count": decisions.count("NEEDS_MORE_CANDIDATES"),
        "role_ablation_matrix_count": sum(len(row["m5_role_ablation"]["matrix"]) for row in rows),
        "runtime_review_ready_or_applied_count": sum(
            1
            for row in rows
            if row["m8_runtime_apply_review"]["review_state"]
            in {"READY_FOR_RUNTIME_APPLY_REVIEW", "RUNTIME_OVERLAY_SMOKE_PASS"}
        ),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _milestones(rows: list[Mapping[str, Any]], blockers: list[str]) -> dict[str, Any]:
    return {
        "M1_skill_source_tiering": _milestone("PASS", "all candidates classified", len(rows)),
        "M2_capability_shortlist": _milestone("PASS", "current primary and challenger shortlist generated", len(rows)),
        "M3_single_skill_tournament": _milestone("PASS", "single-skill decision states derived from MAT-B", len(rows)),
        "M4_multi_role_ablation": _milestone(
            "PASS",
            "role-drop matrices generated for every non-solo assembly",
            sum(len(row["m5_role_ablation"]["matrix"]) for row in rows),
        ),
        "M5_mat_b_decision_gate": _milestone("PASS", "MAT-B decision states normalized", len(rows)),
        "M6_catalog_map_ledger_update": _milestone("PASS", "catalog update actions generated", len(rows)),
        "M7_runtime_apply_review_packet": _milestone("PASS", "runtime apply review states generated", len(rows)),
        "M8_public_gate_separation": {
            "status": "PASS",
            "gate": "public_benchmark_allowed=false",
            "evidence": "internal SFV2/HEEP evidence remains separate from public benchmark claims",
        },
        "blocker_policy": {
            "status": "PASS" if not blockers else "RETURN",
            "blockers": blockers,
        },
    }


def _milestone(status: str, gate: str, count: int) -> dict[str, Any]:
    return {"status": status, "gate": gate, "count": count}


def _pipeline_blockers(rows: list[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for row in rows:
        capability = str(row["capability"])
        if not row["m2_shortlist"]["shortlist_complete"]:
            blockers.append(f"{capability}:missing_primary_skill")
        if row["m1_intake"]["source_class"] == "quarantine":
            blockers.append(f"{capability}:quarantined_primary_skill")
    return blockers


def _index_by(items: Any, key: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(items, list):
        return {}
    out: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if isinstance(item, Mapping) and item.get(key):
            out[str(item.get(key))] = item
    return out


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "role"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the SFV2 single/multi skill selection pipeline artifact.")
    parser.add_argument("--original-map", type=Path, default=DEFAULT_ORIGINAL_MAP)
    parser.add_argument("--assembly", type=Path, default=DEFAULT_ASSEMBLY)
    parser.add_argument("--mat-b", type=Path, default=DEFAULT_MAT_B)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--runtime-overlay", type=Path, default=DEFAULT_RUNTIME_OVERLAY)
    parser.add_argument("--post-apply-smoke", type=Path, default=DEFAULT_POST_APPLY_SMOKE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = build_sfv2_skill_selection_pipeline(
        original_map=_read_json(args.original_map),
        assembly_catalog=_read_json(args.assembly),
        mat_b_report=_read_json(args.mat_b),
        compare_queue=_read_json(args.queue),
        runtime_overlay=_read_json(args.runtime_overlay) if args.runtime_overlay.exists() else {},
        post_apply_smoke=_read_json(args.post_apply_smoke) if args.post_apply_smoke.exists() else {},
    )
    if not args.dry_run:
        _write_json(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "capability_count": payload["summary"]["capability_count"],
                "role_ablation_matrix_count": payload["summary"]["role_ablation_matrix_count"],
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
