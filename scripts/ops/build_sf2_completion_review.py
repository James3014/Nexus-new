#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.sf2_bounded_probe import (
    build_sf2_completion_gate,
    build_sf2_live_receipt_validation,
    build_sf2_promotion_review,
)


DEFAULT_VERDICT = Path("docs/reports/NEXUS_SF2_FINAL_ROUTE_SKILL_VERDICT_CATALOG_2026-05-18.json")
DEFAULT_RECEIPTS = Path("docs/reports/NEXUS_SF2_LIVE_RECEIPT_VALIDATION_2026-05-18.json")
DEFAULT_REVIEW = Path("docs/reports/NEXUS_SF2_PROMOTION_REVIEW_2026-05-18.json")
DEFAULT_GATE = Path("docs/reports/NEXUS_SF2_COMPLETION_GATE_2026-05-18.json")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF2 receipt validation, promotion review, and completion gate.")
    parser.add_argument("--verdict-catalog", default=str(DEFAULT_VERDICT))
    parser.add_argument("--receipt-validation-output", default=str(DEFAULT_RECEIPTS))
    parser.add_argument("--promotion-review-output", default=str(DEFAULT_REVIEW))
    parser.add_argument("--completion-gate-output", default=str(DEFAULT_GATE))
    args = parser.parse_args(argv)

    verdict = json.loads(Path(args.verdict_catalog).read_text(encoding="utf-8"))
    receipts = build_sf2_live_receipt_validation(verdict)
    review = build_sf2_promotion_review(receipts)
    gate = build_sf2_completion_gate(verdict, receipts, review)
    _write(Path(args.receipt_validation_output), receipts)
    _write(Path(args.promotion_review_output), review)
    _write(Path(args.completion_gate_output), gate)
    print(
        json.dumps(
            {
                "status": gate["status"],
                "sf2_closed_loop_complete": gate["summary"]["sf2_closed_loop_complete"],
                "validated_capability_count": receipts["summary"]["validated_capability_count"],
                "review_item_count": review["summary"]["review_item_count"],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
