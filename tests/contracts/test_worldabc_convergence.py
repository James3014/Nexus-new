"""RED acceptance contracts for the World A/B/C convergence seam.

These tests intentionally describe the public contract that is still absent on
the current canonical baseline.  They do not invoke providers, lifecycle
state, or a durable workspace.
"""

from __future__ import annotations

from dataclasses import fields

import pytest


WORLDS = (
    "product_runtime",
    "benchmark_instrument",
    "local_armor",
    "development_task",
)
TOPOLOGIES = ("DIRECT_CANONICAL", "ISOLATED_TARGET", "ASSISTED_CANONICAL")


def _context(**overrides):
    from nexus.contracts.canonical_execution import CanonicalTaskContext

    payload = {
        "task_id": "worldabc-red-1",
        "task_type": "bugfix",
        "task_desc": "repair one bounded file",
        "execution_world": "development_task",
        "transport_ingress": "mcp",
        "execution_channels": ("online", "local"),
        "task_facts": {"mutation_requested": True},
        "authority_inputs": {
            "direct_canonical_eligible": False,
            "isolation_required": True,
            "owner_authorized": False,
        },
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
        execution_topology=plan.execution_topology,
    )
    assert isinstance(decision, ExecutionDecision)
    assert decision.execution_world == context_world
    assert plan.execution_world == context_world
    assert plan.execution_topology in TOPOLOGIES
    assert decision.execution_topology in TOPOLOGIES
    assert route.execution_world == context_world
    assert route.execution_topology == decision.execution_topology


def test_depth_and_topology_are_orthogonal_planner_outputs() -> None:
    from nexus.engine.canonical_execution import plan_canonical_task_bundle

    light_direct = plan_canonical_task_bundle(
        _context(
            task_desc="simple bounded direct repair",
            route_features={"impact_complexity": 0.0},
            execution_channels=("online",),
            authority_inputs={
                "direct_canonical_eligible": True,
                "isolation_required": False,
                "owner_authorized": True,
            },
        )
    )
    light_isolated = plan_canonical_task_bundle(
        _context(
            task_desc="simple bounded isolated repair",
            route_features={"impact_complexity": 0.0},
            execution_channels=("online",),
            authority_inputs={
                "direct_canonical_eligible": False,
                "isolation_required": True,
                "owner_authorized": True,
            },
        )
    )
    assert light_direct.decision.execution_depth == light_isolated.decision.execution_depth
    assert light_direct.decision.execution_topology == "DIRECT_CANONICAL"
    assert light_isolated.decision.execution_topology == "ISOLATED_TARGET"
    assert light_direct.decision.execution_topology != "mcp"


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
