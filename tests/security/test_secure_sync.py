from pathlib import Path
import time
import json
import pytest
import socket
import ssl
from unittest.mock import MagicMock
from nexus.core.belief_contracts import HealingArtifact
from nexus.core.healing_artifacts import HealingArtifactKeyPolicy, artifact_to_packet, sign_healing_artifact
from nexus.events.transport import NexusEventBus
from nexus.security.tls_provider import TLSProvider
from nexus.security.secure_sync import RegistryMessageHandler, SecureRegistrySync, decode_sync_request

@pytest.fixture
def certs_dir(tmp_path):
    """準備測試用的憑證目錄。"""
    d = tmp_path / "certs"
    # 生成 Server 憑證
    TLSProvider(d, node_id="server")
    # 生成 Client 憑證
    TLSProvider(d, node_id="client")
    return d

def test_secure_sync_heartbeat(certs_dir):
    """驗證 mTLS 連線下的 Heartbeat 動作。"""
    registry = MagicMock()
    server_tls = TLSProvider(certs_dir, node_id="server")
    sync = SecureRegistrySync(server_tls, registry)
    
    # 在隨機連接埠啟動 Server
    sync.serve(host="127.0.0.1", port=0)
    port = sync._server_sock.getsockname()[1]
    
    client_tls = TLSProvider(certs_dir, node_id="client")
    client_ctx = client_tls.get_client_context()
    
    # 建立 mTLS 連線並發送 Heartbeat
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        with client_ctx.wrap_socket(sock, server_hostname="127.0.0.1") as ssock:
            ssock.sendall((json.dumps({"action": "heartbeat"}) + "\n").encode())
            resp_line = ssock.makefile("r").readline()
            data = json.loads(resp_line)
            assert data["status"] == "alive"

def test_secure_sync_pull_from_peer(certs_dir):
    """驗證跨節點的技能拉取 (mTLS Pull) 流程。"""
    # Server 側的 Registry Mock
    registry = MagicMock()
    registry.search.return_value = [{"skill_id": "remote_skill_001"}]
    
    server_tls = TLSProvider(certs_dir, node_id="server")
    server_sync = SecureRegistrySync(server_tls, registry)
    server_sync.serve(host="127.0.0.1", port=0)
    port = server_sync._server_sock.getsockname()[1]
    
    # Client 側發起 Pull
    client_tls = TLSProvider(certs_dir, node_id="client")
    client_sync = SecureRegistrySync(client_tls, None) # Client 不需要本地 registry
    
    results = client_sync.pull_from_peer("127.0.0.1", port, query_tokens={"test"}, task_type="repair")
    
    assert len(results) == 1
    assert results[0]["skill_id"] == "remote_skill_001"
    registry.search.assert_called_once()

def test_secure_sync_push_hydration(certs_dir):
    """驗證 mTLS 推送 (Push) 時的資料反序列化。"""
    registry = MagicMock()
    server_tls = TLSProvider(certs_dir, node_id="server")
    sync = SecureRegistrySync(server_tls, registry)
    
    sync.serve(host="127.0.0.1", port=0)
    port = sync._server_sock.getsockname()[1]
    
    client_tls = TLSProvider(certs_dir, node_id="client")
    client_ctx = client_tls.get_client_context()
    
    # 模擬推送一個 Skill payload
    payload = {
        "action": "push",
        "payload": [{
            "name": "Test Skill",
            "description": "A test skill.",
            "task_id": "T-101",
            "skill_id": "new_skill",
            "task_type": "repair",
            "success_metric": {"repair_success": True}
        }]
    }
    
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        with client_ctx.wrap_socket(sock, server_hostname="127.0.0.1") as ssock:
            ssock.sendall((json.dumps(payload) + "\n").encode())
            resp_line = ssock.makefile("r").readline()
            data = json.loads(resp_line)
            assert data["status"] == "ok"
            
    # 檢查 Registry 是否收到 upsert 呼軟
    registry.upsert.assert_called_once()
    fm = registry.upsert.call_args[0][0]
    assert fm.task_id == "T-101"
    assert fm.success_metric.repair_success is True


def test_registry_message_handler_pull_excludes_origin():
    registry = MagicMock()
    registry.search.return_value = [{"skill_id": "s1"}]
    handler = RegistryMessageHandler(registry)

    resp = handler.handle({"action": "pull", "query_tokens": ["repair"], "task_type": "bug", "max_results": 2}, "node-a")

    assert resp == {"status": "ok", "payload": [{"skill_id": "s1"}]}
    registry.search.assert_called_once_with(
        query_tokens={"repair"},
        task_type="bug",
        exclude_origin="node-a",
        max_results=2,
    )


