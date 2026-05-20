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
DEFAULT_CLEAN_REPLAY_REPORT = Path("docs/reports/NEXUS_HEEP_MAT_B_HOLD_CLEAN_REPLAY_REPORT_2026-05-20.json")
DEFAULT_CLEAN_REPLAY_SUMMARY = Path(".nexus/reports/heep_flash_nexus_mat_b_hold_clean_replay_2026-05-20/live_summary.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_HEEP_MAT_B_BLOCKER_RESOLUTION_QUEUE_2026-05-20.json")

TOKEN_BLOCKER = "BLOCKED_BY_PROVIDER_TOKEN_TRUTH"
RECEIPT_BLOCKER = "BLOCKED_BY_RECEIPT_DATA_CONTRACT"


def _reason_codes(row: Mapping[str, Any]) -> list[str]:
    return [str(item) for item in row.get("reason_codes", []) or []]


def _metric(row: Mapping[str, Any], arm: str, key: str) -> Any:
    data = row.get(arm)
    if not isinstance(data, Mapping):
        return None
    return data.get(key)


def _comparisons_by_capability(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("capability") or ""): row
        for row in report.get("comparisons", []) or []
        if isinstance(row, Mapping) and row.get("capability")
    }


def _live_summary_receipts_by_capability(summary: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for row in summary.get("results", []) or []:
        if not isinstance(row, Mapping):
            continue
        capability = str(row.get("capability") or "")
        arm = str(row.get("arm_id") or "")
        if not capability or arm not in {"mode_a_current_primary", "heep_multi_skill"}:
            continue
        bench = row.get("benchmark_row")
        if not isinstance(bench, Mapping):
            continue
        target = "baseline" if arm == "mode_a_current_primary" else "challenger"
        receipts.setdefault(capability, {})[target] = {
            "receipt_data_contract_missing": bench.get("receipt_data_contract_missing", []),
        }
    return receipts


def _missing_receipts(row: Mapping[str, Any], fallback: Mapping[str, Any] | None) -> list[str]:
    missing = {
        str(item)
        for source in (row, fallback or {})
        for arm in ("baseline", "challenger")
        for item in (_metric(source, arm, "receipt_data_contract_missing") or [])
        if str(item).strip()
    }
    return sorted(missing)


def _resolution(row: Mapping[str, Any], clean_replay_row: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    verdict = str(row.get("verdict") or "")
    capability = str(row.get("capability") or "")
    if verdict == TOKEN_BLOCKER:
        return {
            "capability": capability,
            "blocker": verdict,
            "lane": "PROVIDER_TOKEN_TRUTH_REPLAY",
            "required_action": "Rerun the same MAT-B baseline/challenger pair with provider-measured tokens on every model-call row.",
            "closure_gate": [
                "baseline token_data_contract_status == PASS",
                "challenger token_data_contract_status == PASS",
                "total_tokens > 0 when model_calls > 0",
                "receipt_chain_pass remains true for both arms",
            ],
            "can_update_mode_map_before_replay": False,
            "can_update_runtime_before_replay": False,
            "reason_codes": _reason_codes(row),
            "baseline_row_id": row.get("baseline_row_id", ""),
            "challenger_row_id": row.get("challenger_row_id", ""),
        }
    if verdict == RECEIPT_BLOCKER:
        missing = _missing_receipts(row, clean_replay_row)
        return {
            "capability": capability,
            "blocker": verdict,
            "lane": "RECEIPT_INVOCATION_REPLAY",
            "required_action": "Run a targeted route/executor smoke first, then rerun MAT-B only after expected capability receipts are selected, invoked, evidenced, gate-passed, and outcome-contributing.",
            "closure_gate": [
                "expected_capability_receipt_coverage.missing == []",
                "skill_mount_contract_status == PASS",
                "receipt_chain_pass == true for both arms",
                "provider token contract is PASS if model_calls > 0",
            ],
            "missing_expected_capabilities": missing,
            "can_update_mode_map_before_replay": False,
            "can_update_runtime_before_replay": False,
            "reason_codes": _reason_codes(row),
            "baseline_row_id": row.get("baseline_row_id", ""),
            "challenger_row_id": row.get("challenger_row_id", ""),
        }
    return None


def build_heep_mat_b_blocker_resolution_queue(
    *,
    mat_b_report: Mapping[str, Any],
    clean_replay_report: Mapping[str, Any] | None = None,
    clean_replay_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    queue = []
    decided = []
    clean_replay_by_capability = _comparisons_by_capability(clean_replay_report or {})
    live_receipts_by_capability = _live_summary_receipts_by_capability(clean_replay_summary or {})
    for raw in mat_b_report.get("comparisons", []) or []:
        if not isinstance(raw, Mapping):
            continue
        capability = str(raw.get("capability") or "")
        item = _resolution(raw, live_receipts_by_capability.get(capability) or clean_replay_by_capability.get(capability))
        if item is None:
            decided.append(
                {
                    "capability": raw.get("capability", ""),
                    "verdict": raw.get("verdict", ""),
                    "reason_codes": _reason_codes(raw),
                }
            )
            continue
        queue.append(item)

    token_count = sum(1 for item in queue if item["blocker"] == TOKEN_BLOCKER)
    receipt_count = sum(1 for item in queue if item["blocker"] == RECEIPT_BLOCKER)
    return {
        "schema": "nexus.heep_mat_b_blocker_resolution_queue.v1",
        "status": "PASS",
        "summary": {
            "mat_b_comparison_count": len(queue) + len(decided),
            "decided_count": len(decided),
            "blocked_count": len(queue),
            "provider_token_truth_replay_count": token_count,
            "receipt_invocation_replay_count": receipt_count,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "queue": queue,
        "decided": decided,
        "claim_boundary": [
            "This queue is a blocker-resolution artifact for internal HEEP MAT-B only.",
            "Provider-token blockers must not be converted to skill wins by local estimation or zero-fill.",
            "Receipt blockers must not be converted to skill wins until expected capability invocation is confirmed by runtime receipts.",
            "No runtime default or public benchmark claim is unlocked by this queue.",
        ],
        "source_report": str(DEFAULT_REPORT),
        "source_clean_replay_report": str(DEFAULT_CLEAN_REPLAY_REPORT),
        "source_clean_replay_summary": str(DEFAULT_CLEAN_REPLAY_SUMMARY),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build HEEP MAT-B blocker resolution queue.")
    parser.add_argument("--mat-b-report", default=str(DEFAULT_REPORT))
    parser.add_argument("--clean-replay-report", default=str(DEFAULT_CLEAN_REPLAY_REPORT))
    parser.add_argument("--clean-replay-summary", default=str(DEFAULT_CLEAN_REPLAY_SUMMARY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    queue = build_heep_mat_b_blocker_resolution_queue(
        mat_b_report=read_json(args.mat_b_report),
        clean_replay_report=read_json(args.clean_replay_report),
        clean_replay_summary=read_json(args.clean_replay_summary),
    )
    write_json(args.output, queue)
    print(json.dumps({"status": queue["status"], **queue["summary"], "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
