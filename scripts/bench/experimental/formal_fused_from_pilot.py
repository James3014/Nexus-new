#!/usr/bin/env python3
"""CLI: project fused_live_pilot receipt → formal decide_fused_slice_verdict.

NOT a product route. Logic lives in nexus.services.formal_fused_projection.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from nexus.services.formal_fused_projection import (  # noqa: E402
    efficiency_revise_demo_pilot,
    formal_from_pilot,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pilot", type=Path, help="Path to fused_live_pilot JSON")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--synthetic-demo",
        action="store_true",
        help="Emit a deterministic formal path without live cloud (honest REVISE on efficiency)",
    )
    args = p.parse_args(argv)

    if args.synthetic_demo:
        pilot = efficiency_revise_demo_pilot()
    else:
        if not args.pilot or not args.pilot.exists():
            print("need --pilot PATH or --synthetic-demo", file=sys.stderr)
            return 2
        pilot = json.loads(args.pilot.read_text(encoding="utf-8"))

    decision = formal_from_pilot(pilot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": decision.get("verdict"),
                "reason": decision.get("reason"),
                "public_claim_allowed": decision.get("public_claim_allowed"),
                "pair_count": decision.get("pair_count"),
                "out": str(args.out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
