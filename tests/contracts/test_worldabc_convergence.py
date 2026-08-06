"""RED acceptance contracts for the World A/B/C convergence seam.

These tests intentionally describe the public contract that is still absent on
the current canonical baseline.  They do not invoke providers, lifecycle
state, or a durable workspace.
"""

from __future__ import annotations

from dataclasses import fields

import pytest


WORLDS = ("development_task", "local_armor", "benchmark", "governance")
TOPOLOGIES = ("online", "local_only", "cloud_with_local_assist", "localheal_pipeline")


def _context(**overrides):
    from nexus.contracts.canonical_execution import CanonicalTaskContext

    payload = {
        "task_id": "worldabc-red-1",
        "task_type": "bugfix",
        "task_desc": "repair one bounded file",
        "execution_world": "development_task",
        "transport_ingress": "mcp",
        "execution_channels": ("online", "local"),
    }
    payload.update(overrides)
    return CanonicalTaskContext(**payload)


def test_canonical_context_declares_required_world_and_transport_contract() -> None:
    context = _context()
    assert context.execution_world in WORLDS
    assert context.transport_ingress == "mcp"
    assert "execution_world" in {item.name for item in fields(context)}
    assert "transport_ingress" in {item.name for item in fields(context)}


@pytest.mark.parametrize("bad_world", ("", "unknown", "mcp", "local_only"))
def test_canonical_context_rejects_unknown_execution_world(bad_world: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        _context(execution_world=bad_world)


@pytest.mark.parametrize("bad_ingress", ("", "provider", "route", "execution_lane"))
def test_canonical_context_rejects_non_transport_ingress(bad_ingress: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        _context(transport_ingress=bad_ingress)


def test_planner_decision_and_hybrid_route_bind_world_and_topology() -> None:
    from nexus.contracts.canonical_execution import ExecutionDecision
    from nexus.contracts.hybrid_route import HybridRouteDecision
    from nexus.engine.canonical_execution import plan_canonical_task_bundle

    bundle = plan_canonical_task_bundle(_context())
    plan = bundle.plan
    decision = bundle.decision
    context_world = _context().execution_world
    route = HybridRouteDecision(
        execution_world=context_world,
        execution_topology=plan.signal_snapshot["execution_topology"],
    )
    assert isinstance(decision, ExecutionDecision)
    assert decision.execution_world == context_world
    assert decision.execution_topology in TOPOLOGIES
    assert route.execution_world == context_world
    assert route.execution_topology == decision.execution_topology


def test_depth_and_topology_are_orthogonal_planner_outputs() -> None:
    from nexus.engine.canonical_execution import plan_canonical_task_bundle

    light_online = plan_canonical_task_bundle(
        _context(
            task_desc="simple bounded online repair",
            route_features={"impact_complexity": 0.0},
            execution_channels=("online",),
        )
    )
    light_local = plan_canonical_task_bundle(
        _context(
            task_desc="simple bounded local armor repair",
            route_features={"impact_complexity": 0.0, "deterministic_verifier_available": True},
            execution_channels=("local",),
        )
    )
    assert light_online.decision.execution_depth == light_local.decision.execution_depth
    assert light_online.decision.execution_topology != light_local.decision.execution_topology
    assert light_online.decision.execution_topology != "mcp"


def test_world_identity_survives_context_roundtrip_and_identity_projection() -> None:
    from nexus.contracts.canonical_execution import CanonicalTaskContext
    from nexus.engine.canonical_execution import plan_canonical_task_bundle
    from nexus.services.unified_runtime import canonical_execution_identity

    context = _context(execution_world="local_armor", transport_ingress="direct")
    restored = CanonicalTaskContext.from_dict(context.to_dict())
    identity = canonical_execution_identity(plan_canonical_task_bundle(restored))
    assert restored.execution_world == "local_armor"
    assert restored.transport_ingress == "direct"
    assert identity["execution_world"] == "local_armor"
