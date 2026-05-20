#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_CURRENT_OVERLAY = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json")
DEFAULT_REVIEWED_GATE = Path("docs/reports/NEXUS_HEEP_RUNTIME_APPLY_GATE_REVIEWED_2026-05-20.json")
DEFAULT_DECISION = Path("docs/reports/NEXUS_HEEP_RUNTIME_DEFAULT_APPLY_DECISION_2026-05-20.json")
DEFAULT_OVERLAY = Path("docs/reports/NEXUS_HEEP_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-20.json")


def _passing_cases(reviewed_gate: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(case)
        for case in reviewed_gate.get("cases", []) or []
        if isinstance(case, Mapping) and str(case.get("status") or "") == "PASS"
    ]


def _assembly_for_case(case: Mapping[str, Any]) -> list[dict[str, str]]:
    assembly = []
    for check in case.get("skill_checks", []) or []:
        if not isinstance(check, Mapping):
            continue
        skill_id = str(check.get("skill_id") or "").strip()
        if not skill_id:
            continue
        assembly.append({"role": f"skill_{len(assembly) + 1}", "skill_id": skill_id})
    return assembly


def build_heep_runtime_default_apply_decision(
    *,
    current_overlay: Mapping[str, Any],
    reviewed_gate: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if reviewed_gate.get("status") != "PASS":
        blockers.append("reviewed_apply_gate_not_pass")
    primary = dict(current_overlay.get("primary_skill_by_capability") or {})
    candidate_primary = dict(current_overlay.get("candidate_primary_skill_by_capability") or primary)
    assembly_by_capability = dict(current_overlay.get("skill_assembly_by_capability") or {})
    mode_by_capability = dict(current_overlay.get("heep_mode_by_capability") or {})
    applied_rows = []
    for case in _passing_cases(reviewed_gate):
        capability = str(case.get("capability") or "")
        assembly = _assembly_for_case(case)
        if not capability or not assembly:
            blockers.append(f"{capability or 'unknown'}:empty_assembly")
            continue
        assembly_by_capability[capability] = assembly
        mode_by_capability[capability] = str(case.get("selected_mode") or "")
        primary[capability] = assembly[0]["skill_id"]
        candidate_primary[capability] = assembly[0]["skill_id"]
        applied_rows.append(
            {
                "capability": capability,
                "selected_mode": str(case.get("selected_mode") or ""),
                "primary_skill_id": assembly[0]["skill_id"],
                "assembly": assembly,
                "runtime_apply_status": "APPLIED_TO_OVERLAY",
            }
        )
    runtime_update_allowed = bool(applied_rows and not blockers)
    overlay = {
        "schema": "nexus.heep_runtime_skill_policy_overlay.applied.v1",
        "status": "PASS" if runtime_update_allowed else "RETURN",
        "created_at": datetime.now(UTC).isoformat(),
        "primary_skill_by_capability": dict(sorted(primary.items())),
        "candidate_primary_skill_by_capability": dict(sorted(candidate_primary.items())),
        "skill_assembly_by_capability": dict(sorted(assembly_by_capability.items())),
        "heep_mode_by_capability": dict(sorted(mode_by_capability.items())),
        "applied_heep_assemblies": sorted(applied_rows, key=lambda item: item["capability"]),
        "runtime_update_allowed": runtime_update_allowed,
        "public_benchmark_allowed": False,
        "claim_boundary": [
            "This overlay applies reviewed HEEP assemblies for runtime routing input.",
            "It does not claim public benchmark readiness.",
            "Runtime routes must still emit final selected/injected/used/evidence/gate/outcome receipts.",
        ],
        "blockers": sorted(set(blockers)),
    }
    decision = {
        "schema": "nexus.heep_runtime_default_apply_decision.v1",
        "status": overlay["status"],
        "created_at": overlay["created_at"],
        "summary": {
            "applied_assembly_count": len(applied_rows),
            "blocker_count": len(sorted(set(blockers))),
            "runtime_update_allowed": runtime_update_allowed,
            "public_benchmark_allowed": False,
        },
        "applied_heep_assemblies": overlay["applied_heep_assemblies"],
        "overlay_output_schema": overlay["schema"],
        "blockers": overlay["blockers"],
        "claim_boundary": overlay["claim_boundary"],
    }
    return {"decision": decision, "overlay": overlay}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build HEEP runtime default apply decision and overlay artifact.")
    parser.add_argument("--current-overlay", default=str(DEFAULT_CURRENT_OVERLAY))
    parser.add_argument("--reviewed-gate", default=str(DEFAULT_REVIEWED_GATE))
    parser.add_argument("--decision-output", default=str(DEFAULT_DECISION))
    parser.add_argument("--overlay-output", default=str(DEFAULT_OVERLAY))
    args = parser.parse_args(argv)
    result = build_heep_runtime_default_apply_decision(
        current_overlay=read_json(args.current_overlay),
        reviewed_gate=read_json(args.reviewed_gate),
    )
    write_json(args.decision_output, result["decision"])
    write_json(args.overlay_output, result["overlay"])
    print(
        json.dumps(
            {
                "status": result["decision"]["status"],
                "decision_output": args.decision_output,
                "overlay_output": args.overlay_output,
                **result["decision"]["summary"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["decision"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
