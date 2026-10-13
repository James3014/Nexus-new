from __future__ import annotations

from typing import Any

from nexus.services.mainchain_entry import run_mainchain
from nexus.services.unified_runtime import UnifiedRuntimeRequest


def _online(context: dict[str, Any]) -> dict[str, Any]:
    return {"task_id": context.get("task_id"), "invoked": False, "gate_passed": False}


def _ok(context: dict[str, Any]) -> dict[str, Any]:
    task_id = context["task_id"]
    return {
        "task_id": task_id,
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": [f"x:{task_id}"],
    }


def _high_risk_request() -> UnifiedRuntimeRequest:
    return UnifiedRuntimeRequest(
        task_id="forecast-gate-e2e-001",
        workspace_revision="rev-forecast-gate-e2e",
        task_statement="Refactor helper modules across packages",
        task_type="cross_module_refactor_swarm",
        route={
            "recommended_flow": "baseline",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
            "online_invoker_provider": "codex",
            "route_features": {
                "risk_score": 85,
                "candidate_count": 1,
                "is_cross_module_task": True,
            },
            "workforce_bindings": {
                "online": {
                    "worker_id": "codex_luna",
                    "controls": [
                        "task_card",
                        "allowed_files",
                        "mandatory_commands",
                        "independent_verification",
                        "governed_adapter",
                        "receipt",
                    ],
                }
            },
        },
        online_enabled=True,
        online_prompt="task",
        codeintel={
            "scan_report_present": True,
            "risk_score": 85,
            "impact_report_present": True,
            "workspace_root": "/tmp",
            "verify_commands": ["echo ok"],
            "verify_timeout_sec": 10,
        },
    )


def test_planner_selected_forecast_gate_runs_in_mainchain_and_keeps_trigger_source() -> None:
    receipt = run_mainchain(
        _high_risk_request(), online_invoker=_online, verifier=_ok, learning=_ok
    )

    assert "forecast_gate" in receipt["selected_capabilities"]
    stage = receipt["capability_results"]["forecast_gate"]
    assert stage["status"] == "SUCCEEDED"
    assert stage["skipped"] is False
    assert stage["response"]["trigger_source"] == "planner_mainchain_gate_policy"
