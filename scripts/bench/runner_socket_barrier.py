from __future__ import annotations

import contextlib
import ipaddress
import os
import socket
from collections.abc import Iterator
from collections.abc import Mapping
from typing import Any


class SocketBlockedError(OSError):
    pass


def assert_runner_socket_allowed(host: str, port: int | str | None, *, url: str = "") -> None:
    if _is_allowed_loopback_host(host):
        return
    target = f"host={host!r} port={port!r}"
    if url:
        target += f" url={url!r}"
    raise SocketBlockedError(f"benchmark runner socket blocked: {target}")


def runner_socket_barrier_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return str(source.get("NEXUS_BENCH_BLOCK_EXTERNAL_RUNNER_SOCKETS", "")).strip().lower() in {"1", "true", "yes"}


@contextlib.contextmanager
def maybe_block_external_runner_sockets(*, enabled: bool | None = None) -> Iterator[None]:
    active = runner_socket_barrier_enabled() if enabled is None else bool(enabled)
    if not active:
        yield
        return
    with block_external_runner_sockets():
        yield


@contextlib.contextmanager
def block_external_runner_sockets() -> Iterator[None]:
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        host, port = _host_port_from_address(address)
        assert_runner_socket_allowed(host, port)
        return original_connect(sock, address)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        host, port = _host_port_from_address(address)
        assert_runner_socket_allowed(host, port)
        return original_create_connection(address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.create_connection = guarded_create_connection
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create_connection


def _host_port_from_address(address: Any) -> tuple[str, int | str | None]:
    if isinstance(address, tuple) and len(address) >= 2:
        return str(address[0]), address[1]
    if isinstance(address, str):
        return address, None
    return str(address), None


def _is_allowed_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False
