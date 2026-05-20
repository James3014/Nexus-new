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

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_QUEUE = Path("docs/reports/NEXUS_HEEP_FLASH_NEXUS_LIVE_COMPARE_QUEUE_2026-05-20.json")
DEFAULT_RESOLUTION = Path("docs/reports/NEXUS_HEEP_MAT_B_BLOCKED_MODE_RESOLUTION_2026-05-20.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_HEEP_MAT_B_FINAL_SKILL_DECISIONS_2026-05-20.json")

MULTI_WIN = "MULTI_SKILL_NON_COST_WIN"
RECEIPT_MISSING = "UNDECIDED_RECEIPT_CHAIN_MISSING"


def _skill_paths() -> dict[str, str]:
    paths: dict[str, str] = {}
    for path in sorted((PROJECT_ROOT / ".agents" / "skills").glob("**/SKILL.md")):
        skill_id = path.parent.name
        paths.setdefault(skill_id, str(path.relative_to(PROJECT_ROOT)))
    return paths


def _rows_by_capability(queue: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("capability") or ""): row
        for row in queue.get("rows", []) or []
        if isinstance(row, Mapping) and row.get("capability")
    }


def _resolutions_by_capability(resolution: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("capability") or ""): row
        for row in resolution.get("rows", []) or []
        if isinstance(row, Mapping) and row.get("capability")
    }


def _arm(row: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = row.get(key)
    return value if isinstance(value, Mapping) else {}


def _skill_ids(arm: Mapping[str, Any]) -> list[str]:
    return [str(item) for item in arm.get("skill_ids", []) or [] if str(item).strip()]


def _asset_status(skill_ids: list[str], skill_paths: Mapping[str, str]) -> tuple[str, list[str], list[str]]:
    missing = [skill_id for skill_id in skill_ids if skill_id not in skill_paths]
    paths = [skill_paths[skill_id] for skill_id in skill_ids if skill_id in skill_paths]
    return ("PASS" if not missing and skill_ids else "RETURN", paths, missing)


def _decision_for(
    *,
    capability: str,
    queue_row: Mapping[str, Any],
    resolution_row: Mapping[str, Any],
    skill_paths: Mapping[str, str],
) -> dict[str, Any]:
    baseline = _arm(queue_row, "baseline_arm")
    challenger = _arm(queue_row, "challenger_arm")
    mode_decision = str(resolution_row.get("mode_decision") or "")
    if mode_decision == MULTI_WIN:
        selected_mode = "multi_skill"
        selected_arm = challenger
        decision = "USE_MULTI_SKILL"
        reason = "multi_skill_has_stronger_non_cost_evidence"
    elif mode_decision == RECEIPT_MISSING:
        selected_mode = "single_primary"
        selected_arm = baseline
        decision = "USE_SINGLE_PRIMARY_FALLBACK"
        reason = "multi_skill_not_proven_until_executor_receipt_chain_passes"
    else:
        selected_mode = "single_primary"
        selected_arm = baseline
        decision = "USE_SINGLE_PRIMARY_FALLBACK"
        reason = "fallback_for_unrecognized_blocked_mode_decision"

    selected_skill_ids = _skill_ids(selected_arm)
    asset_status, selected_paths, missing = _asset_status(selected_skill_ids, skill_paths)
    return {
        "capability": capability,
        "decision": decision,
        "selected_mode": selected_mode,
        "selected_skill_ids": selected_skill_ids,
        "selected_skill_paths": selected_paths,
        "skill_asset_status": asset_status,
        "missing_skill_ids": missing,
        "reason": reason,
        "source_mode_decision": mode_decision,
        "root_cause": resolution_row.get("root_cause", ""),
        "evidence": {
            "baseline_skill_ids": _skill_ids(baseline),
            "challenger_skill_ids": _skill_ids(challenger),
            "baseline_planned_receipt_chain": baseline.get("runtime_final_receipt_chain", {}),
            "challenger_planned_receipt_chain": challenger.get("runtime_final_receipt_chain", {}),
            "evidence_seal_count_delta": resolution_row.get("evidence_seal_count_delta"),
            "wall_delta_observation": resolution_row.get("wall_delta_observation"),
        },
        "remaining_gate": resolution_row.get("remaining_gate", []),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def build_final_skill_decisions(
    *,
    live_compare_queue: Mapping[str, Any],
    blocked_mode_resolution: Mapping[str, Any],
) -> dict[str, Any]:
    skill_paths = _skill_paths()
    queue_rows = _rows_by_capability(live_compare_queue)
    resolution_rows = _resolutions_by_capability(blocked_mode_resolution)
    decisions = [
        _decision_for(
            capability=capability,
            queue_row=queue_rows.get(capability, {}),
            resolution_row=row,
            skill_paths=skill_paths,
        )
        for capability, row in sorted(resolution_rows.items())
    ]
    missing_assets = [row["capability"] for row in decisions if row["skill_asset_status"] != "PASS"]
    return {
        "schema": "nexus.heep_mat_b_final_skill_decisions.v1",
        "status": "PASS" if decisions and not missing_assets else "RETURN",
        "summary": {
            "capability_count": len(decisions),
            "multi_skill_decision_count": sum(1 for row in decisions if row["decision"] == "USE_MULTI_SKILL"),
            "single_primary_fallback_count": sum(
                1 for row in decisions if row["decision"] == "USE_SINGLE_PRIMARY_FALLBACK"
            ),
            "skill_asset_pass_count": sum(1 for row in decisions if row["skill_asset_status"] == "PASS"),
            "missing_asset_count": len(missing_assets),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "decisions": decisions,
        "claim_boundary": [
            "Every blocked capability has a usable skill or skill set for internal HEEP selection.",
            "Provider-token blockers can select multi-skill for non-cost use but cannot make cost or public claims.",
            "Receipt-chain blockers select the existing single primary fallback until executor receipt replay proves multi-skill.",
            "This artifact does not modify runtime defaults.",
        ],
        "source_reports": {
            "live_compare_queue": str(DEFAULT_QUEUE),
            "blocked_mode_resolution": str(DEFAULT_RESOLUTION),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build final HEEP MAT-B skill decisions for blocked capabilities.")
    parser.add_argument("--live-compare-queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--blocked-mode-resolution", default=str(DEFAULT_RESOLUTION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    report = build_final_skill_decisions(
        live_compare_queue=read_json(args.live_compare_queue),
        blocked_mode_resolution=read_json(args.blocked_mode_resolution),
    )
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], **report["summary"], "output": args.output}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
