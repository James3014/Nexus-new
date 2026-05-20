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
DEFAULT_QUEUE = Path("docs/reports/NEXUS_HEEP_MAT_B_BLOCKER_RESOLUTION_QUEUE_2026-05-20.json")
DEFAULT_NEXT_REPLAY = Path("docs/reports/NEXUS_HEEP_MAT_B_NEXT_REPLAY_STATUS_2026-05-20.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_HEEP_MAT_B_BLOCKED_MODE_RESOLUTION_2026-05-20.json")

TOKEN_BLOCKER = "BLOCKED_BY_PROVIDER_TOKEN_TRUTH"
RECEIPT_BLOCKER = "BLOCKED_BY_RECEIPT_DATA_CONTRACT"


def _comparisons_by_capability(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("capability") or ""): row
        for row in report.get("comparisons", []) or []
        if isinstance(row, Mapping) and row.get("capability")
    }


def _queue_by_capability(queue: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("capability") or ""): row
        for row in queue.get("queue", []) or []
        if isinstance(row, Mapping) and row.get("capability")
    }


def _metric(row: Mapping[str, Any], arm: str, key: str) -> Any:
    value = row.get(arm)
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _delta(row: Mapping[str, Any], key: str) -> Any:
    value = row.get("delta")
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _truthy(value: Any) -> bool:
    return bool(value) is True


def _provider_token_root(next_replay: Mapping[str, Any]) -> str:
    first = next_replay.get("first_return")
    if not isinstance(first, Mapping):
        return "provider_token_truth_unverified"
    if first.get("token_data_contract_status") == "DATA_CONTRACT_VIOLATION":
        return "gateway_stats_missing_after_model_call"
    return "provider_token_truth_unverified"


def _resolve_provider_token_blocker(
    *,
    comparison: Mapping[str, Any],
    queue_item: Mapping[str, Any],
    provider_root: str,
) -> dict[str, Any]:
    evidence_delta = int(_delta(comparison, "evidence_seal_count_delta") or 0)
    pollution_delta = float(_delta(comparison, "pollution_pct_delta") or 0.0)
    wall_delta = _delta(comparison, "wall_delta")
    baseline_receipt = _truthy(_metric(comparison, "baseline", "receipt_chain_pass"))
    challenger_receipt = _truthy(_metric(comparison, "challenger", "receipt_chain_pass"))
    baseline_mount = str(_metric(comparison, "baseline", "skill_mount_contract_status") or "")
    challenger_mount = str(_metric(comparison, "challenger", "skill_mount_contract_status") or "")
    trust_clean = not _truthy(_metric(comparison, "baseline", "trust_mismatch")) and not _truthy(
        _metric(comparison, "challenger", "trust_mismatch")
    )
    governance_clean = (
        baseline_receipt
        and challenger_receipt
        and baseline_mount == "PASS"
        and challenger_mount == "PASS"
        and trust_clean
        and pollution_delta <= 0.0
    )
    if governance_clean and evidence_delta > 0:
        mode_decision = "MULTI_SKILL_NON_COST_WIN"
        decision_reason = "challenger_has_stronger_evidence_chain"
    elif governance_clean:
        mode_decision = "KEEP_SINGLE_PRIMARY_NON_COST"
        decision_reason = "challenger_no_evidence_gain"
    else:
        mode_decision = "HOLD_GOVERNANCE_UNCLEAN"
        decision_reason = "receipt_or_trust_not_clean"
    return {
        "capability": comparison.get("capability", ""),
        "blocker": queue_item.get("blocker", TOKEN_BLOCKER),
        "root_cause": provider_root,
        "mode_decision": mode_decision,
        "decision_scope": "internal_non_cost_mode_selection",
        "decision_reason": decision_reason,
        "baseline_row_id": comparison.get("baseline_row_id", ""),
        "challenger_row_id": comparison.get("challenger_row_id", ""),
        "evidence_seal_count_delta": evidence_delta,
        "pollution_pct_delta": pollution_delta,
        "wall_delta_observation": wall_delta,
        "provider_cost_status": "HOLD_PROVIDER_TOKEN_TRUTH",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "remaining_gate": [
            "provider-clean replay with measured provider tokens",
            "same-window baseline/challenger token truth before cost decision",
        ],
    }


def _resolve_receipt_blocker(*, comparison: Mapping[str, Any], queue_item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "capability": comparison.get("capability", queue_item.get("capability", "")),
        "blocker": queue_item.get("blocker", RECEIPT_BLOCKER),
        "root_cause": "expected_executor_receipt_missing",
        "mode_decision": "UNDECIDED_RECEIPT_CHAIN_MISSING",
        "decision_scope": "no_mode_selection_until_receipt_chain_passes",
        "decision_reason": "baseline_and_challenger_missing_expected_capability_receipts",
        "baseline_row_id": comparison.get("baseline_row_id", queue_item.get("baseline_row_id", "")),
        "challenger_row_id": comparison.get("challenger_row_id", queue_item.get("challenger_row_id", "")),
        "missing_expected_capabilities": queue_item.get("missing_expected_capabilities", []),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "remaining_gate": [
            "targeted route/executor smoke produces selected/invoked/evidence/gate/outcome receipt",
            "provider-clean MAT-B replay after executor receipt is present",
        ],
    }


def build_blocked_mode_resolution(
    *,
    mat_b_report: Mapping[str, Any],
    blocker_queue: Mapping[str, Any],
    next_replay_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    comparisons = _comparisons_by_capability(mat_b_report)
    queue = _queue_by_capability(blocker_queue)
    provider_root = _provider_token_root(next_replay_status or {})
    rows: list[dict[str, Any]] = []
    for capability, item in sorted(queue.items()):
        comparison = comparisons.get(capability, {"capability": capability})
        blocker = str(item.get("blocker") or "")
        if blocker == TOKEN_BLOCKER:
            rows.append(
                _resolve_provider_token_blocker(
                    comparison=comparison,
                    queue_item=item,
                    provider_root=provider_root,
                )
            )
        elif blocker == RECEIPT_BLOCKER:
            rows.append(_resolve_receipt_blocker(comparison=comparison, queue_item=item))

    return {
        "schema": "nexus.heep_mat_b_blocked_mode_resolution.v1",
        "status": "PASS",
        "summary": {
            "blocked_capability_count": len(rows),
            "multi_skill_non_cost_win_count": sum(
                1 for row in rows if row["mode_decision"] == "MULTI_SKILL_NON_COST_WIN"
            ),
            "keep_single_non_cost_count": sum(
                1 for row in rows if row["mode_decision"] == "KEEP_SINGLE_PRIMARY_NON_COST"
            ),
            "receipt_chain_missing_count": sum(
                1 for row in rows if row["mode_decision"] == "UNDECIDED_RECEIPT_CHAIN_MISSING"
            ),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "claim_boundary": [
            "Provider-token blockers may receive internal non-cost mode decisions when receipt/trust evidence is clean.",
            "Internal non-cost mode decisions do not approve runtime default, public benchmark, or cost claims.",
            "Receipt-chain blockers remain undecided until expected capability runtime receipts are present.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve HEEP MAT-B blocked single-vs-multi mode decisions.")
    parser.add_argument("--mat-b-report", default=str(DEFAULT_REPORT))
    parser.add_argument("--blocker-queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--next-replay-status", default=str(DEFAULT_NEXT_REPLAY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    report = build_blocked_mode_resolution(
        mat_b_report=read_json(args.mat_b_report),
        blocker_queue=read_json(args.blocker_queue),
        next_replay_status=read_json(args.next_replay_status),
    )
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], **report["summary"], "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
