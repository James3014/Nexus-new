from __future__ import annotations

from nexus.contracts.network_fetch_guard import build_network_fetch_guard_receipt
from nexus.infrastructure.guarded_fetch import GuardedFetcher, GuardedFetchError


def test_network_fetch_guard_allows_public_http_with_public_dns() -> None:
    receipt = build_network_fetch_guard_receipt(
        url="https://example.com/skill",
        resolved_ips=["93.184.216.34"],
    )

    assert receipt["schema"] == "nexus.network_fetch_guard.v1"
    assert receipt["status"] == "PASS"
    assert receipt["network_fetch_allowed"] is True
    assert receipt["public_benchmark_allowed"] is False


def test_network_fetch_guard_blocks_private_resolved_ip() -> None:
    receipt = build_network_fetch_guard_receipt(
        url="https://example.com/skill",
        resolved_ips=["127.0.0.1", "10.0.0.4", "169.254.169.254"],
    )

    assert receipt["status"] == "RETURN"
    assert receipt["network_fetch_allowed"] is False
    assert receipt["blockers"] == ["resolved_ip_not_public"]


def test_network_fetch_guard_blocks_file_redirect() -> None:
    receipt = build_network_fetch_guard_receipt(
        url="https://example.com/skill",
        resolved_ips=["93.184.216.34"],
        redirect_url="file:///etc/passwd",
    )

    assert receipt["status"] == "RETURN"
    assert "redirect_unsupported_scheme" in receipt["blockers"]
    assert "redirect_missing_hostname" in receipt["blockers"]


def test_guarded_fetcher_blocks_private_dns_before_transport() -> None:
    calls = []

    def transport(url: str, timeout: float):
        calls.append(url)
        return b"secret", url

    fetcher = GuardedFetcher(
        resolver=lambda _host, _port: ["127.0.0.1"],
        transport=transport,
    )

    try:
        fetcher.fetch_text("https://example.com/skill")
    except GuardedFetchError as exc:
        assert "resolved_ip_not_public" in exc.receipt["blockers"]
    else:
        raise AssertionError("expected guarded fetch to block private DNS")
    assert calls == []


def test_guarded_fetcher_blocks_unsafe_redirect_result() -> None:
    fetcher = GuardedFetcher(
        resolver=lambda _host, _port: ["93.184.216.34"],
        transport=lambda _url, _timeout: (b"secret", "file:///etc/passwd"),
    )

    try:
        fetcher.fetch_text("https://example.com/skill")
    except GuardedFetchError as exc:
        assert "redirect_unsupported_scheme" in exc.receipt["blockers"]
    else:
        raise AssertionError("expected guarded fetch to block file redirect")


def test_guarded_fetcher_revalidates_redirect_dns() -> None:
    def resolver(host: str, _port: int | None):
        return ["10.0.0.7"] if host == "internal.example" else ["93.184.216.34"]

    fetcher = GuardedFetcher(
        resolver=resolver,
        transport=lambda _url, _timeout: (b"secret", "https://internal.example/secret"),
    )

    try:
        fetcher.fetch_text("https://example.com/skill")
    except GuardedFetchError as exc:
        assert "redirect_target_resolved_ip_not_public" in exc.receipt["blockers"]
    else:
        raise AssertionError("expected guarded fetch to block private redirect DNS")
