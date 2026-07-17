"""Formal B vs D projection from fused live pilot receipts (Measure M0).

NOT a product route. Reuses decide_fused_slice_verdict — no duplicated decision
logic, no public_claim unlock. Empty/UNAVAILABLE tokens stay numeric-empty so
efficiency gates can honestly REVISE.
"""
from __future__ import annotations

import re
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
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _is_sha256(value: Any) -> bool:
    return bool(_SHA256_RE.match(str(value or "").strip()))


def _formal_invalid(reason: str, pilot: dict[str, Any], **extra: Any) -> dict[str, Any]:
    blockers = list(extra.pop("formal_blockers", None) or [])
    if reason and reason not in blockers:
        blockers.insert(0, reason)
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
        "contract_path_ok": False,
        "provider_receipt_verified": False,
        "verifier_receipt_verified": False,
        "packet_consumption_verified": False,
        "formal_blockers": blockers,
        "simulated": "demo" in reason or "synthetic" in reason or "simulated" in reason,
        "source_pilot_schema": (pilot or {}).get("schema") if isinstance(pilot, dict) else None,
        "token_samples_numeric": {"b": [], "d": []},
    }
    out.update(extra)
    out["public_claim_allowed"] = False
    out["formal_eligible"] = False
    out["contract_path_ok"] = False
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


def _verify_provider_receipt(prov: Any) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not isinstance(prov, Mapping) or not prov:
        return False, ["provider_receipt_missing"]
    provider = str(prov.get("provider") or prov.get("provider_id") or "").strip().lower()
    if provider != "agy":
        blockers.append(f"provider_not_agy:{provider or 'missing'}")
    try:
        model_calls = int(prov.get("model_calls") or 0)
    except (TypeError, ValueError):
        model_calls = 0
    if model_calls <= 0:
        blockers.append("provider_model_calls_not_positive")
    auth = bool(
        prov.get("authenticated")
        or prov.get("authorized")
        or str(prov.get("auth_status") or "").lower() in {"authenticated", "authorized", "ok"}
    )
    if not auth:
        blockers.append("provider_auth_not_proven")
    # successful invocation / run identity
    run_id = str(
        prov.get("run_id")
        or prov.get("invocation_id")
        or prov.get("response_identity")
        or ""
    ).strip()
    success = bool(
        prov.get("success")
        or prov.get("invocation_ok")
        or str(prov.get("status") or "").lower() in {"ok", "success", "succeeded", "pass"}
    )
    if not run_id:
        blockers.append("provider_run_identity_missing")
    if not success:
        blockers.append("provider_invocation_not_successful")
    # reject fixture/synthetic
    blob = " ".join(str(x) for x in (provider, prov.get("source"), prov.get("note"), run_id)).lower()
    if "fixture" in blob or "synthetic" in blob or str(prov.get("fixture") or "").lower() in {
        "1",
        "true",
        "yes",
    }:
        blockers.append("provider_fixture_or_synthetic")
    # confirmed=true alone is insufficient
    if set(prov.keys()) <= {"confirmed", "provider"} and prov.get("confirmed") is True:
        blockers.append("provider_confirmed_bool_insufficient")
    return (not blockers), blockers


def _verify_verifier_receipt(ver: Any) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not isinstance(ver, Mapping) or not ver:
        return False, ["verifier_receipt_missing"]
    status = str(ver.get("status") or ver.get("verifier_status") or "").upper()
    if status not in {"PASS", "PASSED", "OK", "VERIFIED", "SUCCESS"}:
        blockers.append(f"verifier_status_not_pass:{status or 'missing'}")
    art = str(
        ver.get("verifier_artifact_hash")
        or ver.get("artifact_hash")
        or ver.get("verifier_artifact")
        or ""
    ).strip()
    src = str(ver.get("source_hash") or ver.get("verifier_source_hash") or "").strip()
    if not _is_sha256(art):
        blockers.append("verifier_artifact_hash_not_sha256")
    if not _is_sha256(src):
        blockers.append("verifier_source_hash_not_sha256")
    # Binding evidence required — status alone insufficient
    bind = bool(
        ver.get("artifact_source_bound")
        or ver.get("binding_proof")
        or ver.get("bound")
        or ver.get("seal_ok")
        or ver.get("artifact_binds_source")
    )
    if not bind:
        blockers.append("verifier_artifact_source_binding_missing")
    if set(str(k) for k in ver.keys()) <= {"status"}:
        blockers.append("verifier_status_only_insufficient")
    return (not blockers), blockers


