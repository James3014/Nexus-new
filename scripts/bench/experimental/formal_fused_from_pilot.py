#!/usr/bin/env python3
"""Project fused_live_pilot receipt → decide_fused_slice_verdict(phase=formal).

NOT a product route. Produces honest formal REVISE / KEEP / EXPERIMENT_INVALID.
Does not unlock public_claim_allowed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from nexus.services.verified_assist_contract import decide_fused_slice_verdict  # noqa: E402


def _num_list(vals: list[Any]) -> list[float]:
    out: list[float] = []
    for v in vals:
        try:
            if v is None or v == "UNAVAILABLE":
                continue
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def formal_from_pilot(pilot: dict[str, Any]) -> dict[str, Any]:
    pairs = list(pilot.get("pairs") or [])
    n = int(pilot.get("pair_count") or len(pairs) or 0)
    comp = int(pilot.get("comparable_count") or sum(1 for p in pairs if p.get("comparable")))
    infra = int(pilot.get("infra_invalid_count") or sum(1 for p in pairs if p.get("b_infra") or p.get("d_infra")))
    safety = int(pilot.get("safety_violations") or 0)
    treatment_equal = all(p.get("treatment_equal") for p in pairs) if pairs else bool(pilot.get("treatment_equal", True))
    b_solve = pilot.get("b_solve_mean")
    d_solve = pilot.get("d_solve_mean")
    tok = pilot.get("token_samples") if isinstance(pilot.get("token_samples"), dict) else {}
    b_tok = _num_list(list(tok.get("b") or []))
    d_tok = _num_list(list(tok.get("d") or []))
    packet_unconsumed = any(
        (not p.get("d_assist_credited")) for p in pairs if p.get("comparable")
    ) if pairs else False

    decision = decide_fused_slice_verdict(
        phase="formal",
        b_solve=None if b_solve is None else float(b_solve),
        d_solve=None if d_solve is None else float(d_solve),
        safety_violations=safety,
        treatment_equal=bool(treatment_equal),
        pair_count=n,
        comparable_count=comp,
        infra_invalid_count=infra,
        b_online_input_tokens=b_tok,
        d_online_input_tokens=d_tok,
        packet_often_unconsumed=packet_unconsumed,
        contract_path_ok=True,
    )
    decision["public_claim_allowed"] = False
    decision["routing_surface_changed"] = False
    decision["source_pilot_schema"] = pilot.get("schema")
    decision["source_pilot_verdict"] = pilot.get("pilot_verdict")
    decision["token_samples_numeric"] = {"b": b_tok, "d": d_tok}
    decision["note"] = (
        "formal projection from pilot; KEEP does not unlock public claim; "
        "UNAVAILABLE tokens yield efficiency REVISE when empty"
    )
    return decision


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
        pilot = {
            "schema": "nexus.fused_live_pilot.v1",
            "pilot_verdict": "PILOT_PASS",
            "pair_count": 4,
            "comparable_count": 4,
            "infra_invalid_count": 0,
            "safety_violations": 0,
            "b_solve_mean": 1.0,
            "d_solve_mean": 1.0,
            "token_samples": {"b": [], "d": []},  # UNAVAILABLE → efficiency REVISE
            "pairs": [
                {
                    "comparable": True,
                    "treatment_equal": True,
                    "d_assist_credited": True,
                    "b_infra": False,
                    "d_infra": False,
                }
                for _ in range(4)
            ],
        }
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
                "out": str(args.out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
