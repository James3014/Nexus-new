from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import sys

from nexus.services.local_assist_advisor_canary import run_advisor_canary
from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProvider,
    LocalModelProviderResponse,
)


def _request(tmp_path: Path) -> LocalAssistRequest:
    return LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id="m3-d-001",
        parent_task_id="agent-task-001",
        workspace_root=str(tmp_path),
        workspace_revision="rev-1",
        task_statement="Inspect the target and report the safest bounded next action.",
        action="advisor",
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("tests/services/test_local_assist_advisor_canary.py",),
        verifier_command=(sys.executable, "-c", "print('verified')"),
        risk_budget="low",
        time_budget=10.0,
        requested_role="advisor",
        mutation_policy="isolated_only",
        planner_snapshot={
            "route_truth_source": "CapabilityPlanner",
            "execution_topology": "single_local_model",
            "protocol_mode": "unified_diff",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b",
        },
    )


def _recommendation(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": "nexus.local_assist.recommendation.v1",
        "recommended": True,
        "action": "advisor",
        "reason_codes": ["risk_low"],
        "task_risk": "low",
        "confidence": 0.9,
        "mutation_allowed": False,
        "verifier_required": False,
        "candidate_budget": 0,
        "time_budget_sec": 120,
        "shadow_only": True,
        "route_truth_source": "CapabilityPlanner",
    }
    result.update(overrides)
    return result


def test_advisor_canary_invokes_only_read_only_advisor(tmp_path: Path) -> None:
    response = run_advisor_canary(
        request=_request(tmp_path),
        recommendation=_recommendation(),
        calibration={"status": "CALIBRATED"},
        service=LocalAssistService(
            provider=InjectedLocalModelProvider(lambda _: "diagnosis: target is safe to inspect")
        ),
    )
    assert response["status"] == "SUCCEEDED"
    assert response["automatic_advisor_executed"] is True
    assert response["local_assist_invoked"] is True
    assert response["candidate_generation"] is False
    assert response["formal_workspace_mutated"] is False
    assert response["agent_controller"] is True
    assert response["claim_boundary"]["outcome_contributed"] is False


def test_unavailable_provider_fails_closed_without_invocation(tmp_path: Path) -> None:
    called: list[bool] = []
    service = LocalAssistService(provider=InjectedLocalModelProvider(lambda _: called.append(True) or "unused"))
    response = run_advisor_canary(
        request=_request(tmp_path),
        recommendation=_recommendation(),
        calibration={"status": "CALIBRATED"},
        provider_available=False,
        service=service,
    )
    assert response["status"] == "BLOCKED"
    assert response["failure_reason"] == "provider_unavailable"
    assert response["local_assist_invoked"] is False
    assert called == []


def test_uncalibrated_or_high_risk_recommendation_is_blocked(tmp_path: Path) -> None:
    for recommendation, calibration, reason in (
        (_recommendation(), {"status": "BLOCKED"}, "shadow_calibration_not_passed"),
        (_recommendation(task_risk="high"), {"status": "CALIBRATED"}, "risk_above_canary_limit"),
        (_recommendation(mutation_allowed=True), {"status": "CALIBRATED"}, "mutation_not_allowed"),
        ({}, {"status": "CALIBRATED"}, "recommendation_absent"),
    ):
        response = run_advisor_canary(
            request=_request(tmp_path),
            recommendation=recommendation,
            calibration=calibration,
            service=LocalAssistService(provider=InjectedLocalModelProvider(lambda _: "unused")),
        )
        assert response["status"] == "BLOCKED"
        assert response["failure_reason"] == reason
        assert response["local_assist_invoked"] is False


def test_stale_revision_and_invalid_budget_are_blocked(tmp_path: Path) -> None:
    request = _request(tmp_path)
    stale = run_advisor_canary(
        request=request,
        recommendation=_recommendation(),
        calibration={"status": "CALIBRATED"},
        current_workspace_revision="rev-2",
    )
    invalid_budget = run_advisor_canary(
        request=replace(request, time_budget=0),
        recommendation=_recommendation(time_budget_sec=0),
        calibration={"status": "CALIBRATED"},
    )
    assert stale["failure_reason"] == "workspace_revision_stale"
    assert invalid_budget["failure_reason"] == "invalid_time_budget"


def test_formal_mutation_is_blocked(tmp_path: Path) -> None:
    response = run_advisor_canary(
        request=_request(tmp_path),
        recommendation=_recommendation(),
        calibration={"status": "CALIBRATED"},
        formal_workspace_mutation_possible=True,
    )
    assert response["failure_reason"] == "formal_workspace_mutation_possible"
    assert response["local_assist_invoked"] is False


def test_malformed_advisor_output_fails_closed(tmp_path: Path) -> None:
    response = run_advisor_canary(
        request=_request(tmp_path),
        recommendation=_recommendation(),
        calibration={"status": "CALIBRATED"},
        service=LocalAssistService(provider=InjectedLocalModelProvider(lambda _: "")),
    )
    assert response["status"] == "FAILED"
    assert response["failure_reason"] in {"advisor_output_not_delivered", "incomplete_receipt"}
    assert response["claim_boundary"]["value_measured"] is False


def test_timeout_fails_closed(tmp_path: Path) -> None:
    class TimeoutProvider(LocalModelProvider):
        def generate(self, request):
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=request.model_name,
                output_text="",
                error="provider_timeout",
                timed_out=True,
            )

    response = run_advisor_canary(
        request=_request(tmp_path),
        recommendation=_recommendation(),
        calibration={"status": "CALIBRATED"},
        service=LocalAssistService(provider=TimeoutProvider()),
    )
    assert response["status"] == "FAILED"
    assert response["failure_reason"] == "incomplete_receipt"


def test_mismatched_task_identity_fails_closed(tmp_path: Path) -> None:
    receipt_path = tmp_path / "mismatched-receipt.json"
    receipt_path.write_text('{"receipt_complete": true}', encoding="utf-8")
    fake_response = SimpleNamespace(
        task_id="wrong-task",
        status="SUCCEEDED",
        local_model_invoked=True,
        output_delivered=True,
        receipt_path=str(receipt_path),
        to_dict=lambda: {"task_id": "wrong-task"},
    )

    class FakeService:
        def handle(self, _request):
            return fake_response

    response = run_advisor_canary(
        request=_request(tmp_path),
        recommendation=_recommendation(),
        calibration={"status": "CALIBRATED"},
        service=FakeService(),  # type: ignore[arg-type]
    )
    assert response["status"] == "FAILED"
    assert response["failure_reason"] == "task_identity_mismatch"
