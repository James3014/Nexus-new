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

from nexus.app import research_flow_service
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_OVERLAY = Path("docs/reports/NEXUS_HEEP_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-20.json")
DEFAULT_SKILL_STATUS = Path("docs/reports/NEXUS_HEEP_RUNTIME_CURATION_STATUS_2026-05-20.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_HEEP_RUNTIME_POST_APPLY_SMOKE_2026-05-20.json")


def _runtime_receipt(capability: str) -> dict[str, Any]:
    return {
        "name": capability,
        "selected": True,
        "invoked": True,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
        "public_claim_safe": False,
        "evidence_refs": [f"heep_runtime_post_apply_smoke:{capability}"],
    }


def _chain(skill_id: str, requests: list[dict[str, Any]], contracts: list[dict[str, Any]]) -> dict[str, bool]:
    contract = next((item for item in contracts if item.get("skill_id") == skill_id), None)
    return {
        "selected": any(item.get("skill_id") == skill_id for item in requests),
        "injected": bool(contract),
        "used": bool(contract and "runtime_capability_receipt_confirmed" in (contract.get("load_reason_codes") or [])),
        "evidence_present": bool(contract and contract.get("evidence_refs")),
        "gate_passed": bool(contract),
        "outcome_contributed": bool(contract and contract.get("outcome_contributed")),
    }


def build_heep_runtime_post_apply_smoke(
    *,
    overlay: Mapping[str, Any],
    overlay_path: str,
    skill_status_report: str,
) -> dict[str, Any]:
    assemblies = overlay.get("skill_assembly_by_capability")
    assemblies = assemblies if isinstance(assemblies, Mapping) else {}
    cases: list[dict[str, Any]] = []
    blockers: list[str] = []
    for capability in sorted(str(item) for item in assemblies):
        expected = [
            str(item.get("skill_id") if isinstance(item, Mapping) else item)
            for item in assemblies.get(capability, []) or []
            if str(item.get("skill_id") if isinstance(item, Mapping) else item)
        ]
        requests = CapabilityPlanner._runtime_policy_overlay_skill_requests(
            budget={"runtime_skill_policy_overlay_path": overlay_path},
            selected_capabilities=[capability],
        )
        planned = CapabilityPlanner._build_skill_mount_evidence(
            skills=requests,
            budget={"skill_status_report": skill_status_report},
            selected_capabilities=[capability],
        )
        plan_payload = {
            "selected_capabilities": [capability],
            "signal_snapshot": {
                "planned_skill_mount_contracts": planned.get("skill_mount_contracts", []),
                "skill_mount_violations": planned.get("skill_mount_violations", []),
            },
        }
        runtime = research_flow_service._build_runtime_skill_mount_contracts(
            capability_plan_payload=plan_payload,
            route_decision_payload={"task_id": f"heep-post-apply-smoke-{capability}"},
            capability_receipts=[_runtime_receipt(capability)],
        )
        contracts = [item for item in runtime.get("skill_mount_contracts", []) or [] if isinstance(item, Mapping)]
        violations = [item for item in runtime.get("skill_mount_violations", []) or [] if isinstance(item, Mapping)]
        got = [item.get("skill_id") for item in requests]
        chains = {skill_id: _chain(skill_id, requests, contracts) for skill_id in expected}
        status = "PASS" if got == expected and not violations and all(all(chain.values()) for chain in chains.values()) else "RETURN"
        if status != "PASS":
            blockers.append(f"{capability}:post_apply_smoke_return")
        cases.append(
            {
                "capability": capability,
                "expected_skill_ids": expected,
                "requested_skill_ids": got,
                "runtime_final_receipt_chain_by_skill": chains,
                "blocking_skill_mount_violations": violations,
                "status": status,
            }
        )
    status = "PASS" if cases and all(case["status"] == "PASS" for case in cases) and not blockers else "RETURN"
    return {
        "schema": "nexus.heep_runtime_post_apply_smoke.v1",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "summary": {
            "case_count": len(cases),
            "pass_count": sum(1 for case in cases if case["status"] == "PASS"),
            "return_count": sum(1 for case in cases if case["status"] != "PASS"),
            "runtime_update_allowed": status == "PASS",
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "cases": cases,
        "claim_boundary": [
            "Post-apply smoke validates HEEP overlay routing and runtime receipt construction.",
            "It is not a public benchmark.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the applied HEEP runtime overlay.")
    parser.add_argument("--overlay", default=str(DEFAULT_OVERLAY))
    parser.add_argument("--skill-status-report", default=str(DEFAULT_SKILL_STATUS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    smoke = build_heep_runtime_post_apply_smoke(
        overlay=read_json(args.overlay),
        overlay_path=args.overlay,
        skill_status_report=args.skill_status_report,
    )
    write_json(args.output, smoke)
    print(json.dumps({"status": smoke["status"], "output": args.output, **smoke["summary"]}, sort_keys=True))
    return 0 if smoke["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
