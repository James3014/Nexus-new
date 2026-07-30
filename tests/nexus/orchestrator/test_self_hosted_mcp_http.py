import json
from email.message import Message
from io import BytesIO
from pathlib import Path

import pytest

from nexus.orchestrator.self_hosted_mcp_http import (
    MCPHTTPBindError,
    MCPHTTPConfigError,
    build_handler,
    resolve_bind_address,
    validate_bind_host,
    verify_expected_checkout,
)


class RecordingMCP:
    def __init__(self):
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        if request.get("method") == "notifications/initialized":
            return None
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"method": request.get("method")}}


def exercise_handler(handler_cls, method, path, body=None, headers=None):
    handler = object.__new__(handler_cls)
    handler.path = path
    handler.rfile = BytesIO(b"" if body is None else json.dumps(body).encode("utf-8"))
    handler.wfile = BytesIO()
    handler.close_connection = False
    handler.status = None
    handler.response_headers = []
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    if body is not None and "Content-Length" not in message:
        message["Content-Length"] = str(len(json.dumps(body).encode("utf-8")))
    handler.headers = message

    def send_response(status, _message=None):
        handler.status = status

    def send_header(key, value):
        handler.response_headers.append((key, value))

    def end_headers():
        return None

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    getattr(handler, f"do_{method}")()
    return handler.status, dict(handler.response_headers), handler.wfile.getvalue()


def handler_for(token="test-token", mcp_server=None, max_body_bytes=1024):
    return build_handler(
        mcp_server or RecordingMCP(),
        token=token,
        repo_root=Path.cwd(),
        max_body_bytes=max_body_bytes,
    )


def test_auth_rejects_missing_and_invalid_bearer_token():
    secret = "secret-token-never-return"
    handler_cls = handler_for(secret)
    missing = exercise_handler(
        handler_cls,
        "POST",
        "/mcp",
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    invalid = exercise_handler(
        handler_cls,
        "POST",
        "/mcp",
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert missing[0] == 401
    assert invalid[0] == 401
    assert secret.encode("utf-8") not in missing[2]
    assert secret.encode("utf-8") not in invalid[2]
    assert secret not in json.dumps(missing[1])
    assert secret not in json.dumps(invalid[1])


def test_post_mcp_delegates_json_rpc_request_to_existing_handle():
    mcp = RecordingMCP()
    handler_cls = handler_for(mcp_server=mcp)
    status, headers, payload = exercise_handler(
        handler_cls,
        "POST",
        "/mcp",
        {"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}},
        headers={"Authorization": "Bearer test-token"},
    )

    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert json.loads(payload)["result"]["method"] == "tools/list"
    assert mcp.requests == [{"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}}]


def test_post_mcp_notification_returns_202():
    mcp = RecordingMCP()
    handler_cls = handler_for(mcp_server=mcp)
    status, _headers, payload = exercise_handler(
        handler_cls,
        "POST",
        "/mcp",
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        headers={"Authorization": "Bearer test-token"},
    )

    assert status == 202
    assert payload == b""
    assert mcp.requests == [{"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}]


def test_size_and_method_guards():
    handler_cls = handler_for(max_body_bytes=16)
    method_status, _method_headers, _method_payload = exercise_handler(handler_cls, "GET", "/mcp")
    size_status, _size_headers, size_payload = exercise_handler(
        handler_cls,
        "POST",
        "/mcp",
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert method_status == 405
    assert size_status == 413
    assert json.loads(size_payload)["error"] == "request body too large"


def test_default_binding_is_loopback(monkeypatch):
    monkeypatch.setenv("NEXUS_SELF_HOSTED_MCP_TOKEN", "test-token")
    monkeypatch.delenv("NEXUS_SELF_HOSTED_MCP_HOST", raising=False)
    host, _port = resolve_bind_address(port=0)
    assert host == "127.0.0.1"


def test_remote_binding_fails_closed_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("NEXUS_SELF_HOSTED_MCP_ALLOW_REMOTE", raising=False)
    with pytest.raises(MCPHTTPBindError):
        validate_bind_host("0.0.0.0")

    monkeypatch.setenv("NEXUS_SELF_HOSTED_MCP_ALLOW_REMOTE", "1")
    validate_bind_host("0.0.0.0")


def test_health_exposes_non_secret_identity():
    secret = "health-secret-never-return"
    handler_cls = handler_for(secret)
    status, headers, payload = exercise_handler(handler_cls, "GET", "/health")

    body = json.loads(payload)
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert body["status"] == "ok"
    assert body["transport"] == "streamable_http"
    assert body["cwd"] == str(Path.cwd().resolve())
    assert "git_head" in body
    assert secret not in payload.decode("utf-8")


def test_verify_expected_checkout_requires_launch_from_repo_root(tmp_path):
    repo_root = Path.cwd().resolve()
    verify_expected_checkout(repo_root, cwd=repo_root)

    with pytest.raises(MCPHTTPConfigError):
        verify_expected_checkout(repo_root, cwd=tmp_path)


def test_http_mcp_recover_verified_uncommitted_candidate():
    mcp = RecordingMCP()
    handler_cls = handler_for(mcp_server=mcp)
    status, headers, payload = exercise_handler(
        handler_cls,
        "POST",
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 88,
            "method": "tools/call",
            "params": {
                "name": "nexus_self_hosted_recover_verified_uncommitted_candidate",
                "arguments": {"task_id": "recover-http-001"},
            },
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    body = json.loads(payload)
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 88
    assert mcp.requests[-1]["params"]["name"] == "nexus_self_hosted_recover_verified_uncommitted_candidate"


def test_ops_entrypoint_handles_keyboard_interrupt_without_traceback(monkeypatch, capsys):
    from scripts.ops import nexus_self_hosted_mcp_http as entrypoint

    def interrupt(*, expected_repo_root):
        raise KeyboardInterrupt

    monkeypatch.setattr(entrypoint, "serve_from_env", interrupt)

    assert entrypoint.main() == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
