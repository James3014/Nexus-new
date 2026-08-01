#!/usr/bin/env python3
"""Authenticated loopback HTTP transport for the single Nexus MCP gateway."""

from __future__ import annotations

import hmac
import http.server
import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.orchestrator.unified_mcp_gateway import (  # noqa: E402
    CANONICAL_SOURCE_ROOT,
    GATEWAY_NAME,
    GATEWAY_VERSION,
    TOOL_MANIFEST_REVISION,
    UnifiedMCPGateway,
)

TOKEN_ENV = "NEXUS_MCP_GATEWAY_TOKEN"
HOST_ENV = "NEXUS_MCP_GATEWAY_HOST"
PORT_ENV = "NEXUS_MCP_GATEWAY_PORT"
ALLOW_REMOTE_ENV = "NEXUS_MCP_GATEWAY_ALLOW_REMOTE"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
MAX_BODY_BYTES = 1024 * 1024


class GatewayHTTPConfigError(RuntimeError):
    pass


def resolve_bind_address(env: Mapping[str, str] | None = None) -> tuple[str, int]:
    environ = os.environ if env is None else env
    host = environ.get(HOST_ENV, DEFAULT_HOST)
    port = int(environ.get(PORT_ENV, str(DEFAULT_PORT)))
    try:
        loopback = ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if not loopback and environ.get(ALLOW_REMOTE_ENV) != "1":
        raise GatewayHTTPConfigError(f"non-loopback bind requires {ALLOW_REMOTE_ENV}=1")
    if port < 1 or port > 65535:
        raise GatewayHTTPConfigError("port must be between 1 and 65535")
    return host, port


def _git_head() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=3, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def runtime_identity() -> dict[str, Any]:
    return {
        "status": "ok",
        "server": GATEWAY_NAME,
        "version": GATEWAY_VERSION,
        "transport": "streamable_http",
        "repo_root": str(CANONICAL_SOURCE_ROOT),
        "git_head": _git_head(),
        "tool_manifest_revision": TOOL_MANIFEST_REVISION,
        "tool_count": len(UnifiedMCPGateway.tool_specs()),
    }


def build_handler(gateway: UnifiedMCPGateway, *, token: str, max_body_bytes: int = MAX_BODY_BYTES) -> type[http.server.BaseHTTPRequestHandler]:
    class GatewayHTTPHandler(http.server.BaseHTTPRequestHandler):
        server_version = "NexusMCPGatewayHTTP/1.0"
        sys_version = ""

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            return hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}")

        def do_GET(self) -> None:
            if urlsplit(self.path).path == "/health":
                self._send_json(200, runtime_identity())
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/mcp":
                self._send_json(404, {"error": "not found"})
                return
            if not self._authorized():
                self.send_response(401)
                self.send_header("WWW-Authenticate", "Bearer")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._send_json(411, {"error": "content length required"})
                return
            try:
                length = int(raw_length)
            except ValueError:
                self._send_json(400, {"error": "invalid content length"})
                return
            if length < 0 or length > max_body_bytes:
                self._send_json(413, {"error": "request body too large"})
                return
            try:
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                response = gateway.handle(request)
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
                return
            if response is None:
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._send_json(200, response)

        def do_PUT(self) -> None:
            self._send_json(405, {"error": "method not allowed"})

        def do_PATCH(self) -> None:
            self._send_json(405, {"error": "method not allowed"})

        def do_DELETE(self) -> None:
            self._send_json(405, {"error": "method not allowed"})

    return GatewayHTTPHandler


def main() -> int:
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        raise SystemExit(f"{TOKEN_ENV} is required")
    host, port = resolve_bind_address()
    server = http.server.ThreadingHTTPServer((host, port), build_handler(UnifiedMCPGateway(), token=token))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
