#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nexus.app import research_flow_service
from nexus.engine.capability_planner import CapabilityPlanner


DEFAULT_OVERLAY = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json")
DEFAULT_SKILL_STATUS = Path("docs/reports/NEXUS_SF_SYSTEMATIC_BATCH_SKILL_STATUS_2026-05-19.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json")


def _runtime_receipt(capability: str) -> dict[str, Any]:
    return {
        "name": capability,
        "selected": True,
        "invoked": True,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
        "public_claim_safe": False,
        "evidence_refs": [f"sf_current_overlay_smoke:{capability}"],
    }


def build_smoke(*, overlay_path: Path, skill_status_report: Path) -> dict[str, Any]:
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    primary = overlay.get("primary_skill_by_capability")
    primary = primary if isinstance(primary, dict) else {}
    cases: list[dict[str, Any]] = []
    for capability, expected_skill in sorted(primary.items()):
        capability_id = str(capability)
        skill_id = str(expected_skill)
        budget = {
            "runtime_skill_policy_overlay": overlay,
            "skill_status_report": str(skill_status_report),
        }
        requests = CapabilityPlanner._runtime_policy_overlay_skill_requests(
            budget=budget,
            selected_capabilities=[capability_id],
        )
        evidence = CapabilityPlanner._build_skill_mount_evidence(
            skills=requests,
            budget=budget,
            selected_capabilities=[capability_id],
        )
        plan_payload = {
            "selected_capabilities": [capability_id],
            "signal_snapshot": {
                "planned_skill_mount_contracts": evidence.get("skill_mount_contracts", []),
                "skill_mount_violations": evidence.get("skill_mount_violations", []),
            },
        }
        runtime = research_flow_service._build_runtime_skill_mount_contracts(
            capability_plan_payload=plan_payload,
            route_decision_payload={"task_id": f"sf-current-overlay-smoke-{capability_id}"},
            capability_receipts=[_runtime_receipt(capability_id)],
        )
        contracts = runtime.get("skill_mount_contracts", [])
        violations = runtime.get("skill_mount_violations", [])
        contract = next((item for item in contracts if item.get("skill_id") == skill_id), None)
        chain = {
            "selected": bool(requests),
            "injected": bool(contract),
            "used": bool(contract and "runtime_capability_receipt_confirmed" in (contract.get("load_reason_codes") or [])),
            "evidence_present": bool(contract and contract.get("evidence_refs")),
            "gate_passed": bool(contract),
            "outcome_contributed": bool(contract and contract.get("outcome_contributed")),
        }
        blocking_violations = [
            item for item in violations if isinstance(item, dict) and item.get("skill_name") == skill_id
        ]
        cases.append(
            {
                "capability": capability_id,
                "expected_skill": skill_id,
                "planned_requests": requests,
                "runtime_final_receipt_chain": chain,
                "blocking_skill_mount_violations": blocking_violations,
                "status": "PASS" if all(chain.values()) and not blocking_violations else "RETURN",
            }
        )
    return {
        "schema": "nexus.sf_current_overlay_runtime_smoke.v1",
        "status": "PASS" if cases and all(case["status"] == "PASS" for case in cases) else "RETURN",
        "created_at": datetime.now(UTC).isoformat(),
        "overlay_path": str(overlay_path),
        "skill_status_report": str(skill_status_report),
        "runtime_update_allowed": bool(cases) and all(case["status"] == "PASS" for case in cases),
        "public_benchmark_allowed": False,
        "summary": {
            "case_count": len(cases),
            "pass_count": sum(1 for case in cases if case["status"] == "PASS"),
            "return_count": sum(1 for case in cases if case["status"] != "PASS"),
        },
        "cases": cases,
        "claim_boundary": [
            "Runtime contract smoke only.",
            "This verifies overlay selection and final receipt-chain construction for all current SF capabilities.",
            "It is not a public benchmark claim.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the full SF current overlay against the skill catalog.")
    parser.add_argument("--overlay", default=str(DEFAULT_OVERLAY))
    parser.add_argument("--skill-status-report", default=str(DEFAULT_SKILL_STATUS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_smoke(overlay_path=Path(args.overlay), skill_status_report=Path(args.skill_status_report))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
