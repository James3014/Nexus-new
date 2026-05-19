#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nexus.app import research_flow_service
from nexus.app.research_receipt_runtime import build_capability_receipt_payloads


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _runtime_trace(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({"event": "sf_runtime_receipt_smoke", "status": "PASS"}) + "\n", encoding="utf-8")
    return str(path)


def _report_path(repo_root: Path, filename: str, *, date: str) -> Path:
    root_path = repo_root / "docs/reports" / filename
    if root_path.exists():
        return root_path
    archive_path = repo_root / "docs/reports/archive/sf" / date / filename
    if archive_path.exists():
        return archive_path
    return root_path


def _case(
    *,
    repo_root: Path,
    overlay_path: Path,
    skill_status_report: Path,
    task_id: str,
    task_desc: str,
    task_type: str,
    expected_skill: str,
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    plan, decision = research_flow_service._build_capability_plan_and_decision(
        task_desc=task_desc,
        task_type=task_type,
        route={"recommended_flow": "hyper_sprint", "route_features": {"risk_score": 80}},
        task_id=task_id,
        budget={
            "runtime_skill_policy_overlay_path": str(overlay_path),
            "skill_status_report": str(skill_status_report),
        },
        skills=[],
    )
    plan_payload = plan.to_dict()
    usage_trace = {
        "capabilities": capabilities,
        "autoreason": {},
        "ddtree": {},
        "ultra_review": {},
        "codeintel": {},
    }
    capability_receipts = build_capability_receipt_payloads(plan_payload, usage_trace)
    runtime = research_flow_service._build_runtime_skill_mount_contracts(
        capability_plan_payload=plan_payload,
        route_decision_payload=decision,
        capability_receipts=capability_receipts,
    )
    contracts = runtime.get("skill_mount_contracts", [])
    violations = runtime.get("skill_mount_violations", [])
    blocking_violations = [
        item
        for item in violations
        if isinstance(item, dict) and str(item.get("skill_name") or "").strip() == expected_skill
    ]
    contract = next((item for item in contracts if item.get("skill_id") == expected_skill), None)
    contract_capability = str((contract or {}).get("capability") or "").strip()
    receipt = next((item for item in capability_receipts if item.get("name") == contract_capability), None)
    if receipt is None:
        receipt = next(
            (
                item
                for item in capability_receipts
                if item.get("name") in research_flow_service._skill_mount_receipt_names(str((contract or {}).get("capability_mount") or ""))
                and item.get("gate_passed")
                and item.get("outcome_contributed")
            ),
            None,
        )
    chain = {
        "selected": bool(contract),
        "injected": bool(contract),
        "used": bool(contract and "runtime_capability_receipt_confirmed" in (contract.get("load_reason_codes") or [])),
        "evidence_present": bool(contract and contract.get("evidence_refs") and receipt and receipt.get("evidence_present")),
        "gate_passed": bool(contract and receipt and receipt.get("gate_passed")),
        "outcome_contributed": bool(contract and contract.get("outcome_contributed") and receipt and receipt.get("outcome_contributed")),
    }
    return {
        "task_id": task_id,
        "expected_skill": expected_skill,
        "selected_capabilities": plan_payload.get("selected_capabilities", []),
        "planned_skill_mount_contracts": plan_payload.get("signal_snapshot", {}).get("planned_skill_mount_contracts", []),
        "capability_receipts": capability_receipts,
        "skill_mount_contracts": contracts,
        "skill_mount_violations": violations,
        "blocking_skill_mount_violations": blocking_violations,
        "non_blocking_unscoped_violations": [
            item for item in violations if item not in blocking_violations
        ],
        "runtime_final_receipt_chain": chain,
        "status": "PASS" if all(chain.values()) and not blocking_violations else "RETURN",
    }


def build_report(*, repo_root: Path, overlay_path: Path, output: Path) -> dict[str, Any]:
    trace_path = output.with_name(output.stem + "_repair_loop_trace.jsonl")
    cases = [
        _case(
            repo_root=repo_root,
            overlay_path=overlay_path,
            skill_status_report=_report_path(
                repo_root,
                "NEXUS_SKILL_STATUS_2026-05-15.json",
                date="2026-05-15",
            ),
            task_id="sf-runtime-receipt-smoke-repair-loop",
            task_desc="Fix a failing regression with a runtime repair loop.\nExpected capability receipts: repair_loop.",
            task_type="bug",
            expected_skill="tdd",
            capabilities={
                "claim_verified": True,
                "rlm_trace_path": _runtime_trace(trace_path),
                "rlm_trace_present": True,
                "rlm_attempt_id": "sf-runtime-receipt-smoke",
            },
        ),
        _case(
            repo_root=repo_root,
            overlay_path=overlay_path,
            skill_status_report=_report_path(
                repo_root,
                "NEXUS_SF_FORECAST_CREATE_PLAN_SEAL_SKILL_STATUS_2026-05-18.json",
                date="2026-05-18",
            ),
            task_id="sf-runtime-receipt-smoke-forecast-pregate",
            task_desc=(
                "Review implementation risk and plan quality before execution.\n"
                "Expected capability receipts: forecast_gate, pregate, plan_quality_gate."
            ),
            task_type="plan",
            expected_skill="create-plan",
            capabilities={
                "claim_verified": True,
                "forecast_refs": ["forecast:sf-runtime-receipt-smoke"],
                "forecast_gate_passed": True,
                "pregate_refs": ["pregate:sf-runtime-receipt-smoke"],
                "pregate_gate_passed": True,
                "plan_quality_refs": ["plan_quality:sf-runtime-receipt-smoke"],
                "plan_quality_gate_passed": True,
            },
        ),
    ]
    report = {
        "schema": "nexus_sf_runtime_receipt_smoke_v1",
        "status": "PASS" if all(item["status"] == "PASS" for item in cases) else "RETURN",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "overlay_path": str(overlay_path),
        "summary": {
            "case_count": len(cases),
            "pass_count": sum(1 for item in cases if item["status"] == "PASS"),
            "return_count": sum(1 for item in cases if item["status"] != "PASS"),
        },
        "cases": cases,
        "claim_boundary": {
            "scope": "runtime_receipt_smoke_only",
            "not_public_benchmark": True,
            "runtime_default_change": False,
        },
    }
    _write_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--overlay", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_report(
        repo_root=Path(args.repo_root).resolve(),
        overlay_path=Path(args.overlay),
        output=Path(args.output),
    )
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
