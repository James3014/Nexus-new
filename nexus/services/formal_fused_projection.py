"""Formal B vs D projection from fused live pilot receipts (Measure M0).

NOT a product route. Reuses decide_fused_slice_verdict — no duplicated decision
logic, no public_claim unlock. Empty/UNAVAILABLE tokens stay numeric-empty so
efficiency gates can honestly REVISE.
"""
from __future__ import annotations

from typing import Any, Mapping

from nexus.services.verified_assist_contract import decide_fused_slice_verdict

ALLOWED_LIVE_PILOT_SCHEMAS = frozenset(
    {
        "nexus.fused_live_pilot.v1",
    }
)
DEMO_OR_SIMULATED_SCHEMAS = frozenset(
    {
        "nexus.fused_live_pilot.demo.v1",
        "nexus.fused_live_pilot.synthetic.v1",
    }
)


def _formal_invalid(reason: str, pilot: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out = {
        "schema": "nexus.formal_fused_decision.v1",
        "phase": "formal",
        "verdict": "EXPERIMENT_INVALID",
        "reason": reason,
        "pair_count": int(pilot.get("pair_count") or 0) if isinstance(pilot, dict) else 0,
        "comparable_count": int(pilot.get("comparable_count") or 0) if isinstance(pilot, dict) else 0,
        "public_claim_allowed": False,
        "routing_surface_changed": False,
        "production_ready": False,
        "formal_eligible": False,
        "simulated": "demo" in reason or "synthetic" in reason or "simulated" in reason,
        "contract_path_ok": False,
        "source_pilot_schema": (pilot or {}).get("schema") if isinstance(pilot, dict) else None,
    }
    out.update(extra)
    return out



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

    schema = str(pilot.get("schema") or "").strip()
    if schema in DEMO_OR_SIMULATED_SCHEMAS or bool(pilot.get("simulated")):
        return _formal_invalid(
            "simulated_or_demo_pilot_ineligible_for_formal_m0",
            pilot,
            simulated=True,
            formal_eligible=False,
            token_samples_numeric={"b": [], "d": []},
        )
    if schema not in ALLOWED_LIVE_PILOT_SCHEMAS:
        return _formal_invalid(
            f"disallowed_pilot_schema:{schema or 'missing'}",
            pilot,
            simulated=False,
            token_samples_numeric={"b": [], "d": []},
        )

    # Require pair identity / treatment fingerprint / provider-verifier receipts
    pairs = list(pilot.get("pairs") or [])
    if not pairs and int(pilot.get("pair_count") or 0) <= 0:
        return _formal_invalid("missing_pairs", pilot)

    # Fail closed: absent/empty provider or verifier receipt → INVALID (not REVISE)
    prov = pilot.get("provider_receipt")
    ver = pilot.get("verifier_receipt")
    if prov is False or ver is False or prov in (None, "", {}, []) or ver in (None, "", {}, []):
        return _formal_invalid(
            "missing_provider_or_verifier_receipt",
            pilot,
            token_samples_numeric={"b": [], "d": []},
        )
    if not isinstance(prov, Mapping) or not isinstance(ver, Mapping):
        return _formal_invalid(
            "provider_or_verifier_receipt_not_mapping",
            pilot,
            token_samples_numeric={"b": [], "d": []},
        )
    # Minimal non-empty identity fields on receipts
    if not (prov.get("provider") or prov.get("provider_id") or prov.get("confirmed") is True):
        return _formal_invalid("provider_receipt_identity_missing", pilot)
    if not (
        ver.get("artifact_hash")
        or ver.get("verifier_artifact")
        or ver.get("source_hash")
        or str(ver.get("status") or "").upper() in {"PASS", "PASSED", "OK", "VERIFIED"}
    ):
        return _formal_invalid("verifier_receipt_identity_missing", pilot)

    pilot_task = str(pilot.get("task_id") or "").strip()
    pilot_tf = str(pilot.get("treatment_fingerprint") or "").strip()
    if not pilot_task and not pilot_tf:
        # require per-pair identity if pilot-level missing
        for p in pairs:
            if not isinstance(p, Mapping):
                return _formal_invalid("pair_not_mapping", pilot)
            if not (p.get("task_id") or p.get("pair_id")):
                return _formal_invalid("missing_pair_identity", pilot)
            if not (p.get("treatment_fingerprint") or p.get("treatment_equal") is True):
                return _formal_invalid("missing_treatment_fingerprint", pilot)

    for i, p in enumerate(pairs):
        if not isinstance(p, Mapping):
            return _formal_invalid("pair_not_mapping", pilot)
        if not (p.get("task_id") or p.get("pair_id") or pilot_task):
            return _formal_invalid("missing_pair_identity", pilot)
        # d_assist_credited requires packet consumption proof
        if p.get("d_assist_credited") and not (
            p.get("packet_consumption_proof")
            or p.get("packet_hash")
            or pilot.get("packet_consumption_proof")
        ):
            p = dict(p)
            p["d_assist_credited"] = False
            pairs[i] = p

    # contract_path_ok from real receipt fields, never hardcode True
    contract_path_ok = bool(
        pilot.get("contract_path_ok")
        if "contract_path_ok" in pilot
        else (
            schema in ALLOWED_LIVE_PILOT_SCHEMAS
            and not pilot.get("contract_path_broken")
            and isinstance(prov, Mapping)
            and isinstance(ver, Mapping)
        )
    )

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
        contract_path_ok=bool(contract_path_ok),
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
    """Deterministic simulated pilot — NOT formal M0 eligible (demo schema)."""
    return {
        "schema": "nexus.fused_live_pilot.demo.v1",
        "simulated": True,
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


def efficiency_revise_live_shaped_pilot() -> dict[str, Any]:
    """Allowed live schema pilot with empty tokens → efficiency REVISE (formal eligible)."""
    return {
        "schema": "nexus.fused_live_pilot.v1",
        "pilot_verdict": "PILOT_PASS",
        "task_id": "formal-task-1",
        "treatment_fingerprint": "tf-bd-equal",
        "pair_count": 4,
        "comparable_count": 4,
        "infra_invalid_count": 0,
        "safety_violations": 0,
        "b_solve_mean": 1.0,
        "d_solve_mean": 1.0,
        "token_samples": {"b": [], "d": []},
        "contract_path_ok": True,
        "provider_receipt": {"provider": "agy", "confirmed": True},
        "verifier_receipt": {"status": "PASS", "artifact_hash": "a" * 64},
        "packet_consumption_proof": {"packet_hash": "p" * 64, "consumed": True},
        "pairs": [
            {
                "pair_id": f"p{i}",
                "task_id": "formal-task-1",
                "comparable": True,
                "treatment_equal": True,
                "d_assist_credited": True,
                "packet_consumption_proof": {"packet_hash": "p" * 64, "consumed": True},
                "b_infra": False,
                "d_infra": False,
            }
            for i in range(4)
        ],
    }
