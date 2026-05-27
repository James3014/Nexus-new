#!/usr/bin/env python3
from typing import Dict, Any

def backfill_single_receipt(
    receipt_dict: Dict[str, Any],
    source: str,
    has_infra_invalid: bool,
    bundle_telemetries: Dict[str, Any]
) -> Dict[str, Any]:
    """
    🛡️ Row-Keyed Evidence Hygiene Backfill Operation.
    Enforces strict fail-closed hygiene. Establishes telemetry provenance, source attribution,
    and locks estimated/unknown telemetry to OBSERVATION_ONLY.
    """
    res = dict(receipt_dict)
    
    # 建立回補之 telemetry 結構外框，包含 source 與 infra-invalid 標籤
    telemetries = {
        "wall_time_ms": bundle_telemetries.get("wall_time_ms", 0),
        "token_usage": bundle_telemetries.get("token_usage", 0),
        "provider_costs": bundle_telemetries.get("provider_costs", 0.0),
        "overhead_ms": bundle_telemetries.get("overhead_ms", 0),
        "telemetry_source": source,
        "has_infra_invalid": has_infra_invalid,
    }
    
    # row-keyed telemetry classification rule
    if source in ("estimated", "unknown"):
        telemetries["claimability"] = "OBSERVATION_ONLY"
    elif source == "reconstructed_from_bundle" and not has_infra_invalid:
        telemetries["claimability"] = "CLAIMABLE"
    else:
        telemetries["claimability"] = "OBSERVATION_ONLY"
        
    res["telemetries"] = telemetries
    return res
