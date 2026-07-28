"""Authenticated Streamable HTTP adapter for the self-hosted MCP server."""

from __future__ import annotations

import hmac
import http.server
import ipaddress
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

from nexus.orchestrator.self_hosted_mcp import NexusSelfHostedMCPServer

TOKEN_ENV = "NEXUS_SELF_HOSTED_MCP_TOKEN"
HOST_ENV = "NEXUS_SELF_HOSTED_MCP_HOST"
PORT_ENV = "NEXUS_SELF_HOSTED_MCP_PORT"
ALLOW_REMOTE_ENV = "NEXUS_SELF_HOSTED_MCP_ALLOW_REMOTE"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_REQUEST_BODY_BYTES = 1024 * 1024


class MCPHTTPConfigError(RuntimeError):
    """Raised when the HTTP transport would start in an unsafe configuration."""


class MCPHTTPBindError(MCPHTTPConfigError):
    """Raised when bind policy rejects the configured host."""


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def require_bearer_token(env: Mapping[str, str] | None = None) -> str:
    environ = os.environ if env is None else env
    token = environ.get(TOKEN_ENV, "")
    if not token:
        raise MCPHTTPConfigError(f"{TOKEN_ENV} is required")
    return token


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def validate_bind_host(host: str, env: Mapping[str, str] | None = None) -> None:
    if _is_loopback_host(host):
        return
    environ = os.environ if env is None else env
    if environ.get(ALLOW_REMOTE_ENV) != "1":
        raise MCPHTTPBindError(
            f"non-loopback bind host rejected: set {ALLOW_REMOTE_ENV}=1 to allow remote binding"
        )


def resolve_bind_address(
    *,
    host: str | None = None,
    port: int | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str, int]:
    environ = os.environ if env is None else env
    bind_host = host if host is not None else environ.get(HOST_ENV, DEFAULT_HOST)
    bind_port = port if port is not None else int(environ.get(PORT_ENV, str(DEFAULT_PORT)))
    validate_bind_host(bind_host, environ)
    return bind_host, bind_port


def git_head(cwd: Path | str | None = None) -> str:
    root = Path(cwd or Path.cwd()).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def runtime_identity(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    return {
        "status": "ok",
        "server": "nexus-self-hosted-development",
        "transport": "streamable_http",
        "cwd": str(Path.cwd().resolve()),
        "repo_root": str(root),
        "git_head": git_head(root),
    }


def verify_expected_checkout(expected_repo_root: Path | str, cwd: Path | str | None = None) -> None:
    expected = Path(expected_repo_root).resolve()
    current = Path(cwd or Path.cwd()).resolve()
    if current != expected:
        raise MCPHTTPConfigError(f"launch cwd must be expected checkout: {expected}")
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=current,
        capture_output=True,
        text=True,
        timeout=2,
    )
    if result.returncode != 0:
        raise MCPHTTPConfigError("launch cwd is not a git checkout")
    actual = Path(result.stdout.strip()).resolve()
    if actual != expected:
        raise MCPHTTPConfigError(f"git checkout mismatch: expected {expected}, got {actual}")


def build_handler(
    mcp_server: NexusSelfHostedMCPServer,
    *,
    token: str,
    repo_root: Path | str | None = None,
    max_body_bytes: int = MAX_REQUEST_BODY_BYTES,
) -> type[http.server.BaseHTTPRequestHandler]:
    identity_root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()

    class NexusSelfHostedMCPHTTPHandler(http.server.BaseHTTPRequestHandler):
        server_version = "NexusSelfHostedMCPHTTP/1.0"
        sys_version = ""

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _is_authorized(self) -> bool:
            provided = self.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            return hmac.compare_digest(provided, expected)

        def _send_auth_failed(self) -> None:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("WWW-Authenticate", "Bearer")
            body = b'{"error":"unauthorized"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _reject_mcp_method(self) -> None:
            if urlsplit(self.path).path == "/mcp":
                self._send_json(405, {"error": "method not allowed"})
                return
            self._send_json(404, {"error": "not found"})

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/health":
                self._send_json(200, runtime_identity(identity_root))
                return
            self._reject_mcp_method()

        def do_HEAD(self) -> None:
            self._reject_mcp_method()

        def do_OPTIONS(self) -> None:
            self._reject_mcp_method()

        def do_PUT(self) -> None:
            self._reject_mcp_method()

        def do_PATCH(self) -> None:
            self._reject_mcp_method()

        def do_DELETE(self) -> None:
            self._reject_mcp_method()

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/mcp":
                self._send_json(404, {"error": "not found"})
                return
            if not self._is_authorized():
                self._send_auth_failed()
                return
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._send_json(411, {"error": "content length required"})
                return
            try:
                content_length = int(raw_length)
            except ValueError:
                self._send_json(400, {"error": "invalid content length"})
                return
            if content_length < 0 or content_length > max_body_bytes:
                self.close_connection = True
                self._send_json(413, {"error": "request body too large"})
                return
            try:
                request = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(400, {"error": "invalid json"})
                return
            if not isinstance(request, dict):
                self._send_json(400, {"error": "json-rpc request must be an object"})
                return
            try:
                response = mcp_server.handle(request)
            except Exception:
                self._send_json(500, {"error": "internal server error"})
                return
            if response is None:
                self._send_empty(202)
                return
            self._send_json(200, response)

    return NexusSelfHostedMCPHTTPHandler


def create_http_server(
    *,
    mcp_server: Optional[NexusSelfHostedMCPServer] = None,
    host: str | None = None,
    port: int | None = None,
    env: Mapping[str, str] | None = None,
    repo_root: Path | str | None = None,
    max_body_bytes: int = MAX_REQUEST_BODY_BYTES,
) -> http.server.ThreadingHTTPServer:
    environ = os.environ if env is None else env
    bind_host, bind_port = resolve_bind_address(host=host, port=port, env=environ)
    token = require_bearer_token(environ)
    handler = build_handler(
        mcp_server or NexusSelfHostedMCPServer(),
        token=token,
        repo_root=repo_root,
        max_body_bytes=max_body_bytes,
    )
    return http.server.ThreadingHTTPServer((bind_host, bind_port), handler)


def serve_from_env(*, expected_repo_root: Path | str | None = None) -> None:
    if expected_repo_root is not None:
        verify_expected_checkout(expected_repo_root)
    httpd = create_http_server(repo_root=expected_repo_root)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
