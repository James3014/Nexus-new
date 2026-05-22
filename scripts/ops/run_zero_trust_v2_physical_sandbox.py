#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_physical_runner import run_zero_trust_v2_physical_rows


DEFAULT_REPLAY_MATRIX = Path("docs/reports/NEXUS_ZERO_TRUST_V2_REPLAY_MATRIX_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_PHYSICAL_SANDBOX_RUN_2026-05-21.json")


def run_zero_trust_v2_physical_sandbox_matrix(
    *,
    replay_matrix: dict,
    command: list[str],
    signing_secret: str,
    limit: int,
    promotion_credit_allowed: bool = False,
) -> dict:
    rows = [row for row in replay_matrix.get("rows", []) or [] if isinstance(row, dict)]
    selected_rows = rows[:limit] if limit > 0 else rows
    run_id = f"ztv2-physical-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    executed_rows = run_zero_trust_v2_physical_rows(
        selected_rows,
        command=command,
        signing_secret=signing_secret,
        run_id=run_id,
        promotion_credit_allowed=promotion_credit_allowed,
    )
    execution_counts = Counter(str(row.get("execution_status") or "UNKNOWN") for row in executed_rows)
    ready_count = sum(
        1
        for row in executed_rows
        if isinstance(row.get("promotion_evaluation"), dict)
        and row["promotion_evaluation"].get("status") == "READY_FOR_MANUAL_APPLY"
    )
    return {
        "schema": "nexus.zero_trust_v2.physical_sandbox_run.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_replay_matrix": str(DEFAULT_REPLAY_MATRIX),
        "summary": {
            "input_row_count": len(rows),
            "executed_row_count": len(executed_rows),
            "ready_for_manual_apply_count": ready_count,
            "execution_status_counts": dict(sorted(execution_counts.items())),
            "runtime_mutation_allowed": False,
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
            "probe_only": not promotion_credit_allowed,
        },
        "rows": executed_rows,
        "claim_boundary": [
            "This physical sandbox run enriches V2 replay rows but does not mutate runtime overlays.",
            "Rows with blocked sandbox attestation produce no V2 promotion credit.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Zero-Trust V2 replay rows through physical sandbox wrapper.")
    parser.add_argument("--replay-matrix", default=str(DEFAULT_REPLAY_MATRIX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--allow-promotion-credit", action="store_true")
    parser.add_argument("--command", nargs="+", default=["/bin/echo", "nexus-zero-trust-v2-physical-row"])
    args = parser.parse_args(argv)
    signing_secret = os.environ.get("NEXUS_V2_RUNNER_SIGNING_SECRET", "local-nonproduction-v2-physical-runner")
    result = run_zero_trust_v2_physical_sandbox_matrix(
        replay_matrix=read_json(args.replay_matrix),
        command=args.command,
        signing_secret=signing_secret,
        limit=args.limit,
        promotion_credit_allowed=args.allow_promotion_credit,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
