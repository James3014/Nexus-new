#!/usr/bin/env python3
"""Local acceptance matrix for the canonical MCP task ingress.

This is deliberately non-mutating: it exercises the exact public schema and
the fail-closed route-override guard against a deterministic runtime double.
It does not claim a live connector or provider execution.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Mapping

import nexus.orchestrator.unified_mcp_gateway as gateway_module
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway


def _content(response: Mapping[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("structuredContent"), dict):
        raise AssertionError(f"missing structuredContent: {response}")
    if result.get("isError"):
        raise AssertionError(f"unexpected gateway error: {result['structuredContent']}")
    return dict(result["structuredContent"])


def _call(gateway: UnifiedMCPGateway, name: str, arguments: Mapping[str, Any], request_id: int) -> dict[str, Any]:
    return _content(gateway.handle({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": dict(arguments)}}))


def run_acceptance() -> dict[str, Any]:
    original_runtime = gateway_module.execute_canonical_product_task
    calls: list[dict[str, Any]] = []

    def fake_runtime(task_text: str, project_root: Any, *, execution_context: Mapping[str, Any]) -> Any:
        del task_text, project_root
        calls.append(dict(execution_context))
        task_id = str(execution_context["task_id"])
        return SimpleNamespace(
            ok=True,
            receipt={"task_id": task_id, "canonical_execution": {"execution_decision_authority": "CapabilityPlanner", "execution_world": "development_task", "canonical_execution_topology": "ASSISTED_CANONICAL"}},
            root_receipt={"schema": "nexus.root_receipt.v1", "root_receipt_hash": "sha256:" + "a" * 64},
            root_receipt_valid=True,
            root_receipt_blockers=(),
            receipt_path="/tmp/nexus-mcp-acceptance-receipt.json",
            execution_decision_authority="CapabilityPlanner",
            production_ingress_count=1,
            production_runtime_entry_count=1,
        )

    gateway_module.execute_canonical_product_task = fake_runtime
    try:
        gateway = UnifiedMCPGateway(service=object())
        schema = next(spec["inputSchema"] for spec in gateway.tool_specs() if spec["name"] == "nexus_task_run")
        expected_keys = {"task_id", "what", "why", "allowed_files", "verifier_commands"}
        expected_required = {"what", "why", "allowed_files"}
        accepted_fields = set(schema["properties"])
        required_fields = set(schema.get("required", []))
        if accepted_fields != expected_keys or required_fields != expected_required or schema.get("additionalProperties") is not False:
            raise AssertionError(f"nexus_task_run schema broadened: {schema}")

        request_id = 1
        for index in range(10):
            payload = _call(gateway, "nexus_task_run", {"task_id": f"schema-acceptance-{index}", "what": "bounded schema acceptance", "why": "canonical ingress", "allowed_files": ["README.md"], "verifier_commands": ["git diff --check"]}, request_id)
            if payload["execution_world"] != "development_task" or payload["execution_decision_authority"] != "CapabilityPlanner":
                raise AssertionError(f"canonical runtime identity mismatch: {payload}")
            request_id += 1

        negatives = 0
        for field, value in (("execution_lane", "DIRECT_CANONICAL"), ("preferred_worker", "agy"), ("idempotency_key", "forbidden"), ("task_card_path", "tasks/x.md")):
            response = gateway.handle({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": {"what": "bad", "why": "override", "allowed_files": ["README.md"], field: value}}})
            result = response.get("result", {})
            if result.get("isError") and str(result.get("structuredContent", {}).get("error", "")).endswith(field):
                negatives += 1
            else:
                raise AssertionError(f"route override accepted: {field}: {response}")
            request_id += 1
    finally:
        gateway_module.execute_canonical_product_task = original_runtime

    receipt = {
        "schema": "nexus.mcp_gateway.acceptance.v1",
        "scope": "LOCAL_CANONICAL_SCHEMA_ACCEPTANCE",
        "matrix": {"canonical_task_run": len(calls), "negative_route_overrides": negatives},
        "accepted_fields": sorted(accepted_fields),
        "required_fields": sorted(required_fields),
        "invariants": {"production_schema_unchanged": accepted_fields == {"task_id", "what", "why", "allowed_files", "verifier_commands"} and required_fields == {"what", "why", "allowed_files"}, "route_overrides_rejected": negatives == 4, "formal_workspace_mutated": False},
        "live_connector_smoke": "NOT_RUN",
    }
    receipt["gate_passed"] = bool(receipt["invariants"]["route_overrides_rejected"])
    if not receipt["gate_passed"]:
        raise AssertionError(json.dumps(receipt, sort_keys=True))
    return receipt


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), indent=2, sort_keys=True))
