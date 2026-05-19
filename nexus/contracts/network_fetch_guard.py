from __future__ import annotations

import ipaddress
from urllib.parse import urlparse
from typing import Any


NETWORK_FETCH_GUARD_SCHEMA = "nexus.network_fetch_guard.v1"
ALLOWED_SCHEMES = {"http", "https"}


def build_network_fetch_guard_receipt(
    *,
    url: str,
    resolved_ips: list[str] | tuple[str, ...] = (),
    redirect_url: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        blockers.append("unsupported_url_scheme")
    if not parsed.hostname:
        blockers.append("missing_hostname")
    blockers.extend(_ip_blockers(resolved_ips, prefix="resolved"))
    if redirect_url:
        redirect = urlparse(redirect_url)
        if redirect.scheme not in ALLOWED_SCHEMES:
            blockers.append("redirect_unsupported_scheme")
        if not redirect.hostname:
            blockers.append("redirect_missing_hostname")
    return {
        "schema": NETWORK_FETCH_GUARD_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "url": url,
        "redirect_url": redirect_url or "",
        "resolved_ips": list(resolved_ips),
        "network_fetch_allowed": not blockers,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "blockers": sorted(set(blockers)),
        "claim_boundary": [
            "Network fetch guards validate URL and resolved-address safety only.",
            "Call sites must re-run DNS and redirect validation at fetch time.",
        ],
    }


def _ip_blockers(ips: list[str] | tuple[str, ...], *, prefix: str) -> list[str]:
    blockers: list[str] = []
    for raw in ips:
        try:
            address = ipaddress.ip_address(str(raw))
        except ValueError:
            blockers.append(f"{prefix}_ip_invalid")
            continue
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        ):
            blockers.append(f"{prefix}_ip_not_public")
    return blockers
