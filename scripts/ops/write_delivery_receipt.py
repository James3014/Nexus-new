#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from nexus.delivery.receipt import write_delivery_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-path", required=True)
    parser.add_argument("--evidence-path", required=True)
    parser.add_argument("--baseline-path", required=True)
    parser.add_argument("--acceptance-report", required=True)
    parser.add_argument("--acceptance-policy", required=True)
    parser.add_argument("--acceptance-exit-code", required=True, type=int)
    parser.add_argument("--acceptance-status", required=True)
    parser.add_argument("--acceptance-gate", required=True)
    parser.add_argument("--acceptance-primary", required=True)
    args = parser.parse_args()

    write_delivery_receipt(
        receipt_path=Path(args.receipt_path),
        evidence_path=Path(args.evidence_path),
        baseline_path=Path(args.baseline_path),
        acceptance_report=Path(args.acceptance_report),
        acceptance_policy=args.acceptance_policy,
        acceptance_exit_code=args.acceptance_exit_code,
        acceptance_status=args.acceptance_status,
        acceptance_gate=str(args.acceptance_gate).lower() == "true",
        acceptance_primary=args.acceptance_primary,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
