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


DEFAULT_REPORT = Path("docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json")
DEFAULT_MAP_GATE = Path("docs/reports/NEXUS_HEEP_LIVE_MAP_UPDATE_GATE_2026-05-20.json")
DEFAULT_APPLY_PACKET = Path("docs/reports/NEXUS_HEEP_RUNTIME_APPLY_REVIEW_PACKET_2026-05-20.json")
DEFAULT_CATALOG = Path("docs/reports/NEXUS_HEEP_MODE_CANDIDATE_CATALOG_2026-05-20.json")


def _rows_by_capability(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("capability") or ""): dict(row)
        for row in (payload.get("rows", []) or [])
        if isinstance(row, Mapping) and row.get("capability")
    }


def _comparisons_by_capability(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("capability") or ""): dict(row)
        for row in (report.get("comparisons", []) or [])
        if isinstance(row, Mapping) and row.get("capability")
    }


def _mode_for_comparison(comparison: Mapping[str, Any], existing_mode: str) -> str:
    verdict = str(comparison.get("verdict") or "")
    if verdict == "APPROVE_HEEP_MODE_CANDIDATE":
        return existing_mode or "Mode B/C (HEEP Candidate)"
    return "Mode A (Solo)"


def _map_update_allowed(comparison: Mapping[str, Any]) -> bool:
    return str(comparison.get("verdict") or "") in {
        "APPROVE_HEEP_MODE_CANDIDATE",
        "KEEP_SINGLE_PRIMARY",
        "REJECT_MULTI_SKILL",
    }


def _apply_disposition(comparison: Mapping[str, Any] | None, existing: Mapping[str, Any]) -> str:
    if comparison is None:
        return str(existing.get("disposition") or "KEEP_SINGLE_PRIMARY")
    verdict = str(comparison.get("verdict") or "")
    if verdict == "APPROVE_HEEP_MODE_CANDIDATE":
        return "READY_FOR_RUNTIME_APPLY_REVIEW"
    return verdict or "HOLD"


def build_heep_mat_b_update_packets(
    *,
    mat_b_report: Mapping[str, Any],
    map_gate: Mapping[str, Any],
    apply_packet: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    comparisons = _comparisons_by_capability(mat_b_report)
    map_rows = []
    for capability, row in _rows_by_capability(map_gate).items():
        comparison = comparisons.get(capability)
        existing_mode = str(row.get("heep_mode_candidate") or "")
        if comparison is None:
            mode = existing_mode
            allowed = bool(row.get("map_update_allowed"))
            verdict = "NOT_IN_MAT_B_LIVE_COMPARE"
            reasons: list[str] = []
        else:
            mode = _mode_for_comparison(comparison, existing_mode)
            allowed = _map_update_allowed(comparison)
            verdict = str(comparison.get("verdict") or "")
            reasons = [str(item) for item in comparison.get("reason_codes", []) or []]
        map_rows.append(
            {
                "capability": capability,
                "heep_mode_candidate": mode,
                "mat_b_verdict": verdict,
                "mat_b_reason_codes": reasons,
                "map_update_allowed": allowed,
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    apply_rows = []
    for capability, row in _rows_by_capability(apply_packet).items():
        comparison = comparisons.get(capability)
        disposition = _apply_disposition(comparison, row)
        apply_rows.append(
            {
                "capability": capability,
                "selected_mode": _mode_for_comparison(comparison, str(row.get("selected_mode") or ""))
                if comparison is not None
                else row.get("selected_mode"),
                "disposition": disposition,
                "mat_b_verdict": str(comparison.get("verdict") or "") if comparison else "NOT_IN_MAT_B_LIVE_COMPARE",
                "mat_b_reason_codes": list(comparison.get("reason_codes", []) or []) if comparison else [],
                "mat_b_required_before_runtime_apply": False,
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    catalog_rows = []
    for capability, comparison in sorted(comparisons.items()):
        catalog_rows.append(
            {
                "capability": capability,
                "baseline_row_id": comparison.get("baseline_row_id", ""),
                "challenger_row_id": comparison.get("challenger_row_id", ""),
                "mat_b_verdict": comparison.get("verdict", ""),
                "mat_b_reason_codes": comparison.get("reason_codes", []),
                "selected_mode_candidate": _mode_for_comparison(
                    comparison,
                    _rows_by_capability(map_gate).get(capability, {}).get("heep_mode_candidate", ""),
                ),
                "runtime_apply_review_ready": comparison.get("verdict") == "APPROVE_HEEP_MODE_CANDIDATE",
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )

    map_update = {
        "schema": "nexus.heep_live_map_update_gate.v2",
        "status": "PASS",
        "summary": {
            "candidate_update_count": sum(1 for row in map_rows if row["map_update_allowed"]),
            "mat_b_comparison_count": len(comparisons),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": map_rows,
        "blockers": [],
        "claim_boundary": [
            "Map updates are HEEP mode candidates only.",
            "They do not alter runtime defaults or public benchmark readiness.",
        ],
    }
    runtime_apply = {
        "schema": "nexus.heep_runtime_apply_review_packet.v2",
        "status": "PASS",
        "summary": {
            "capability_count": len(apply_rows),
            "ready_for_runtime_apply_review_count": sum(
                1 for row in apply_rows if row["disposition"] == "READY_FOR_RUNTIME_APPLY_REVIEW"
            ),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": apply_rows,
        "blockers": [],
        "claim_boundary": [
            "This packet records runtime apply review candidates only.",
            "MAT-B approval is not runtime default approval.",
            "Runtime default remains disabled until a separate apply gate passes.",
        ],
    }
    catalog = {
        "schema": "nexus.heep_mode_candidate_catalog.v1",
        "status": "PASS",
        "summary": {
            "capability_count": len(catalog_rows),
            "approved_mode_candidate_count": sum(
                1 for row in catalog_rows if row["mat_b_verdict"] == "APPROVE_HEEP_MODE_CANDIDATE"
            ),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": catalog_rows,
        "source_report": str(DEFAULT_REPORT),
    }
    return {"map_gate": map_update, "apply_packet": runtime_apply, "catalog": catalog}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write HEEP MAT-B map/catalog/apply update packets.")
    parser.add_argument("--mat-b-report", default=str(DEFAULT_REPORT))
    parser.add_argument("--map-gate", default=str(DEFAULT_MAP_GATE))
    parser.add_argument("--apply-packet", default=str(DEFAULT_APPLY_PACKET))
    parser.add_argument("--catalog-output", default=str(DEFAULT_CATALOG))
    args = parser.parse_args(argv)
    packets = build_heep_mat_b_update_packets(
        mat_b_report=read_json(args.mat_b_report),
        map_gate=read_json(args.map_gate),
        apply_packet=read_json(args.apply_packet),
    )
    write_json(args.map_gate, packets["map_gate"])
    write_json(args.apply_packet, packets["apply_packet"])
    write_json(args.catalog_output, packets["catalog"])
    print(
        json.dumps(
            {
                "status": packets["catalog"]["status"],
                **packets["catalog"]["summary"],
                "map_gate": args.map_gate,
                "apply_packet": args.apply_packet,
                "catalog_output": args.catalog_output,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
