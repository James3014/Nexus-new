#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SFV2 = PROJECT_ROOT / "docs/reports/NEXUS_SFV2_SKILL_SELECTION_PIPELINE_2026-05-20.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs/reports/NEXUS_SFV2_ROLE_ABLATION_PROBE_2026-05-20.json"


def build_sfv2_role_ablation_probe(*, sfv2_pipeline: Mapping[str, Any]) -> dict[str, Any]:
    approved_rows = [
        row
        for row in sfv2_pipeline.get("rows", []) or []
        if isinstance(row, Mapping)
        and row.get("m6_mat_b_decision", {}).get("decision_state") == "APPROVE_MULTI_ASSEMBLY"
    ]
    rows = [_probe_row(row) for row in approved_rows]
    blockers = [
        f"{row['capability']}:missing_role_ablation_matrix"
        for row in rows
        if not row.get("arms")
    ]
    return {
        "schema": "nexus.sfv2_role_ablation_probe.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": {
            "approved_multi_assembly_count": len(rows),
            "arm_count": sum(len(row.get("arms") or []) for row in rows),
            "ready_for_live_role_ablation_count": sum(
                1 for row in rows if row["role_contribution_state"] == "READY_FOR_LIVE_ROLE_ABLATION"
            ),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "blockers": blockers,
        "claim_boundary": [
            "This artifact completes the local role-ablation probe and execution plan for approved multi-skill assemblies.",
            "It does not claim role contribution is live-proven until full/minus-role arms produce clean MAT-B receipts.",
            "Runtime defaults and public benchmark remain blocked by their independent gates.",
        ],
    }


def _probe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    capability = str(row.get("capability") or "")
    ablation = row.get("m5_role_ablation", {}) if isinstance(row.get("m5_role_ablation"), Mapping) else {}
    mat_b = row.get("m6_mat_b_decision", {}) if isinstance(row.get("m6_mat_b_decision"), Mapping) else {}
    arms = [_arm(capability, item) for item in ablation.get("matrix", []) or [] if isinstance(item, Mapping)]
    full_arm = next((arm for arm in arms if arm["arm_id"] == "full_assembly"), {})
    minus_arms = [arm for arm in arms if arm["arm_id"] != "full_assembly"]
    return {
        "capability": capability,
        "selected_mode": str(row.get("m4_multi_skill_assembly", {}).get("mode") or ""),
        "role_contribution_state": "READY_FOR_LIVE_ROLE_ABLATION" if full_arm and minus_arms else "MISSING_ABLATION_ARMS",
        "baseline_mat_b_verdict": mat_b.get("verdict"),
        "baseline_mat_b_delta": mat_b.get("delta") if isinstance(mat_b.get("delta"), Mapping) else {},
        "arms": arms,
        "decision_rule": [
            "full_assembly must pass reliability, quality, governance, regression, and provider-token gates",
            "every minus-role arm must be compared against full_assembly on the same task family",
            "role contribution is proven only when dropping a role worsens at least one correctness or governance KPI without improving a higher-priority gate",
            "token/wall improvements cannot override reliability, quality, governance, or regression loss",
        ],
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _arm(capability: str, item: Mapping[str, Any]) -> dict[str, Any]:
    skill_ids = [str(skill) for skill in item.get("skill_ids", []) or [] if str(skill)]
    arm_id = str(item.get("arm_id") or "")
    dropped_role = str(item.get("dropped_role") or "")
    return {
        "row_id": f"sfv2-role-ablation::{capability}::{arm_id}",
        "arm_id": arm_id,
        "dropped_role": dropped_role,
        "skill_ids": skill_ids,
        "runner_env": {
            "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
            "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps(skill_ids, ensure_ascii=False),
            "NEXUS_SFV2_ROLE_ABLATION_ARM": arm_id,
            "NEXUS_SFV2_DROPPED_ROLE": dropped_role,
        },
        "required_receipt_keys": [
            "selected",
            "injected",
            "used",
            "evidence_present",
            "gate_passed",
            "outcome_contributed",
        ],
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SFV2 role-ablation probe rows for approved multi-skill assemblies.")
    parser.add_argument("--sfv2", type=Path, default=DEFAULT_SFV2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = build_sfv2_role_ablation_probe(sfv2_pipeline=_read_json(args.sfv2))
    if not args.dry_run:
        _write_json(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "approved_multi_assembly_count": payload["summary"]["approved_multi_assembly_count"],
                "arm_count": payload["summary"]["arm_count"],
                "ready_for_live_role_ablation_count": payload["summary"]["ready_for_live_role_ablation_count"],
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
