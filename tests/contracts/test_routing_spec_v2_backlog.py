from __future__ import annotations

from nexus.contracts.routing_spec_v2_backlog import (
    ROUTING_SPEC_V2_BACKLOG_GATE_SCHEMA,
    build_routing_spec_v2_backlog_gate,
)


def test_routing_spec_v2_backlog_gate_holds_forbidden_swarm_work_at_boundary() -> None:
    gate = build_routing_spec_v2_backlog_gate()

    assert gate["schema"] == ROUTING_SPEC_V2_BACKLOG_GATE_SCHEMA
    assert gate["status"] == "PASS"
    assert gate["production_boundary_ready"] is True
    assert gate["implementation_complete"] is False
    assert gate["runtime_update_allowed"] is False
    assert gate["public_benchmark_allowed"] is False
    sidecar = gate["items"][0]
    assert sidecar["id"] == "service_mesh_sidecar"
    assert sidecar["status"] == "FORBIDDEN_PATH_BOUNDARY"
    assert sidecar["forbidden_paths"]


def test_routing_spec_v2_backlog_gate_returns_for_forbidden_path_without_boundary() -> None:
    gate = build_routing_spec_v2_backlog_gate(
        [
            {
                "id": "bad_sidecar",
                "target_paths": ["nexus-swarm/webhook/mutating_webhook.go"],
                "status": "READY_FOR_ALLOWED_PATH_IMPLEMENTATION",
            }
        ]
    )

    assert gate["status"] == "RETURN"
    assert "bad_sidecar:forbidden_path_without_boundary" in gate["blockers"]


def test_routing_spec_v2_backlog_gate_returns_for_claim_boundary_crossing() -> None:
    gate = build_routing_spec_v2_backlog_gate(
        [
            {
                "id": "unsafe",
                "target_paths": ["nexus/engine/rlm_controller.py"],
                "runtime_update_allowed": True,
                "public_benchmark_allowed": True,
            }
        ]
    )

    assert gate["status"] == "RETURN"
    assert "unsafe:runtime_update_allowed" in gate["blockers"]
    assert "unsafe:public_benchmark_allowed" in gate["blockers"]
