from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway


class _NoDispatchService:
    def __init__(self) -> None:
        self.submitted: list[dict[str, Any]] = []

    def submit_task(self, request: dict[str, Any]) -> dict[str, Any]:
        self.submitted.append(request)
        raise AssertionError("canonical MCP ingress must not enter lifecycle dispatch")


class _RuntimeResult(SimpleNamespace):
    def __bool__(self) -> bool:
        return bool(self.ok)


@pytest.fixture(autouse=True)
def _canonical_runtime(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _execute(task_text, project_root, execution_context=None):
        calls.append(
            {
                "task_text": task_text,
                "project_root": project_root,
                "execution_context": dict(execution_context or {}),
            }
        )
        task_id = str((execution_context or {}).get("task_id") or "mcp-runtime")
        return _RuntimeResult(
            ok=True,
            receipt={
                "task_id": task_id,
                "canonical_execution": {
                    "execution_decision_authority": "CapabilityPlanner",
                    "execution_world": "development_task",
                    "canonical_execution_topology": "ASSISTED_CANONICAL",
                    "context_hash": "context-hash",
                    "decision_hash": "decision-hash",
                    "projection_hash": "projection-hash",
                },
            },
            receipt_path="/tmp/mcp-canonical-runtime.json",
            root_receipt={
                "schema": "nexus.root_receipt.v1",
                "root_receipt_hash": "sha256:" + "a" * 64,
            },
            root_receipt_valid=True,
            root_receipt_blockers=(),
            execution_decision_authority="CapabilityPlanner",
            production_ingress_count=1,
            production_runtime_entry_count=1,
        )

    monkeypatch.setattr(
        "nexus.orchestrator.unified_mcp_gateway.execute_canonical_product_task",
        _execute,
    )
    return calls


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

    assert set(properties) == {"task_id", "what", "why", "allowed_files", "verifier_commands"}
    assert schema["additionalProperties"] is False
    assert properties["verifier_commands"]["maxItems"] == 1
    for field in (
        "execution_preference",
        "preferred_worker",
        "preferred_model",
        "execution_lane",
        "provider",
        "model",
    ):
        assert field not in properties


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
def test_task_run_rejects_caller_route_override_before_runtime(
    _canonical_runtime: list[dict[str, Any]],
    field: str,
    value: str,
) -> None:
    service = _NoDispatchService()
    result = _call_task_run(UnifiedMCPGateway(service=service), **{field: value})

    assert result["isError"] is True
    assert result["structuredContent"]["error"] == f"CALLER_ROUTE_OVERRIDE_FORBIDDEN:{field}"
    assert _canonical_runtime == []
    assert service.submitted == []


def test_task_run_enters_canonical_product_runtime_once(
    _canonical_runtime: list[dict[str, Any]],
) -> None:
    service = _NoDispatchService()
    result = _call_task_run(UnifiedMCPGateway(service=service))

    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["schema"] == "nexus.mcp_canonical_runtime.v1"
    assert payload["status"] == "SUCCEEDED"
    assert payload["execution_decision_authority"] == "CapabilityPlanner"
    assert payload["execution_world"] == "development_task"
    assert payload["canonical_execution_topology"] == "ASSISTED_CANONICAL"
    assert payload["runtime_dispatched"] is True
    assert payload["formal_workspace_mutated"] is False
    assert payload["root_receipt_valid"] is True
    assert payload["production_ingress_count"] == 1
    assert payload["production_runtime_entry_count"] == 1
    assert len(_canonical_runtime) == 1
    call = _canonical_runtime[0]
    assert call["execution_context"]["local_assist_mode"] == "advisor"
    assert call["execution_context"]["execution_world"] == "development_task"
    assert call["execution_context"]["transport_ingress"] == "mcp"
    assert call["execution_context"]["canonical_semantic_hash"].startswith("sha256:")
    assert call["execution_context"]["target_files"] == ["README.md"]
    assert "online_policy" not in call["execution_context"]
    assert service.submitted == []


def test_task_run_threads_one_verifier_to_world_c(
    _canonical_runtime: list[dict[str, Any]],
) -> None:
    result = _call_task_run(
        UnifiedMCPGateway(service=_NoDispatchService()),
        verifier_commands=["python -m py_compile README.md"],
    )

    assert result["isError"] is False
    assert _canonical_runtime[0]["execution_context"]["verifier_command"] == (
        "python -m py_compile README.md"
    )


def test_task_run_rejects_parallel_verifier_authority(
    _canonical_runtime: list[dict[str, Any]],
) -> None:
    result = _call_task_run(
        UnifiedMCPGateway(service=_NoDispatchService()),
        verifier_commands=["pytest -q", "git diff --check"],
    )

    assert result["isError"] is True
    assert "supports exactly one isolated command" in result["structuredContent"]["error"]
    assert _canonical_runtime == []


def test_gateway_task_run_contains_no_second_planner_or_lifecycle_writer() -> None:
    source = inspect.getsource(UnifiedMCPGateway._task_run)

    assert source.count("execute_canonical_product_task(") == 1
    assert "plan_mcp_task" not in source
    assert "plan_canonical_task" not in source
    assert "submit_task" not in source
    assert "execution_lane" not in source


@pytest.mark.parametrize(
    "field",
    (
        "task_card_path",
        "task_card_hash",
        "owner_confirmation",
        "worker_may_commit",
        "idempotency_key",
        "apply",
        "dirty_overlap",
    ),
)
def test_task_run_rejects_noncanonical_execution_control_fields(field: str) -> None:
    result = _call_task_run(UnifiedMCPGateway(service=_NoDispatchService()), **{field: True})

    assert result["isError"] is True
    assert result["structuredContent"]["error"] == f"MCP_CANONICAL_INGRESS_FIELD_FORBIDDEN:{field}"


def test_mcp_canonical_ingress_soak_uses_one_runtime_per_request(
    _canonical_runtime: list[dict[str, Any]],
) -> None:
    service = _NoDispatchService()
    gateway = UnifiedMCPGateway(service=service)

    for index in range(20):
        result = _call_task_run(gateway, task_id=f"mcp-canonical-soak-{index}")
        assert result["isError"] is False
        assert result["structuredContent"]["runtime_dispatched"] is True
        assert result["structuredContent"]["formal_workspace_mutated"] is False

    assert len(_canonical_runtime) == 20
    assert service.submitted == []
