from __future__ import annotations

import inspect
from typing import Any

import pytest

from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway


class _NoDispatchService:
    def __init__(self) -> None:
        self.submitted: list[dict[str, Any]] = []

    def submit_task(self, request: dict[str, Any]) -> dict[str, Any]:
        self.submitted.append(request)
        raise AssertionError("canonical MCP ingress must not dispatch before runtime convergence")


def _call_task_run(gateway: UnifiedMCPGateway, **overrides: Any) -> dict[str, Any]:
    arguments = {
        "task_id": "mcp-canonical-ingress",
        "what": "Inspect one bounded file",
        "why": "Verify canonical ingress identity",
        "allowed_files": ["README.md"],
        **overrides,
    }
    response = gateway.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "nexus_task_run", "arguments": arguments},
        }
    )
    assert response is not None
    return response["result"]


def test_task_run_schema_excludes_caller_route_override_fields() -> None:
    spec = next(item for item in UnifiedMCPGateway.tool_specs() if item["name"] == "nexus_task_run")
    schema = spec["inputSchema"]
    properties = schema["properties"]

    assert "execution_preference" not in properties
    assert "preferred_worker" not in properties
    assert "preferred_model" not in properties
    assert set(properties) == {"task_id", "what", "why", "allowed_files", "verifier_commands"}
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("execution_preference", "auto"),
        ("preferred_worker", "auto"),
        ("preferred_model", ""),
        ("execution_lane", "DIRECT_CANONICAL"),
        ("provider", "agy"),
        ("model", "example/model"),
        ("target_repo_root", "/tmp/forged-target"),
    ),
)
def test_task_run_rejects_caller_route_override_before_planning(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    from nexus.engine import canonical_execution

    planned = False

    def _unexpected_plan(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal planned
        planned = True
        raise AssertionError("planner must not run for a forged route override")

    monkeypatch.setattr(canonical_execution, "plan_canonical_task", _unexpected_plan)
    service = _NoDispatchService()
    result = _call_task_run(UnifiedMCPGateway(service=service), **{field: value})

    assert result["isError"] is True
    assert result["structuredContent"]["error"] == f"CALLER_ROUTE_OVERRIDE_FORBIDDEN:{field}"
    assert planned is False
    assert service.submitted == []


def test_task_run_returns_canonical_decision_without_physical_dispatch() -> None:
    service = _NoDispatchService()
    result = _call_task_run(UnifiedMCPGateway(service=service))

    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["schema"] == "nexus.mcp_canonical_decision.v1"
    assert payload["status"] == "CANONICAL_DECISION_READY"
    assert payload["execution_decision_authority"] == "CapabilityPlanner"
    assert payload["mutation_dispatched"] is False
    assert payload["context_hash"] == payload["execution_decision"]["context_hash"]
    assert payload["decision_hash"] == payload["canonical_execution_projection"]["decision_hash"]
    assert payload["projection_hash"]
    assert "execution_lane" not in payload
    assert "provider" not in payload
    assert "model" not in payload
    assert service.submitted == []


def test_mcp_and_direct_seam_produce_the_same_decision_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus.engine.canonical_execution import plan_canonical_task
    from nexus.orchestrator import canonical_mcp_ingress

    context = canonical_mcp_ingress.build_mcp_task_context(
        task_id="mcp-canonical-ingress",
        what="Inspect one bounded file",
        why="Verify canonical ingress identity",
        allowed_files=["README.md"],
    )
    direct_decision, direct_projection = plan_canonical_task(context)
    planner_calls = 0

    def _counted_plan(canonical_context):
        nonlocal planner_calls
        planner_calls += 1
        return plan_canonical_task(canonical_context)

    monkeypatch.setattr(canonical_mcp_ingress, "plan_canonical_task", _counted_plan)
    result = _call_task_run(UnifiedMCPGateway(service=_NoDispatchService()))
    payload = result["structuredContent"]

    assert result["isError"] is False
    assert planner_calls == 1
    assert payload["decision_hash"] == direct_decision.decision_hash
    assert payload["projection_hash"] == direct_projection.projection_hash


def test_gateway_task_run_contains_no_route_authority_writer() -> None:
    source = inspect.getsource(UnifiedMCPGateway._task_run)

    assert not hasattr(UnifiedMCPGateway, "_plan_route")
    for forbidden in (
        "execution_lane",
        "execution_preference",
        "preferred_worker",
        "preferred_model",
        "resolve_execution_lane",
    ):
        assert forbidden not in source


@pytest.mark.parametrize(
    "field",
    (
        "task_card_path",
        "task_card_hash",
        "owner_confirmation",
        "owner_inline_expires_at",
        "worker_may_commit",
        "idempotency_key",
        "apply",
        "controller_dirty_baseline_authorization",
        "dirty_overlap",
    ),
)
def test_task_run_rejects_noncanonical_execution_control_fields(field: str) -> None:
    result = _call_task_run(UnifiedMCPGateway(service=_NoDispatchService()), **{field: True})

    assert result["isError"] is True
    assert result["structuredContent"]["error"] == f"MCP_CANONICAL_INGRESS_FIELD_FORBIDDEN:{field}"


def test_task_run_decision_does_not_probe_dirty_worktree(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.orchestrator import worktree_manager

    def _unexpected_snapshot(*_args: Any, **_kwargs: Any) -> bytes:
        raise AssertionError("dirty worktree is a post-decision containment fact")

    monkeypatch.setattr(worktree_manager, "controller_status_bytes", _unexpected_snapshot)
    result = _call_task_run(UnifiedMCPGateway(service=_NoDispatchService()))

    assert result["isError"] is False
    assert result["structuredContent"]["status"] == "CANONICAL_DECISION_READY"


def test_mcp_reconnect_preserves_task_and_decision_identity() -> None:
    first = _call_task_run(UnifiedMCPGateway(service=_NoDispatchService()))["structuredContent"]
    second = _call_task_run(UnifiedMCPGateway(service=_NoDispatchService()))["structuredContent"]

    assert first["task_id"] == second["task_id"]
    assert first["context_hash"] == second["context_hash"]
    assert first["decision_hash"] == second["decision_hash"]
    assert first["projection_hash"] == second["projection_hash"]


def test_mcp_canonical_ingress_soak_never_dispatches_mutation() -> None:
    service = _NoDispatchService()
    gateway = UnifiedMCPGateway(service=service)

    for index in range(20):
        result = _call_task_run(gateway, task_id=f"mcp-canonical-soak-{index}")
        assert result["isError"] is False
        assert result["structuredContent"]["status"] == "CANONICAL_DECISION_READY"
        assert result["structuredContent"]["mutation_dispatched"] is False

    assert service.submitted == []