def _packet_proof_ok(proof: Any, *, expected_packet_hash: str = "") -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not isinstance(proof, Mapping) or not proof:
        return False, ["packet_consumption_proof_missing"]
    if proof.get("consumed") is not True:
        blockers.append("packet_not_consumed")
    ph = str(proof.get("packet_hash") or "").strip()
    if not _is_sha256(ph):
        blockers.append("packet_hash_not_sha256")
    exp = str(expected_packet_hash or "").strip()
    if exp and ph and ph != exp:
        blockers.append("packet_hash_mismatch_vap")
    # reject {"anything": true} style
    if "consumed" not in proof or "packet_hash" not in proof:
        blockers.append("packet_proof_fields_incomplete")
    return (not blockers), blockers


def _verify_pairs(
    pairs: list[Any],
    *,
    pilot: Mapping[str, Any],
    packet_hash: str,
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    if not pairs:
        return False, ["missing_pairs"], []
    claimed_n = int(pilot.get("pair_count") or 0)
    if claimed_n != len(pairs):
        blockers.append(f"pair_count_mismatch:claimed={claimed_n}:actual={len(pairs)}")
    ids: list[str] = []
    task_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    pilot_task = str(pilot.get("task_id") or "").strip()
    for i, p in enumerate(pairs):
        if not isinstance(p, Mapping):
            blockers.append(f"pair_not_mapping:{i}")
            continue
        row = dict(p)
        pid = str(row.get("pair_id") or "").strip()
        if not pid:
            blockers.append(f"pair_id_missing:{i}")
        else:
            if pid in ids:
                blockers.append(f"pair_id_duplicate:{pid}")
            ids.append(pid)
        tid = str(row.get("task_id") or pilot_task or "").strip()
        if not tid:
            blockers.append(f"pair_task_identity_missing:{i}")
        else:
            task_ids.add(tid)
        # treatment core equality
        if row.get("treatment_equal") is not True and not row.get("treatment_fingerprint"):
            blockers.append(f"pair_treatment_core_missing:{i}")
        if row.get("d_assist_credited"):
            proof = row.get("packet_consumption_proof") or pilot.get("packet_consumption_proof")
            ok, pb = _packet_proof_ok(proof, expected_packet_hash=packet_hash)
            if not ok:
                blockers.extend(f"pair{i}:{b}" for b in pb)
                row["d_assist_credited"] = False
        normalized.append(row)
    if len(task_ids) > 1:
        blockers.append("pair_task_identity_inconsistent")
    return (not blockers), blockers, normalized


def formal_from_pilot(pilot: dict[str, Any]) -> dict[str, Any]:
    """Project pilot receipt fields into a formal-phase fused verdict.

    Requires authentic provider/verifier/packet/pair proofs. Always sets
    public_claim_allowed=False. Never trusts caller contract_path_ok alone.
    """
    if not isinstance(pilot, dict):
        raise TypeError("pilot must be a dict")

    schema = str(pilot.get("schema") or "").strip()
    if schema in DEMO_OR_SIMULATED_SCHEMAS or bool(pilot.get("simulated")):
        return _formal_invalid(
            "simulated_or_demo_pilot_ineligible_for_formal_m0",
            pilot,
            simulated=True,
        )
    if schema not in ALLOWED_LIVE_PILOT_SCHEMAS:
        return _formal_invalid(
            f"disallowed_pilot_schema:{schema or 'missing'}",
            pilot,
            simulated=False,
        )

    pairs = list(pilot.get("pairs") or [])
    formal_blockers: list[str] = []

    prov_ok, prov_blockers = _verify_provider_receipt(pilot.get("provider_receipt"))
    formal_blockers.extend(prov_blockers)

    ver_ok, ver_blockers = _verify_verifier_receipt(pilot.get("verifier_receipt"))
    formal_blockers.extend(ver_blockers)

    # Packet hash from VAP / assist packet
    vap = pilot.get("vap_packet") if isinstance(pilot.get("vap_packet"), Mapping) else {}
    assist = pilot.get("assist_packet") if isinstance(pilot.get("assist_packet"), Mapping) else {}
    pkt_proof = (
        pilot.get("packet_consumption_proof")
        if isinstance(pilot.get("packet_consumption_proof"), Mapping)
        else {}
    )
    expected_packet = str(
        pilot.get("packet_hash")
        or vap.get("packet_hash")
        or assist.get("packet_hash")
        or pkt_proof.get("packet_hash")
        or ""
    ).strip()
    pkt_ok, pkt_blockers = _packet_proof_ok(
        pilot.get("packet_consumption_proof"),
        expected_packet_hash=expected_packet if _is_sha256(expected_packet) else "",
    )
    # If no pilot-level packet proof, still require per-credited-pair proofs later
    if not isinstance(pilot.get("packet_consumption_proof"), Mapping):
        formal_blockers.append("packet_consumption_proof_missing")
        pkt_ok = False
    else:
        formal_blockers.extend(pkt_blockers)

    pairs_ok, pair_blockers, pairs = _verify_pairs(
        pairs,
        pilot=pilot,
        packet_hash=expected_packet if _is_sha256(expected_packet) else str(
            (pilot.get("packet_consumption_proof") or {}).get("packet_hash") or ""
            if isinstance(pilot.get("packet_consumption_proof"), Mapping)
            else ""
        ),
    )
    formal_blockers.extend(pair_blockers)

    provider_receipt_verified = prov_ok
    verifier_receipt_verified = ver_ok
    packet_consumption_verified = pkt_ok and all(
        (not p.get("d_assist_credited"))
        or (
            isinstance(p.get("packet_consumption_proof"), Mapping)
            and p["packet_consumption_proof"].get("consumed") is True
            and _is_sha256(p["packet_consumption_proof"].get("packet_hash"))
        )
        for p in pairs
    )
    # Recompute packet_consumption_verified after pair credit stripping
    if any(p.get("d_assist_credited") for p in pairs) and not packet_consumption_verified:
        if "packet_consumption_incomplete" not in formal_blockers:
            formal_blockers.append("packet_consumption_incomplete")

    formal_eligible = bool(
        provider_receipt_verified
        and verifier_receipt_verified
        and packet_consumption_verified
        and pairs_ok
        and not formal_blockers
    )
    # Never trust caller contract_path_ok
    contract_path_ok = formal_eligible

    if not formal_eligible:
        return _formal_invalid(
            "formal_authenticity_failed",
            pilot,
            formal_blockers=formal_blockers,
            provider_receipt_verified=provider_receipt_verified,
            verifier_receipt_verified=verifier_receipt_verified,
            packet_consumption_verified=packet_consumption_verified,
            formal_eligible=False,
            contract_path_ok=False,
        )

    n = len(pairs)
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
        contract_path_ok=True,  # only after authenticity gates
    )
    decision["public_claim_allowed"] = False
    decision["routing_surface_changed"] = False
    decision["production_ready"] = False
    decision["source_pilot_schema"] = pilot.get("schema")
    decision["source_pilot_verdict"] = pilot.get("pilot_verdict")
    decision["token_samples_numeric"] = {"b": b_tok, "d": d_tok}
    decision["pair_count"] = n
    decision["comparable_count"] = comp
    decision["formal_eligible"] = True
    decision["contract_path_ok"] = True
    decision["provider_receipt_verified"] = True
    decision["verifier_receipt_verified"] = True
    decision["packet_consumption_verified"] = True
    decision["formal_blockers"] = []
    decision["note"] = (
        "formal projection from authenticated pilot; KEEP does not unlock public claim; "
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
    """Allowed live schema pilot with authentic receipts → efficiency REVISE."""
    packet_hash = "b" * 64
    source_hash = "c" * 64
    artifact_hash = "d" * 64
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
        "packet_hash": packet_hash,
        "provider_receipt": {
            "provider": "agy",
            "model_calls": 2,
            "authenticated": True,
            "authorized": True,
            "success": True,
            "run_id": "agy-run-formal-1",
            "status": "ok",
        },
        "verifier_receipt": {
            "status": "VERIFIED",
            "verifier_artifact_hash": artifact_hash,
            "source_hash": source_hash,
            "artifact_source_bound": True,
            "bound": True,
        },
        "packet_consumption_proof": {
            "packet_hash": packet_hash,
            "consumed": True,
        },
        "pairs": [
            {
                "pair_id": f"p{i}",
                "task_id": "formal-task-1",
                "comparable": True,
                "treatment_equal": True,
                "treatment_fingerprint": "tf-bd-equal",
                "d_assist_credited": True,
                "packet_consumption_proof": {
                    "packet_hash": packet_hash,
                    "consumed": True,
                },
                "b_infra": False,
                "d_infra": False,
            }
            for i in range(4)
        ],
    }
