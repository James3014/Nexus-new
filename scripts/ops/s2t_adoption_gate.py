#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from nexus.contracts.s2t_policy import S2TAdoptionDecision, S2TAdoptionMetrics


def evaluate_metrics_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "passed": False,
            "metrics": {},
            "decision": {"status": "shadow_only", "reason_codes": ["metrics_missing"]},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = S2TAdoptionMetrics(**payload)
    decision = S2TAdoptionDecision.from_metrics(metrics)
    return {
        "passed": decision.status == "strict_opt_in",
        "metrics": asdict(metrics),
        "decision": asdict(decision),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate S2T adoption readiness from metrics JSON.")
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        report = evaluate_metrics_file(args.metrics)
    except Exception as exc:  # noqa: BLE001 - command boundary returns structured failure.
        report = {
            "passed": False,
            "metrics": {},
            "decision": {"status": "shadow_only", "reason_codes": ["invalid_metrics"]},
            "error": str(exc),
        }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
