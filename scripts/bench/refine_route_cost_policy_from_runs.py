#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _latest_jsonl(run_dir: Path, arm: str) -> Path:
    files = sorted(run_dir.glob(f"{arm}_*.jsonl"))
    if not files:
        raise FileNotFoundError(f"missing {arm}_*.jsonl in {run_dir}")
    return files[-1]


def _rows(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = _latest_jsonl(run_dir, "with_nexus")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {str(row.get("task_id") or ""): row for row in rows if row.get("task_id")}


def _verified(row: dict[str, Any]) -> bool:
    return bool(row.get("run_eligible", True)) and str(row.get("semantic_status") or "") == "VERIFIED" and not bool(
        row.get("report_trust_mismatch", False)
    )


def _num(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def refine_policy(
    *,
    baseline_rows: dict[str, dict[str, Any]],
    candidate_rows: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    overrides = policy.get("candidate_cap_overrides", {})
    overrides = overrides if isinstance(overrides, dict) else {}
    lite_tasks = set(str(item) for item in policy.get("lite_route_tasks", []) or [])
    kept_overrides: dict[str, int] = {}
    kept_lite: list[str] = []
    rejected: dict[str, str] = {}

    for task_id, cap in sorted(overrides.items()):
        baseline = baseline_rows.get(str(task_id), {})
        candidate = candidate_rows.get(str(task_id), {})
        if not baseline or not candidate:
            rejected[str(task_id)] = "missing_comparable_row"
            continue
        if not _verified(baseline) or not _verified(candidate):
            rejected[str(task_id)] = "verified_delivery_not_preserved"
            continue
        wall_ok = _num(candidate, "wall_duration_sec") <= _num(baseline, "wall_duration_sec")
        tokens_ok = _num(candidate, "total_tokens") <= _num(baseline, "total_tokens")
        if not wall_ok or not tokens_ok:
            rejected[str(task_id)] = "cost_not_improved"
            continue
        kept_overrides[str(task_id)] = max(1, int(cap or 1))
        if str(task_id) in lite_tasks:
            kept_lite.append(str(task_id))

    refined = dict(policy)
    refined["candidate_cap_overrides"] = {}
    refined["lite_route_tasks"] = []
    refined["legacy_task_policy_source_ids"] = {
        "candidate_cap_task_ids": sorted(kept_overrides),
        "lite_task_ids": kept_lite,
    }
    refined["refinement"] = {
        "schema": "nexus_route_cost_policy_refinement_v1",
        "kept_task_ids": sorted(kept_overrides),
        "rejected_task_reasons": rejected,
        "gate": {
            "same_task_before_after_required": True,
            "verified_delivery_preserved": True,
            "wall_and_tokens_must_not_regress": True,
        },
    }
    return refined


def build_refinement(*, baseline_dir: Path, candidate_dir: Path, policy_path: Path) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    return refine_policy(
        baseline_rows=_rows(baseline_dir),
        candidate_rows=_rows(candidate_dir),
        policy=policy,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refine a route-cost policy using same-task before/after rows.")
    parser.add_argument("--baseline-dir", required=True, type=Path)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    refined = build_refinement(baseline_dir=args.baseline_dir, candidate_dir=args.candidate_dir, policy_path=args.policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(refined, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(refined.get("refinement", {}), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
