#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_SETTLEMENT = PROJECT_ROOT / "docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_SETTLEMENT_2026-05-21.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs/reports/NEXUS_SF_FINAL_COMPARE_REPORT_2026-05-21.json"

DECISION_READY_FOR_LIVE_COMPARE = "READY_FOR_LIVE_COMPARE"
DECISION_REJECT_PRECHECK = "REJECT_PRECHECK"
DECISION_KEEP_CURRENT_NO_LIVE_EVIDENCE = "KEEP_CURRENT_NO_LIVE_EVIDENCE"


def build_sf_final_compare_report(*, settlement: Mapping[str, Any]) -> dict[str, Any]:
    matrix_rows = [row for row in settlement.get("canonical_compare_matrix", []) or [] if isinstance(row, Mapping)]
    compare_rows = [_compare_row(row) for row in matrix_rows]
    blockers = _blockers(settlement, compare_rows)
    return {
        "schema": "nexus.sf_final_compare_report.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": _summary(settlement=settlement, compare_rows=compare_rows),
        "compare_rows": compare_rows,
        "live_compare_batches": _live_compare_batches(compare_rows),
        "decision_ledger": _decision_ledger(compare_rows),
        "sf_final_compare_taskcards": _taskcards(blockers),
        "claim_boundary": [
            "SF-FINAL-COMPARE is deterministic/local compare triage, not live Flash+Nexus replacement evidence.",
            "READY_FOR_LIVE_COMPARE means the candidate can be tested against the current primary; it does not mean the candidate wins.",
            "Runtime defaults and public benchmarks remain disabled until live comparison, runtime receipt, and apply gate pass.",
        ],
        "blockers": blockers,
    }