def test_registry_message_handler_heartbeat_and_unknown_action():
    handler = RegistryMessageHandler(MagicMock())

    assert handler.handle({"action": "heartbeat"}, "node-a")["status"] == "alive"
    resp = handler.handle({"action": "unknown"}, "node-a")
    assert resp["status"] == "error"
    assert "Unknown action" in resp["message"]


def test_registry_message_handler_denies_unauthorized_action():
    handler = RegistryMessageHandler(MagicMock(), allowed_actions={"node-a": {"heartbeat"}})

    assert handler.handle({"action": "heartbeat"}, "node-a")["status"] == "alive"
    resp = handler.handle({"action": "push", "payload": []}, "node-a")

    assert resp == {"status": "error", "message": "unauthorized_action", "action": "push"}


def test_secure_sync_denies_unauthorized_action_over_socket(certs_dir):
    registry = MagicMock()
    server_tls = TLSProvider(certs_dir, node_id="server")
    sync = SecureRegistrySync(server_tls, registry, allowed_actions={"client": {"heartbeat"}})
    sync.serve(host="127.0.0.1", port=0)
    port = sync._server_sock.getsockname()[1]

    client_tls = TLSProvider(certs_dir, node_id="client")
    client_ctx = client_tls.get_client_context()

    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        with client_ctx.wrap_socket(sock, server_hostname="127.0.0.1") as ssock:
            ssock.sendall((json.dumps({"action": "push", "payload": []}) + "\n").encode())
            data = json.loads(ssock.makefile("r").readline())

    assert data == {"status": "error", "message": "unauthorized_action", "action": "push"}
    registry.upsert.assert_not_called()


def test_decode_sync_request_rejects_invalid_and_oversized_messages():
    assert decode_sync_request(b"{bad-json\n")[1] == {"status": "error", "message": "invalid_json"}
    assert decode_sync_request(b"[]\n")[1] == {"status": "error", "message": "invalid_request"}
    assert decode_sync_request(b'{"action":"heartbeat"}\n', max_bytes=4)[1] == {
        "status": "error",
        "message": "message_too_large",
    }
    req, error = decode_sync_request(b'{"action":"heartbeat"}\n')
    assert error is None
    assert req == {"action": "heartbeat"}


def test_registry_message_handler_accepts_verified_remote_healing_artifact(tmp_path):
    NexusEventBus.configure(tmp_path)
    seen = []
    NexusEventBus.subscribe("healing_artifact_announced", lambda payload: seen.append(payload))
    signed = sign_healing_artifact(
        HealingArtifact(
            task_id="task-1",
            artifact_id="heal-1",
            artifact_type="repair_plan",
            created_at="2026-05-05T00:00:00Z",
            evidence_id="EV-1",
            summary="Use scoped storage",
        ),
        key="secret",
        key_id="node-a",
    )
    handler = RegistryMessageHandler(
        None,
        healing_artifact_policy=HealingArtifactKeyPolicy(
            allowed_key_ids=frozenset({"node-a"}),
            verification_keys={"node-a": "secret"},
        ),
    )

    resp = handler.handle(
        {
            "action": "event",
            "event_type": "healing_artifact_announced",
            "payload": {"task_id": "spoofed", "packet": artifact_to_packet(signed)},
        },
        "node-a",
    )

    assert resp["status"] == "ok"
    assert resp["receipt"]["passed"] is True
    assert len(seen) == 1
    assert seen[0]["task_id"] == "task-1"
    assert seen[0]["artifact_id"] == "heal-1"
    assert seen[0]["_source_node"] == "node-a"


def test_registry_message_handler_rejects_invalid_remote_healing_artifact_without_publish(tmp_path):
    NexusEventBus.configure(tmp_path)
    seen = []
    NexusEventBus.subscribe("healing_artifact_announced", lambda payload: seen.append(payload))
    signed = sign_healing_artifact(
        HealingArtifact(
            task_id="task-1",
            artifact_id="heal-1",
            artifact_type="repair_plan",
            created_at="2026-05-05T00:00:00Z",
            evidence_id="EV-1",
            summary="Use scoped storage",
        ),
        key="secret",
        key_id="node-a",
    )
    packet = artifact_to_packet(signed)
    packet["payload"]["summary"] = "Run arbitrary repair"
    handler = RegistryMessageHandler(
        None,
        healing_artifact_policy=HealingArtifactKeyPolicy(
            allowed_key_ids=frozenset({"node-a"}),
            verification_keys={"node-a": "secret"},
        ),
    )

    resp = handler.handle(
        {"action": "event", "event_type": "healing_artifact_announced", "payload": {"packet": packet}},
        "node-a",
    )

    assert resp["status"] == "error"
    assert resp["receipt"]["passed"] is False
    assert "invalid_signature" in resp["receipt"]["failure_reasons"]
    assert seen == []
