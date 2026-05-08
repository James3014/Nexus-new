#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.bench.s2t_shadow_report import build_promoted_s2t_policy, build_s2t_shadow_report


def load_rows_from_evidence_bundle(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_files = payload.get("raw_files", {})
    raw_files = raw_files if isinstance(raw_files, dict) else {}
    rows: list[dict[str, Any]] = []
    for mode, metadata in raw_files.items():
        if not isinstance(metadata, dict):
            continue
        raw_path = Path(str(metadata.get("path") or ""))
        if not raw_path.exists():
            continue
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                row.setdefault("mode", mode)
                rows.append(row)
    return rows


def build_export(path: Path) -> dict[str, Any]:
    rows = load_rows_from_evidence_bundle(path)
    report = build_s2t_shadow_report(rows)
    policy = build_promoted_s2t_policy(report)
    route_cost_policy = build_route_cost_policy_candidate(policy, source=str(path))
    return {
        "schema": "nexus_s2t_shadow_policy_export_v1",
        "source_evidence_bundle": str(path),
        "row_count": len(rows),
        "s2t_shadow_report": report,
        "s2t_policy_draft": policy,
        "route_cost_policy_candidate": route_cost_policy,
    }


def build_route_cost_policy_candidate(policy: dict[str, Any], *, source: str) -> dict[str, Any]:
    candidate_cap_actions = {
        "prefer_lite_or_standard",
        "try_standard_with_cost_cap",
        "try_lite_with_defensive_gate",
    }
    task_rules = policy.get("task_rules", {})
    task_rules = task_rules if isinstance(task_rules, dict) else {}
    # Lite disables bounded self-heal in the current runner. Keep it behind a
    # stricter future promotion gate; candidate caps are the safe first step.
    lite_tasks: list[str] = []
    candidate_cap_tasks = [
        str(task_id)
        for task_id, rule in sorted(task_rules.items())
        if isinstance(rule, dict) and str(rule.get("recommended_action") or "") in candidate_cap_actions
    ]
    return {
        "schema_version": "nexus_promoted_route_cost_policy.v1",
        "source": source,
        "candidate_cap_overrides": {task_id: 1 for task_id in candidate_cap_tasks},
        "lite_route_tasks": lite_tasks,
        "hold_tasks": [],
        "promotion_gate": {
            "source_policy_status": str(policy.get("status") or ""),
            "requires_same_model_before_after_ab": True,
            "defensive_run_required": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export S2T shadow telemetry and draft policy from an evidence bundle.")
    parser.add_argument("--evidence-bundle", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    export = build_export(args.evidence_bundle)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(export, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(export, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if export["row_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
