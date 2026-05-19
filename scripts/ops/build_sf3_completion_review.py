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
    build_sf3_best_candidate_search,
    build_sf3_capability_overlap_resolver,
    build_sf3_combo_probe,
    build_sf3_live_causality_probe,
    build_sf3_metadata_bias_rescue,
    build_sf3_runtime_review_gate,
)


DEFAULT_RECEIPTS = Path("docs/reports/NEXUS_SF2_LIVE_RECEIPT_VALIDATION_2026-05-18.json")
DEFAULT_REVIEW = Path("docs/reports/NEXUS_SF2_PROMOTION_REVIEW_2026-05-18.json")
DEFAULT_LIVE = Path("docs/reports/NEXUS_SF3_LIVE_CAUSALITY_PROBE_2026-05-18.json")
DEFAULT_COMBO = Path("docs/reports/NEXUS_SF3_SKILL_COMBO_PROBE_2026-05-18.json")
DEFAULT_OVERLAP = Path("docs/reports/NEXUS_SF3_CAPABILITY_OVERLAP_RESOLVER_2026-05-18.json")
DEFAULT_RESCUE = Path("docs/reports/NEXUS_SF3_METADATA_BIAS_RESCUE_2026-05-18.json")
DEFAULT_BEST = Path("docs/reports/NEXUS_SF3_BEST_CANDIDATE_SEARCH_2026-05-18.json")
DEFAULT_GATE = Path("docs/reports/NEXUS_SF3_RUNTIME_REVIEW_GATE_2026-05-18.json")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF3 causality, combo, overlap, rescue, and review gates.")
    parser.add_argument("--receipt-validation", default=str(DEFAULT_RECEIPTS))
    parser.add_argument("--promotion-review", default=str(DEFAULT_REVIEW))
    parser.add_argument("--live-causality-output", default=str(DEFAULT_LIVE))
    parser.add_argument("--combo-output", default=str(DEFAULT_COMBO))
    parser.add_argument("--overlap-output", default=str(DEFAULT_OVERLAP))
    parser.add_argument("--metadata-rescue-output", default=str(DEFAULT_RESCUE))
    parser.add_argument("--best-candidate-output", default=str(DEFAULT_BEST))
    parser.add_argument("--runtime-review-gate-output", default=str(DEFAULT_GATE))
    args = parser.parse_args(argv)

    receipts = json.loads(Path(args.receipt_validation).read_text(encoding="utf-8"))
    review = json.loads(Path(args.promotion_review).read_text(encoding="utf-8"))
    live = build_sf3_live_causality_probe(receipts)
    combo = build_sf3_combo_probe(live)
    overlap = build_sf3_capability_overlap_resolver(live)
    rescue = build_sf3_metadata_bias_rescue(review)
    best = build_sf3_best_candidate_search(live, review, combo, overlap)
    gate = build_sf3_runtime_review_gate(live, combo, best)
    _write(Path(args.live_causality_output), live)
    _write(Path(args.combo_output), combo)
    _write(Path(args.overlap_output), overlap)
    _write(Path(args.metadata_rescue_output), rescue)
    _write(Path(args.best_candidate_output), best)
    _write(Path(args.runtime_review_gate_output), gate)
    print(
        json.dumps(
            {
                "status": gate["status"],
                "sf3_closed_loop_complete": gate["summary"]["sf3_closed_loop_complete"],
                "live_effective_capability_count": live["summary"]["live_effective_capability_count"],
                "combo_pass_count": combo["summary"]["combo_pass_count"],
                "best_candidate_capability_count": best["summary"]["capability_with_default_count"],
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
