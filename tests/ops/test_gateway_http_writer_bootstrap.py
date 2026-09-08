"""HTTP entrypoint tests for the Card C source-owned writer bootstrap."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from nexus.events.state_owner_manifest import read_manifest
from nexus.events.writer_generation import EventWriterGeneration, install_generation
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.state_owner_transition_authority import LoadedSourceIdentity
from nexus.orchestrator.unified_mcp_gateway import LoadedTaskWriterBinding, UnifiedMCPGateway
from scripts.ops import nexus_mcp_gateway_http as http_entrypoint


def test_server_construction_disables_reconciliation_before_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class CountingService(SelfHostedTaskService):
        def __init__(self, *args: object, **kwargs: object) -> None:
            events.append("service")
            super().__init__(*args, **kwargs)

        def reconcile_tasks(self) -> object:
            events.append("reconcile")
            return super().reconcile_tasks()

    monkeypatch.setattr(http_entrypoint, "SelfHostedTaskService", CountingService)
    monkeypatch.setattr(
        http_entrypoint.UnifiedMCPGateway,
        "bootstrap_writer_admission",
        lambda self: events.append("bootstrap"),
        raising=False,
    )

    service_root = tmp_path / "tasks"
    CountingService(state_dir=service_root, ephemeral=True, auto_reconcile=False)
    assert service_root.exists() is False
    events.clear()
    # The production helper creates the actual service and Gateway.  This
    # factory substitution only gives it an isolated fixture root.
    monkeypatch.setattr(
        http_entrypoint,
        "SelfHostedTaskService",
        lambda **kwargs: CountingService(state_dir=service_root, ephemeral=True, **kwargs),
    )
    server = http_entrypoint.build_server(host="127.0.0.1", port=0, token="test-token")
    try:
        assert events[0] == "service"
        assert "bootstrap" in events[1:]
        assert "reconcile" not in events
        assert service_root.exists() is False
    finally:
        server.server_close()


def test_held_root_http_write_is_denied_before_state_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "tasks"
    service = SelfHostedTaskService(state_dir=root, ephemeral=True, auto_reconcile=False)
    service.loaded_source_identity = LoadedSourceIdentity(
        "James3014/Nexus-new", "a" * 40, "b" * 40, "card.md", "c" * 64
    )
    service.writer_generation = 1
    service.writer_id = "writer-old"
    seed = {
        "task_id": "held-task",
        "status": "PENDING",
        "attempt_id": "attempt",
        "worker_pid": None,
    }
    service._create_state("held-task", seed)
    initial = (root / "held-task.json").read_bytes()
    seed_gateway = UnifiedMCPGateway(service=service)
    registry = seed_gateway._writer_quiescence_registry
    assert registry is not None
    hold = registry.begin_hold([root], cohort_id="held-cohort")
    hold.acknowledge("writer-old", root=root, role="task_state", generation=1)
    hold.finalize()

    monkeypatch.setattr(http_entrypoint, "SelfHostedTaskService", lambda **_: service)
    server = http_entrypoint.build_server(host="127.0.0.1", port=0, token="test-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            data=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "nexus_task_cancel", "arguments": {"task_id": "held-task"}},
            }).encode(),
            method="POST",
            headers={"Authorization": "Bearer test-token"},
        )
        response = json.loads(urllib.request.urlopen(request, timeout=3).read())
        assert response["result"]["isError"] is True
        assert (root / "held-task.json").read_bytes() == initial
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_activated_root_without_loaded_binding_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "tasks"
    install_generation(root, EventWriterGeneration(1, "writer-activated"))
    service = SelfHostedTaskService(state_dir=root, ephemeral=True, auto_reconcile=False)
    monkeypatch.setattr(http_entrypoint, "SelfHostedTaskService", lambda **_: service)
    with pytest.raises(RuntimeError, match="ACTIVATED_TASK_WRITER"):
        http_entrypoint.build_server(host="127.0.0.1", port=0, token="test-token")


def test_fresh_activated_http_write_uses_registered_generation_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.nexus.orchestrator.test_loaded_task_state_writer import _activated_service

    root = tmp_path / "state"
    service, _fixture_registry = _activated_service(root)
    service.loaded_source_identity = LoadedSourceIdentity(
        "James3014/Nexus-new", "a" * 40, "b" * 40, "card.md", "c" * 64
    )
    service.writer_generation = 1
    service.writer_id = "task-writer"
    service._write_state("http-task", {"task_id": "http-task", "status": "SUBMITTED"})
    manifest = read_manifest(root)
    assert manifest is not None
    service.loaded_task_writer_binding = LoadedTaskWriterBinding(
        root=root.resolve(),
        owner_id=manifest.owner_id,
        transaction_id=manifest.transaction_id,
        generation=1,
        writer_id="task-writer",
        source_head="a" * 40,
        source_tree="b" * 40,
    )
    write_witness: list[tuple[str, str, int]] = []
    server_holder: dict[str, object] = {}
    original_locked_write = service._write_state_locked

    def witnessed_locked_write(task_id: str, state: dict[str, object], *, owner_context=None):
        server = server_holder.get("server")
        registry = getattr(server.gateway, "_writer_quiescence_registry", None) if server else None
        if registry is not None:
            active = [
                lease.observation
                for lease in registry._leases.values()
                if lease.observation.identity.root == str(root.resolve())
                and lease.observation.identity.generation == 1
                and lease.observation.identity.thread_id == str(threading.get_ident())
            ]
            assert active, "HTTP state write must hold its exact operation lease first"
            write_witness.append((task_id, active[-1].operation_id, active[-1].identity.generation))
        return original_locked_write(task_id, state, owner_context=owner_context)

    service._write_state_locked = witnessed_locked_write
    monkeypatch.setattr(http_entrypoint, "SelfHostedTaskService", lambda **_: service)
    server = http_entrypoint.build_server(host="127.0.0.1", port=0, token="test-token")
    server_holder["server"] = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            data=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "nexus_task_cancel", "arguments": {"task_id": "http-task"}},
            }).encode(),
            method="POST",
            headers={"Authorization": "Bearer test-token"},
        )
        response = json.loads(urllib.request.urlopen(request, timeout=3).read())
        assert response["result"]["isError"] is False
        assert write_witness and write_witness[0][0] == "http-task"
        registry = server.gateway._writer_quiescence_registry
        assert registry is not None
        operation_id = write_witness[0][1]
        lease = next(item for item in registry._lease_history if item.operation_id == operation_id)
        assert lease.durable_outcome == "committed"
        assert lease.identity.root == str(root.resolve())
        assert lease.identity.generation == 1
        assert lease.identity.thread_id
        assert json.loads((root / "http-task.json").read_text())["status"] == "CANCELLED"
        assert read_manifest(root).state == "COMMITTED"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
