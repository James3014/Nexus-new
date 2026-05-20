from __future__ import annotations

import socket
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from nexus.contracts.network_fetch_guard import build_network_fetch_guard_receipt


class GuardedFetchError(RuntimeError):
    def __init__(self, receipt: dict[str, object]) -> None:
        self.receipt = receipt
        super().__init__(",".join(str(item) for item in receipt.get("blockers", [])))


@dataclass(frozen=True)
class GuardedFetchResponse:
    body: bytes
    final_url: str
    receipt: dict[str, object]


Transport = Callable[[str, float], tuple[bytes, str]]
Resolver = Callable[[str, int | None], list[str]]


@dataclass(frozen=True)
class GuardedFetcher:
    """Network fetch adapter that validates DNS and redirect safety at fetch time."""

    resolver: Resolver | None = None
    transport: Transport | None = None
    max_bytes: int = 200_000

    def fetch_text(self, url: str, *, timeout_sec: float = 5.0) -> str:
        response = self.fetch(url, timeout_sec=timeout_sec)
        return response.body.decode("utf-8", errors="ignore")

    def fetch(self, url: str, *, timeout_sec: float = 5.0) -> GuardedFetchResponse:
        resolved_ips = self._resolve(url)
        preflight = build_network_fetch_guard_receipt(url=url, resolved_ips=resolved_ips)
        if not preflight["network_fetch_allowed"]:
            raise GuardedFetchError(preflight)

        body, final_url = (self.transport or self._urlopen)(url, max(0.1, float(timeout_sec or 5.0)))
        redirect_url = "" if final_url == url else final_url
        final_receipt = build_network_fetch_guard_receipt(
            url=url,
            resolved_ips=resolved_ips,
            redirect_url=redirect_url or None,
        )
        if redirect_url:
            redirect_receipt = build_network_fetch_guard_receipt(
                url=redirect_url,
                resolved_ips=self._resolve(redirect_url),
            )
            redirect_blockers = [f"redirect_target_{item}" for item in redirect_receipt["blockers"]]
            if redirect_blockers:
                blockers = sorted(set(list(final_receipt["blockers"]) + redirect_blockers))
                final_receipt = {
                    **final_receipt,
                    "status": "RETURN",
                    "network_fetch_allowed": False,
                    "blockers": blockers,
                }
        if not final_receipt["network_fetch_allowed"]:
            raise GuardedFetchError(final_receipt)
        return GuardedFetchResponse(body=body[: self.max_bytes], final_url=final_url, receipt=final_receipt)

    def _resolve(self, url: str) -> list[str]:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname:
            return []
        resolver = self.resolver or _default_resolver
        return resolver(hostname, parsed.port)

    def _urlopen(self, url: str, timeout_sec: float) -> tuple[bytes, str]:
        request = urllib.request.Request(url, headers={"User-Agent": "nexus-guarded-fetch/1.0"})
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return response.read(self.max_bytes), response.geturl()


def _default_resolver(hostname: str, port: int | None) -> list[str]:
    resolved: list[str] = []
    for family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(hostname, port or 443):
        if family not in {socket.AF_INET, socket.AF_INET6}:
            continue
        ip = str(sockaddr[0])
        if ip not in resolved:
            resolved.append(ip)
    return resolved
