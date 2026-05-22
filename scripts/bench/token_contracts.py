from __future__ import annotations

from typing import Any


def token_data_contract(row: dict[str, Any]) -> dict[str, Any]:
    model_calls = int(row.get("model_calls", 0) or 0)
    total_tokens = int(row.get("total_tokens", 0) or 0)
    status = str(row.get("token_capture_status") or row.get("model_token_capture_status") or "").strip().lower()
    measured = total_tokens > 0 and status in {"ok", "measured"}
    if model_calls > 0 and not measured:
        return {
            "status": "DATA_CONTRACT_VIOLATION",
            "reason": "model_call_without_measured_provider_tokens",
            "source": str(row.get("gateway_token_source") or "missing"),
        }
    if model_calls <= 0:
        return {
            "status": "NOT_APPLICABLE",
            "reason": "no_model_call",
            "source": str(row.get("gateway_token_source") or "none"),
        }
    return {
        "status": "PASS",
        "reason": "",
        "source": str(row.get("gateway_token_source") or "provider"),
    }
