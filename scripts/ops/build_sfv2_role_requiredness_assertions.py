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


DEFAULT_LIVE = Path(".nexus/reports/sfv2_role_ablation_edgecase_live_2026-05-21/live_summary.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_EXECUTION_MATRIX_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SFV2_ROLE_REQUIREDNESS_ASSERTION_PACKET_2026-05-21.json")


ROLE_ASSERTIONS = {
    "Scout": {
        "assertion_id": "scout_external_surface_present",
        "required_fields": ["codeintel_scan_report_present", "codeintel_impact_report_present", "dci_locator_present"],
        "loss_dimension": "external_scan_or_surface_evidence",
    },
    "Logic": {
        "assertion_id": "logic_decision_invariant_present",
        "required_fields": ["autoreason_status", "belief_confidence", "capability_plan_trace_present"],
        "loss_dimension": "decision_invariant_or_reasoning_evidence",
    },
    "Audit": {
        "assertion_id": "audit_boundary_gate_present",
        "required_fields": ["rubric_contract_status", "evidence_rubric_status", "delivery_rubric_status", "warning_clean"],
        "loss_dimension": "governance_boundary_or_regression_evidence",
    },
    "primary": {
        "assertion_id": "primary_expected_receipt_present",
        "required_fields": [
            "expected_capability_receipt_coverage",
            "expected_capability_invocation_coverage",
            "skill_mount_contract_status",
        ],
        "loss_dimension": "primary_capability_receipt_evidence",
    },
}


def build_sfv2_role_requiredness_assertions(
    *,
    live_summary: Mapping[str, Any],
    matrix: Mapping[str, Any],
    output: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    matrix_by_row = {str(row.get("row_id") or ""): row for row in matrix.get("rows", []) if isinstance(row, Mapping)}
    live_by_pair: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = {}
    for result in live_summary.get("results", []) or []:
        if not isinstance(result, Mapping):
            continue
        matrix_row = matrix_by_row.get(str(result.get("row_id") or ""), {})
        role = str(matrix_row.get("role_focus") or "primary")
        key = (str(result.get("capability") or ""), role)
        pair = live_by_pair.setdefault(key, {})
        arm = str(result.get("arm_id") or "")
        if arm == "full_assembly":
            pair["full"] = result
        elif arm.startswith("minus_"):
            pair["minus"] = result

    assertions = []
    for (capability, role), pair in sorted(live_by_pair.items()):
        assertion = ROLE_ASSERTIONS.get(role, ROLE_ASSERTIONS["primary"])
        full = pair.get("full") or {}
        minus = pair.get("minus") or {}
        full_row = full.get("benchmark_row") if isinstance(full.get("benchmark_row"), Mapping) else {}
        minus_row = minus.get("benchmark_row") if isinstance(minus.get("benchmark_row"), Mapping) else {}
        full_state = _field_state(full_row, assertion["required_fields"])
        minus_state = _field_state(minus_row, assertion["required_fields"])
        full_clean = _row_clean(full, full_row)
        minus_clean = _row_clean(minus, minus_row)
        minus_returned = str(minus.get("status") or "") != "PASS"
        status = "ROLE_REQUIREDNESS_PROVEN" if full_clean and minus_returned and not minus_clean else "NOT_PROVEN"
        reason = "minus_role_preserved_required_external_assertions"
        if not full_clean:
            reason = "full_assembly_not_clean_for_assertion"
        elif minus_returned and not minus_clean:
            reason = "minus_role_lost_required_external_assertion"
        assertions.append(
            {
                "capability": capability,
                "role_focus": role,
                "assertion_id": assertion["assertion_id"],
                "loss_dimension": assertion["loss_dimension"],
                "status": status,
                "reason": reason,
                "full_clean": full_clean,
                "minus_clean": minus_clean,
                "full_field_state": full_state,
                "minus_field_state": minus_state,
                "full_row_id": str(full.get("row_id") or ""),
                "minus_row_id": str(minus.get("row_id") or ""),
            }
        )

    summary = {
        "assertion_count": len(assertions),
        "role_requiredness_proven_count": sum(1 for row in assertions if row["status"] == "ROLE_REQUIREDNESS_PROVEN"),
        "not_proven_count": sum(1 for row in assertions if row["status"] != "ROLE_REQUIREDNESS_PROVEN"),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }
    packet = {
        "schema": "nexus.sfv2_role_requiredness_assertion_packet.v1",
        "status": "PASS" if assertions else "RETURN",
        "summary": summary,
        "claim_boundary": [
            "This packet evaluates role requiredness with machine-checkable runtime fields.",
            "A role is required only when full assembly is clean and the matching minus-role arm loses a required external assertion.",
            "No runtime default or public benchmark is unlocked by this packet.",
        ],
        "assertions": assertions,
    }
    write_json(output, packet)
    return packet


def _row_clean(result: Mapping[str, Any], bench_row: Mapping[str, Any]) -> bool:
    return (
        str(result.get("status") or "") == "PASS"
        and str(bench_row.get("rubric_contract_status") or "").upper() == "PASS"
        and str(bench_row.get("token_data_contract_status") or "").upper() == "PASS"
        and str(bench_row.get("receipt_data_contract_status") or "").upper() == "PASS"
        and str(bench_row.get("skill_mount_contract_status") or "").upper() == "PASS"
    )


def _field_state(row: Mapping[str, Any], fields: list[str]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for field in fields:
        value = row.get(field)
        state[field] = {
            "present": value is not None and value != "" and value != [] and value != {},
            "value": value,
        }
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SFV2 role requiredness assertion packet.")
    parser.add_argument("--live-summary", default=str(DEFAULT_LIVE))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    packet = build_sfv2_role_requiredness_assertions(
        live_summary=read_json(args.live_summary),
        matrix=read_json(args.matrix),
        output=Path(args.output),
    )
    print(json.dumps({"status": packet["status"], **packet["summary"], "output": str(args.output)}, sort_keys=True))
    return 0 if packet["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
