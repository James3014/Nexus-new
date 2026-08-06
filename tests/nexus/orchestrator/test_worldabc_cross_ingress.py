"""RED cross-ingress and receipt-lineage acceptance tests."""

from __future__ import annotations

from typing import Any

import pytest


def _task() -> dict[str, Any]:
    return {
        "task_id": "worldabc-ingress-red-1",
        "what": "repair one bounded file",
        "why": "cross-ingress planner parity",
        "allowed_files": ["README.md"],
        "verifier_commands": ["python -m py_compile README.md"],
    }


def test_mcp_cli_direct_normalizers_produce_equivalent_canonical_context() -> None:
    from nexus.orchestrator import canonical_mcp_ingress

    mcp = canonical_mcp_ingress.build_mcp_execution_context(
        task_id=_task()["task_id"],
        workspace_revision="rev-worldabc-red",
        allowed_files=_task()["allowed_files"],
        verifier_commands=_task()["verifier_commands"],
    )
    cli = canonical_mcp_ingress.build_cli_execution_context(**_task(), workspace_revision="rev-worldabc-red")
    direct = canonical_mcp_ingress.build_direct_execution_context(**_task(), workspace_revision="rev-worldabc-red")
    assert mcp["execution_world"] == cli["execution_world"] == direct["execution_world"] == "development_task"
    assert mcp["transport_ingress"] == "mcp"
    assert cli["transport_ingress"] == "cli"
    assert direct["transport_ingress"] == "direct"
    assert mcp["canonical_context_hash"] == cli["canonical_context_hash"] == direct["canonical_context_hash"]


@pytest.mark.parametrize("field", ("execution_world", "execution_topology", "provider", "model", "execution_lane"))
def test_mcp_caller_cannot_override_world_or_route(field: str) -> None:
    from nexus.orchestrator.canonical_mcp_ingress import reject_caller_route_overrides

    with pytest.raises(ValueError):
        reject_caller_route_overrides({**_task(), field: "local_armor"})


def test_four_worlds_preserve_world_identity_through_shared_planner() -> None:
    from nexus.contracts.canonical_execution import CanonicalTaskContext
    from nexus.engine.canonical_execution import plan_canonical_task_bundle

    decisions = {}
    for world in ("development_task", "local_armor", "benchmark", "governance"):
        context = CanonicalTaskContext(
            task_id=f"world-{world}",
            task_type="bugfix",
            task_desc="bounded world preservation probe",
            execution_world=world,
            transport_ingress="direct",
        )
        bundle = plan_canonical_task_bundle(context)
        decisions[world] = bundle.decision
        assert bundle.decision.execution_world == world
        assert bundle.projection.execution_world == world
    assert set(decisions) == {"development_task", "local_armor", "benchmark", "governance"}


def test_unified_runtime_receipt_binds_local_armor_lineage_to_canonical_identity(tmp_path) -> None:
    from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest

    request = UnifiedRuntimeRequest(
        task_id="worldabc-local-armor-red",
        workspace_revision="rev-worldabc-red",
        task_statement="bounded local armor probe",
        task_type="bugfix",
        route={"workspace_root": str(tmp_path)},
        online_enabled=False,
        local_enabled=True,
        canonical_context={
            "execution_world": "local_armor",
            "transport_ingress": "direct",
        },
    )
    receipt = UnifiedRuntime().run(request, local_executor=lambda _req: {"status": "SUCCEEDED"})
    assert receipt["canonical_execution"]["execution_world"] == "local_armor"
    assert receipt["local"]["response"]["world_c_receipt"]["canonical_execution_hash"] == receipt["canonical_execution"]["context_hash"]

