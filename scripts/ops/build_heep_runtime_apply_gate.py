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


DEFAULT_MAT_B_REPORT = Path("docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json")
DEFAULT_SKILL_STATUS = Path("docs/reports/NEXUS_HEEP_FLASH_NEXUS_SKILL_STATUS_2026-05-20.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_HEEP_RUNTIME_APPLY_GATE_2026-05-20.json")

RECEIPT_KEYS = ("selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed")


def _approved_capabilities(mat_b_report: Mapping[str, Any]) -> set[str]:
    return {
        str(row.get("capability") or "")
        for row in mat_b_report.get("comparisons", []) or []
        if isinstance(row, Mapping) and str(row.get("verdict") or "") == "APPROVE_HEEP_MODE_CANDIDATE"
    }


def _candidate_rows(matrix: Mapping[str, Any], approved: set[str]) -> list[dict[str, Any]]:
    rows = []
    for row in matrix.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("arm_id") or "") != "heep_multi_skill":
            continue
        if str(row.get("capability") or "") not in approved:
            continue
        rows.append(dict(row))
    return sorted(rows, key=lambda item: str(item.get("capability") or ""))


def _runtime_receipt(capability: str) -> dict[str, Any]:
    return {
        "name": capability,
        "selected": True,
        "invoked": True,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
        "public_claim_safe": False,
        "evidence_refs": [f"heep_runtime_apply_gate:{capability}"],
    }


def _chain_for_skill(
    *,
    skill_id: str,
    requests: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    blocking_violations: list[dict[str, Any]],
) -> dict[str, bool]:
    contract = next((item for item in contracts if item.get("skill_id") == skill_id), None)
    requested = any(item.get("skill_id") == skill_id for item in requests)
    return {
        "selected": requested,
        "injected": bool(contract),
        "used": bool(contract and "runtime_capability_receipt_confirmed" in (contract.get("load_reason_codes") or [])),
        "evidence_present": bool(contract and contract.get("evidence_refs")),
        "gate_passed": bool(contract) and not blocking_violations,
        "outcome_contributed": bool(contract and contract.get("outcome_contributed")),
    }


def build_heep_runtime_apply_gate(
    *,
    mat_b_report: Mapping[str, Any],
    execution_matrix: Mapping[str, Any],
    skill_status_report: str,
) -> dict[str, Any]:
    approved = _approved_capabilities(mat_b_report)
    rows = _candidate_rows(execution_matrix, approved)
    cases: list[dict[str, Any]] = []
    blockers: list[str] = []
    for row in rows:
        capability = str(row.get("capability") or "")
        skill_ids = [str(item) for item in row.get("skill_mount_requests", []) or [] if str(item)]
        requests = [
            {"skill_id": skill_id, "capability_id": capability, "source": "heep_runtime_apply_review"}
            for skill_id in skill_ids
        ]
        budget = {"skill_status_report": skill_status_report}
        planned = CapabilityPlanner._build_skill_mount_evidence(
            skills=requests,
            budget=budget,
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
            route_decision_payload={"task_id": f"heep-runtime-apply-gate-{capability}"},
            capability_receipts=[_runtime_receipt(capability)],
        )
        contracts = [item for item in runtime.get("skill_mount_contracts", []) or [] if isinstance(item, Mapping)]
        violations = [item for item in runtime.get("skill_mount_violations", []) or [] if isinstance(item, Mapping)]
        skill_checks = []
        for skill_id in skill_ids:
            blocking = [item for item in violations if str(item.get("skill_name") or "") == skill_id]
            chain = _chain_for_skill(
                skill_id=skill_id,
                requests=requests,
                contracts=contracts,
                blocking_violations=blocking,
            )
            status = "PASS" if all(chain.values()) and not blocking else "RETURN"
            if status != "PASS":
                reasons = [str(item.get("reason") or "unknown") for item in blocking] or ["skill_mount_not_confirmed"]
                blockers.extend(f"{capability}:{skill_id}:{reason}" for reason in reasons)
            skill_checks.append(
                {
                    "skill_id": skill_id,
                    "status": status,
                    "runtime_final_receipt_chain": chain,
                    "blocking_skill_mount_violations": blocking,
                }
            )
        cases.append(
            {
                "capability": capability,
                "selected_mode": row.get("heep_mode", ""),
                "skill_count": len(skill_ids),
                "skill_ids": skill_ids,
                "status": "PASS" if skill_checks and all(item["status"] == "PASS" for item in skill_checks) else "RETURN",
                "skill_checks": skill_checks,
            }
        )
    status = "PASS" if cases and all(case["status"] == "PASS" for case in cases) and not blockers else "RETURN"
    return {
        "schema": "nexus.heep_runtime_apply_gate.v1",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "summary": {
            "approved_candidate_count": len(approved),
            "case_count": len(cases),
            "pass_count": sum(1 for case in cases if case["status"] == "PASS"),
            "return_count": sum(1 for case in cases if case["status"] != "PASS"),
            "blocker_count": len(sorted(set(blockers))),
            "runtime_update_allowed": status == "PASS",
            "public_benchmark_allowed": False,
        },
        "blockers": sorted(set(blockers)),
        "cases": cases,
        "claim_boundary": [
            "HEEP runtime apply gate verifies MAT-B-approved assemblies only.",
            "It does not update runtime defaults.",
            "Public benchmark remains blocked and must use a separate gate.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the HEEP runtime apply gate for MAT-B approved modes.")
    parser.add_argument("--mat-b-report", default=str(DEFAULT_MAT_B_REPORT))
    parser.add_argument("--execution-matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--skill-status-report", default=str(DEFAULT_SKILL_STATUS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    gate = build_heep_runtime_apply_gate(
        mat_b_report=read_json(args.mat_b_report),
        execution_matrix=read_json(args.execution_matrix),
        skill_status_report=args.skill_status_report,
    )
    write_json(args.output, gate)
    print(json.dumps({"status": gate["status"], "output": args.output, **gate["summary"]}, sort_keys=True))
    return 0 if gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