def _compare_row(row: Mapping[str, Any]) -> dict[str, Any]:
    blockers = [str(item) for item in row.get("precheck_blockers", []) or []]
    current_primary = str(row.get("current_primary_skill_id") or "")
    candidate = str(row.get("candidate_skill_id") or "")
    role = str(row.get("candidate_role") or "Logic")
    if not blockers and candidate == current_primary:
        decision = DECISION_KEEP_CURRENT_NO_LIVE_EVIDENCE
        reason = "candidate_is_current_primary"
    elif blockers:
        decision = DECISION_REJECT_PRECHECK
        reason = blockers[0]
    else:
        decision = DECISION_READY_FOR_LIVE_COMPARE
        reason = "needs_flash_nexus_live_compare"
    return {
        "capability": str(row.get("capability") or ""),
        "baseline_arm": {
            "mode": "current_primary",
            "skill_ids": [current_primary] if current_primary else [],
        },
        "challenger_arm": _challenger_arm(current_primary=current_primary, candidate=candidate, role=role),
        "candidate_skill_id": candidate,
        "candidate_role": role,
        "candidate_source_tier": str(row.get("candidate_source_tier") or ""),
        "canonical_source_path": str(row.get("canonical_source_path") or ""),
        "static_fit_score": int(row.get("static_fit_score") or 0),
        "fit_reason": str(row.get("fit_reason") or ""),
        "mirror_count": int(row.get("mirror_count") or 1),
        "deterministic_precheck": {
            "status": "PASS" if not blockers else "RETURN",
            "blockers": blockers,
            "checks": [
                "candidate_has_skill_id",
                "candidate_not_current_primary",
                "source_tier_not_quarantine",
                "safety_status_pass",
            ],
        },
        "decision": decision,
        "reason": reason,
        "required_next_step": "run_flash_nexus_live_compare" if decision == DECISION_READY_FOR_LIVE_COMPARE else "none",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _challenger_arm(*, current_primary: str, candidate: str, role: str) -> dict[str, Any]:
    if role in {"Audit", "Scout"}:
        skill_ids = [item for item in [current_primary, candidate] if item]
        return {"mode": "candidate_multi_skill", "skill_ids": _dedupe(skill_ids)}
    return {"mode": "candidate_single_skill", "skill_ids": [candidate] if candidate else []}


def _live_compare_batches(compare_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ready = [row for row in compare_rows if row.get("decision") == DECISION_READY_FOR_LIVE_COMPARE]
    batches: list[dict[str, Any]] = []
    for capability in sorted({str(row.get("capability") or "") for row in ready}):
        rows = [row for row in ready if row.get("capability") == capability]
        batches.append(
            {
                "capability": capability,
                "row_count": len(rows),
                "candidate_skill_ids": [str(row.get("candidate_skill_id") or "") for row in rows],
                "batch_state": "READY_FOR_FLASH_NEXUS_COMPARE",
                "runner_contract": {
                    "same_model": True,
                    "required_receipt_chain": ["selected", "injected", "used", "evidence", "gate", "outcome"],
                    "trust_mismatch_required": 0,
                    "provider_token_truth_required": "MEASURED_OR_NOT_APPLICABLE",
                },
            }
        )
    return batches


def _decision_ledger(compare_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "capability": str(row.get("capability") or ""),
            "candidate_skill_id": str(row.get("candidate_skill_id") or ""),
            "decision": str(row.get("decision") or ""),
            "reason": str(row.get("reason") or ""),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        }
        for row in compare_rows
    ]


def _summary(*, settlement: Mapping[str, Any], compare_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    decisions = _counts(str(row.get("decision") or "") for row in compare_rows)
    return {
        "source_settlement_status": settlement.get("status"),
        "capability_count": len({str(row.get("capability") or "") for row in compare_rows}),
        "compare_row_count": len(compare_rows),
        "ready_for_live_compare_count": decisions.get(DECISION_READY_FOR_LIVE_COMPARE, 0),
        "reject_precheck_count": decisions.get(DECISION_REJECT_PRECHECK, 0),
        "keep_current_no_live_evidence_count": decisions.get(DECISION_KEEP_CURRENT_NO_LIVE_EVIDENCE, 0),
        "decision_counts": decisions,
        "live_compare_batch_count": len({str(row.get("capability") or "") for row in compare_rows if row.get("decision") == DECISION_READY_FOR_LIVE_COMPARE}),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def _taskcards(blockers: list[str]) -> dict[str, Any]:
    status = "PASS" if not blockers else "RETURN"
    return {
        "SF-FINAL-COMPARE-0_canonical_input": {"status": status, "exit": "consume canonical SF-FINAL compare matrix"},
        "SF-FINAL-COMPARE-1_current_vs_candidate_matrix": {"status": status, "exit": "every row has baseline and challenger arms"},
        "SF-FINAL-COMPARE-2_deterministic_precheck": {"status": status, "exit": "quarantine/same-primary blockers normalize before live"},
        "SF-FINAL-COMPARE-3_live_batch_plan": {"status": status, "exit": "ready rows grouped by capability for Flash+Nexus live compare"},
        "SF-FINAL-COMPARE-4_decision_ledger": {"status": status, "exit": "no row can be mistaken for runtime/public approval"},
    }


def _blockers(settlement: Mapping[str, Any], compare_rows: list[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    if settlement.get("status") != "PASS":
        blockers.append("source_settlement_not_pass")
    if not compare_rows:
        blockers.append("missing_compare_rows")
    for row in compare_rows:
        if not row.get("capability"):
            blockers.append("compare_row_missing_capability")
        if not row.get("candidate_skill_id"):
            blockers.append(f"{row.get('capability', 'unknown')}:missing_candidate_skill")
        if not row.get("baseline_arm", {}).get("skill_ids"):
            blockers.append(f"{row.get('capability', 'unknown')}:missing_current_primary")
    return sorted(set(blockers))


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF-FINAL deterministic compare report.")
    parser.add_argument("--settlement", type=Path, default=DEFAULT_SETTLEMENT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = build_sf_final_compare_report(settlement=_read_json(args.settlement))
    if not args.dry_run:
        _write_json(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                **payload["summary"],
                "output": "" if args.dry_run else str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
