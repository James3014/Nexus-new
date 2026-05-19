from __future__ import annotations

from nexus.contracts.route_runtime_plan import build_route_runtime_plan_from_pregate
from nexus.engine.route_runtime_dispatcher import RouteRuntimeDispatcher


def test_route_runtime_dispatcher_prepares_without_dispatch_or_claim() -> None:
    plan = build_route_runtime_plan_from_pregate(
        {
            "schema": "nexus.route_dag_pregate.v1",
            "status": "PASS",
            "runtime_dispatch_changed": False,
            "claim_verdict": "NOT_EVALUATED",
            "nodes": [
                {
                    "capability": "codeintel",
                    "state": "selected",
                    "execution_slot": "standard",
                    "required_receipts": ["code_scan"],
                }
            ],
        }
    )

    payload = RouteRuntimeDispatcher().prepare(plan)

    assert payload["schema"] == "nexus.route_runtime_dispatch_preparation.v1"
    assert payload["status"] == "PASS"
    assert payload["plan_consumed"] is True
    assert payload["plan_schema"] == "nexus.route_runtime_plan.v1"
    assert payload["dispatch_ready"] is True
    assert payload["dispatch_executed"] is False
    assert payload["runtime_dispatch_changed"] is False
    assert payload["claim_verdict"] == "NOT_EVALUATED"
    assert payload["runtime_update_allowed"] is False
    assert payload["public_benchmark_allowed"] is False


def test_route_runtime_dispatcher_requires_runtime_plan_schema() -> None:
    payload = RouteRuntimeDispatcher().prepare(
        {
            "schema": "nexus.route_dag_pregate.v1",
            "status": "PASS",
            "runtime_dispatch_changed": False,
            "claim_verdict": "NOT_EVALUATED",
        }
    )

    assert payload["status"] == "RETURN"
    assert payload["dispatch_ready"] is False
    assert "invalid_or_missing_route_runtime_plan_schema" in payload["blockers"]


def test_route_runtime_dispatcher_returns_when_plan_crosses_claim_boundary() -> None:
    payload = RouteRuntimeDispatcher().prepare(
        {
            "schema": "nexus.route_runtime_plan.v1",
            "status": "PASS",
            "runtime_dispatch_changed": True,
            "claim_verdict": "PASS",
            "runtime_update_allowed": True,
            "public_benchmark_allowed": True,
        }
    )

    assert payload["status"] == "RETURN"
    assert payload["dispatch_ready"] is False
    assert payload["dispatch_executed"] is False
    assert "runtime_dispatch_changed" in payload["blockers"]
    assert "claim_verdict_evaluated_in_runtime_plan" in payload["blockers"]
    assert "runtime_update_allowed_in_runtime_plan" in payload["blockers"]
    assert "public_benchmark_allowed_in_runtime_plan" in payload["blockers"]


def test_route_runtime_dispatcher_consumes_hard_gate_without_unlocking_claims() -> None:
    plan = build_route_runtime_plan_from_pregate(
        {
            "schema": "nexus.route_dag_pregate.v1",
            "status": "PASS",
            "runtime_dispatch_changed": False,
            "claim_verdict": "NOT_EVALUATED",
            "nodes": [],
        }
    )

    payload = RouteRuntimeDispatcher().prepare(
        plan,
        hard_gate={
            "status": "RETURN",
            "blockers": ["completion_envelope_not_pass"],
            "runtime_update_allowed": True,
            "public_benchmark_allowed": True,
        },
    )

    assert payload["status"] == "RETURN"
    assert payload["dispatch_ready"] is False
    assert payload["hard_gate_status"] == "RETURN"
    assert "hard_gate_compatibility_not_pass" in payload["blockers"]
    assert "completion_envelope_not_pass" in payload["blockers"]
    assert "hard_gate_runtime_update_allowed" in payload["blockers"]
    assert "hard_gate_public_benchmark_allowed" in payload["blockers"]
    assert payload["claim_verdict"] == "NOT_EVALUATED"
