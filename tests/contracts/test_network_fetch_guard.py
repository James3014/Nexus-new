from __future__ import annotations

from nexus.contracts.network_fetch_guard import build_network_fetch_guard_receipt


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
