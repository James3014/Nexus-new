import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway  # noqa: E402
from scripts.ops.nexus_mcp_gateway_http import (  # noqa: E402
    ALLOW_REMOTE_ENV,
    build_handler,
    resolve_bind_address,
    runtime_identity,
)


class FakeService:
    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self):
        return {"actionable_count": 0, "tasks": []}


def _server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(UnifiedMCPGateway(service=FakeService()), token="secret"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(server, payload, *, token=None):
    url = f"http://127.0.0.1:{server.server_port}/mcp"
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(request, timeout=3)


def test_loopback_default_and_remote_opt_in():
    assert resolve_bind_address({}) == ("127.0.0.1", 8766)
    try:
        resolve_bind_address({"NEXUS_MCP_GATEWAY_HOST": "0.0.0.0"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("remote bind must fail closed")
    assert resolve_bind_address({"NEXUS_MCP_GATEWAY_HOST": "0.0.0.0", ALLOW_REMOTE_ENV: "1"}) == ("0.0.0.0", 8766)


def test_health_exposes_one_gateway_identity():
    server, thread = _server()
    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=3)
        payload = json.loads(response.read())
        assert payload["server"] == "nexus-mcp-gateway"
        assert payload["tool_count"] == len(UnifiedMCPGateway.tool_specs())
        assert payload["git_head"]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_mcp_requires_bearer_and_forwards_jsonrpc():
    server, thread = _server()
    try:
        try:
            _request(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("missing bearer token must fail")
        response = _request(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, token="secret")
        payload = json.loads(response.read())
        assert len(payload["result"]["tools"]) == len(UnifiedMCPGateway.tool_specs())
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_non_post_mcp_is_rejected():
    server, thread = _server()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/mcp", method="GET")
        try:
            urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("GET /mcp must fail")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_runtime_identity_function_is_deterministic():
    first = runtime_identity()
    second = runtime_identity()
    assert first == second
