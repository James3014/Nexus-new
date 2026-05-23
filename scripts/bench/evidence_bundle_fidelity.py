from __future__ import annotations

from typing import Any, Mapping


_PUBLIC_GATE_CHECK_KEYS = (
    "hidden_verifier_mode",
    "nexus_wearing_valid_rate",
    "model_uses_nexus_rate",
    "nexus_context_delivered_rate",
    "nexus_usage_valid_rate",
    "claim_verified_rate",
    "route_decision_present_rate",
    "provider_token_measured_rate_with",
    "provider_token_measured_rate_without",
    "wall_cost_ratio_with_over_without",
    "token_cost_ratio_with_over_without",
    "model_call_ratio_with_over_without",
)


def _section(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def extract_telemetry_fidelity_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return stable telemetry fields for refactor fidelity checks."""
    public_claim_gate = _section(payload, "public_claim_gate")
    public_gate_checks = _section(public_claim_gate, "checks")
    wall_ledger = _section(payload, "wall_ledger_conservation")
    wall_with = _section(wall_ledger, "with_nexus")
    wall_without = _section(wall_ledger, "without_nexus")

    return {
        "schema": "nexus_telemetry_fidelity_snapshot_v1",
        "telemetry_completeness": dict(_section(payload, "telemetry_completeness")),
        "nexus_wearing": dict(_section(payload, "nexus_wearing")),
        "public_gate_checks": {
            key: public_gate_checks.get(key)
            for key in _PUBLIC_GATE_CHECK_KEYS
        },
        "wall_ledger_conservation": {
            "telemetry_invalid": wall_ledger.get("telemetry_invalid"),
            "with_conserved_rate": wall_with.get("conserved_rate"),
            "without_conserved_rate": wall_without.get("conserved_rate"),
            "with_reason_codes": list(wall_with.get("reason_codes", []) or []),
            "without_reason_codes": list(wall_without.get("reason_codes", []) or []),
        },
        "posture": {
            "public_claim_gate": public_claim_gate.get("verdict"),
            "public_verified_delivery_claim_gate": _section(
                payload,
                "public_verified_delivery_claim_gate",
            ).get("verdict"),
            "public_cost_claim_gate": _section(payload, "public_cost_claim_gate").get("verdict"),
            "public_cost_efficiency_claim_gate": _section(
                payload,
                "public_cost_efficiency_claim_gate",
            ).get("verdict"),
            "valid_comparison_readiness_gate": _section(
                payload,
                "valid_comparison_readiness_gate",
            ).get("status"),
            "public_claim_posture_key": _section(payload, "public_claim_posture").get("public_wording_key"),
            "training_eligibility_status": _section(payload, "training_eligibility_posture").get("status"),
        },
    }
