"""Formal B vs D projection from fused live pilot receipts (Measure M0).

NOT a product route. Reuses decide_fused_slice_verdict — no duplicated decision
logic, no public_claim unlock. Empty/UNAVAILABLE tokens stay numeric-empty so
efficiency gates can honestly REVISE.
"""
from __future__ import annotations

from typing import Any

from nexus.services.verified_assist_contract import decide_fused_slice_verdict


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
    """Project pilot receipt fields into a formal-phase fused verdict.

    Requires pair_count > 0 for a non-glue formal path. Always sets
    public_claim_allowed=False and routing_surface_changed=False.
    """
    if not isinstance(pilot, dict):
        raise TypeError("pilot must be a dict")

    pairs = list(pilot.get("pairs") or [])
    n = int(pilot.get("pair_count") or len(pairs) or 0)
    comp = int(
        pilot.get("comparable_count")
        or sum(1 for p in pairs if p.get("comparable"))
    )
    infra = int(
        pilot.get("infra_invalid_count")
        or sum(1 for p in pairs if p.get("b_infra") or p.get("d_infra"))
    )
    safety = int(pilot.get("safety_violations") or 0)
    treatment_equal = (
        all(p.get("treatment_equal") for p in pairs)
        if pairs
        else bool(pilot.get("treatment_equal", True))
    )
    b_solve = pilot.get("b_solve_mean")
    d_solve = pilot.get("d_solve_mean")
    tok = pilot.get("token_samples") if isinstance(pilot.get("token_samples"), dict) else {}
    b_tok = _num_list(list(tok.get("b") or []))
    d_tok = _num_list(list(tok.get("d") or []))
    packet_unconsumed = (
        any((not p.get("d_assist_credited")) for p in pairs if p.get("comparable"))
        if pairs
        else False
    )

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
    # Task invariant: formal KEEP/REVISE never unlocks public claim
    decision["public_claim_allowed"] = False
    decision["routing_surface_changed"] = False
    decision["production_ready"] = False
    decision["source_pilot_schema"] = pilot.get("schema")
    decision["source_pilot_verdict"] = pilot.get("pilot_verdict")
    decision["token_samples_numeric"] = {"b": b_tok, "d": d_tok}
    decision["pair_count"] = n
    decision["comparable_count"] = comp
    decision["note"] = (
        "formal projection from pilot; KEEP does not unlock public claim; "
        "UNAVAILABLE tokens yield efficiency REVISE when empty"
    )
    return decision


def efficiency_revise_demo_pilot() -> dict[str, Any]:
    """Deterministic pilot shape: comparable pairs, empty tokens → efficiency REVISE."""
    return {
        "schema": "nexus.fused_live_pilot.v1",
        "pilot_verdict": "PILOT_PASS",
        "pair_count": 4,
        "comparable_count": 4,
        "infra_invalid_count": 0,
        "safety_violations": 0,
        "b_solve_mean": 1.0,
        "d_solve_mean": 1.0,
        "token_samples": {"b": [], "d": []},
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
