#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_behavior_adapter import build_behavior_runner_adapter


DEFAULT_BACKLOG = Path("docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json")
DEFAULT_FRESH_TASK_REFS = Path("docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_REFS_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json")


def _fresh_task_ref_lookup(fresh_task_refs: dict | None) -> dict[tuple[str, str], dict]:
    lookup: dict[tuple[str, str], dict] = {}
    if not fresh_task_refs:
        return lookup
    for item in fresh_task_refs.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        task_ref = item.get("task_ref") if isinstance(item.get("task_ref"), dict) else {}
        lookup[(str(item.get("capability_id") or ""), str(item.get("skill_id") or ""))] = dict(task_ref)
    return lookup


def build_zero_trust_v2_behavior_runner_matrix(*, backlog: dict, fresh_task_refs: dict | None = None) -> dict:
    items = [item for item in backlog.get("items", []) or [] if isinstance(item, dict)]
    refs = _fresh_task_ref_lookup(fresh_task_refs)
    enriched_items = []
    for item in items:
        key = (str(item.get("capability_id") or ""), str(item.get("skill_id") or ""))
        enriched = dict(item)
        if key in refs:
            enriched["fresh_task_ref"] = refs[key]
        enriched_items.append(enriched)
    adapters = [build_behavior_runner_adapter(item) for item in enriched_items]
    status_counts = Counter(adapter["status"] for adapter in adapters)
    priority_counts = Counter(adapter["priority"] for adapter in adapters)
    return {
        "schema": "nexus.zero_trust_v2.behavior_runner_matrix.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_backlog": str(DEFAULT_BACKLOG),
        "source_fresh_task_refs": str(DEFAULT_FRESH_TASK_REFS) if fresh_task_refs else "",
        "summary": {
            "candidate_count": len(adapters),
            "p0_count": priority_counts.get("P0", 0),
            "p1_count": priority_counts.get("P1", 0),
            "p2_count": priority_counts.get("P2", 0),
            "ready_for_physical_behavior_run_count": status_counts.get("READY_FOR_PHYSICAL_BEHAVIOR_RUN", 0),
            "blocked_count": status_counts.get("BLOCKED", 0),
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
            "promotion_credit_allowed": False,
        },
        "adapters": adapters,
        "claim_boundary": [
            "M13 provides a capability_ab_runner physical behavior adapter, not promotion evidence.",
            "Fresh task_ref is required before P0/P1/P2 candidates can produce V2 behavior receipts.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 behavior runner adapter matrix.")
    parser.add_argument("--backlog", default=str(DEFAULT_BACKLOG))
    parser.add_argument("--fresh-task-refs", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    fresh_task_refs = read_json(args.fresh_task_refs) if args.fresh_task_refs else None
    result = build_zero_trust_v2_behavior_runner_matrix(backlog=read_json(args.backlog), fresh_task_refs=fresh_task_refs)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
