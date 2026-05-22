from __future__ import annotations

from typing import Any

from nexus.contracts.network_fetch_guard import build_network_fetch_guard_receipt


LOCAL_GATEWAY_SCHEMA = "nexus.local_gateway.v1"
HIGH_RISK_TARGET_CLASSES = {"provider_call", "tool_call", "network_fetch"}


def build_local_gateway_receipt(
    *,
    target: str,
    target_class: str,
    resolved_ips: list[str] | tuple[str, ...] = (),
    retry_after_sec: float = 0.0,
    circuit_open: bool = False,
    backoff_reason: str = "",
) -> dict[str, Any]:
    blockers: list[str] = []
    normalized_class = str(target_class or "").strip()
    if normalized_class not in HIGH_RISK_TARGET_CLASSES:
        blockers.append("unknown_target_class")
    if circuit_open:
        blockers.append("circuit_open")
    if retry_after_sec < 0:
        blockers.append("invalid_retry_after")

    network_receipt: dict[str, Any] = {}
    if normalized_class == "network_fetch":
        network_receipt = build_network_fetch_guard_receipt(url=target, resolved_ips=resolved_ips)
        blockers.extend(str(item) for item in network_receipt.get("blockers", []))

    unique_blockers = sorted(set(blockers))
    return {
        "schema": LOCAL_GATEWAY_SCHEMA,
        "status": "PASS" if not unique_blockers else "RETURN",
        "target": target,
        "target_class": normalized_class,
        "allowed": not unique_blockers,
        "retry_policy": {
            "retry_after_sec": max(0.0, float(retry_after_sec)),
            "backoff_reason": str(backoff_reason or ""),
            "circuit_open": bool(circuit_open),
        },
        "network_receipt": network_receipt,
        "blockers": unique_blockers,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }
