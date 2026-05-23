from __future__ import annotations

import socket

import pytest

from scripts.bench.runner_socket_barrier import (
    SocketBlockedError,
    assert_runner_socket_allowed,
    block_external_runner_sockets,
    maybe_block_external_runner_sockets,
    runner_socket_barrier_enabled,
)


def test_assert_runner_socket_allowed_blocks_external_host_with_target_details():
    with pytest.raises(SocketBlockedError) as exc_info:
        assert_runner_socket_allowed("example.com", 443, url="https://example.com/resource")

    message = str(exc_info.value)
    assert "example.com" in message
    assert "443" in message
    assert "https://example.com/resource" in message


def test_block_external_runner_sockets_blocks_create_connection_before_dns():
    with block_external_runner_sockets(), pytest.raises(SocketBlockedError, match="example.com"):
        socket.create_connection(("example.com", 443), timeout=0.01)


def test_block_external_runner_sockets_allows_loopback_connection():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        with block_external_runner_sockets():
            client = socket.create_connection(("127.0.0.1", port), timeout=1)
            conn, _ = server.accept()
        client.close()
        conn.close()
    finally:
        server.close()


def test_runner_socket_barrier_enabled_is_explicit_opt_in():
    assert runner_socket_barrier_enabled({}) is False
    assert runner_socket_barrier_enabled({"NEXUS_BENCH_BLOCK_EXTERNAL_RUNNER_SOCKETS": "0"}) is False
    assert runner_socket_barrier_enabled({"NEXUS_BENCH_BLOCK_EXTERNAL_RUNNER_SOCKETS": "1"}) is True


def test_maybe_block_external_runner_sockets_is_noop_when_disabled():
    original_create_connection = socket.create_connection
    with maybe_block_external_runner_sockets(enabled=False):
        assert socket.create_connection is original_create_connection
