from __future__ import annotations

from pathlib import Path
import sys

from nexus.services.local_assist_bounded_dispatch import dispatch_local_assist
from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


def _request(tmp_path: Path, action: str) -> LocalAssistRequest:
    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    return LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id="m3-g-001",
        parent_task_id="agent-task-001",
        workspace_root=str(tmp_path),
        workspace_revision="rev-1",
        task_statement="Implement a bounded change and verify it.",
        action=action,
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("tests/services/test_local_assist_bounded_dispatch.py",),
        verifier_command=(sys.executable, "-c", "print('verified')"),
        risk_budget="medium",
        time_budget=10.0,
        requested_role="advisor" if action == "advisor" else "candidate",
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


def _recommendation(action: str) -> dict[str, object]:
    return {
        "schema": "nexus.local_assist.recommendation.v1",
        "recommended": True,
        "action": action,
        "reason_codes": ["bounded_test"],
        "task_risk": "low" if action != "verified-subtask" else "medium",
        "confidence": 0.9,
        "mutation_allowed": False,
        "verifier_required": action == "verified-subtask",
        "candidate_budget": 1 if action in {"candidate", "verified-subtask"} else 0,
        "time_budget_sec": 180 if action != "skip" else 0,
        "shadow_only": True,
        "route_truth_source": "CapabilityPlanner",
    }


def _receipt(request: LocalAssistRequest, recommendation: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "nexus.local_assist.recommendation_receipt.v1",
        "task_id": request.task_id,
        "workspace_revision": request.workspace_revision,
        "planner_recommendation": recommendation,
    }


def _service() -> LocalAssistService:
    return LocalAssistService(
        provider=InjectedLocalModelProvider(
            lambda _: "--- a/target.py\n+++ b/target.py\n@@ -1,2 +1,2 @@\n def target():\n-    return 1\n+    return 2\n"
        )
    )


def test_skip_dispatches_nothing_but_records_lineage(tmp_path: Path) -> None:
    request = _request(tmp_path, "advisor")
    recommendation = _recommendation("skip")
    result = dispatch_local_assist(
        request=request,
        recommendation=recommendation,
        recommendation_receipt=_receipt(request, recommendation),
        calibration={"status": "CALIBRATED"},
        service=_service(),
    )
    assert result["status"] == "SKIPPED"
    assert result["automatic_dispatch"] is False
    assert result["local_assist_invoked"] is False
    assert result["task_id"] == request.task_id
    assert result["workspace_revision"] == request.workspace_revision


def test_advisor_dispatch_is_bounded_and_agent_remains_controller(tmp_path: Path) -> None:
    request = _request(tmp_path, "advisor")
    recommendation = _recommendation("advisor")
    result = dispatch_local_assist(
        request=request,
        recommendation=recommendation,
        recommendation_receipt=_receipt(request, recommendation),
        calibration={"status": "CALIBRATED"},
        service=LocalAssistService(provider=InjectedLocalModelProvider(lambda _: "read-only advice")),
    )
    assert result["status"] == "SUCCEEDED"
    assert result["automatic_dispatch"] is True
    assert result["local_assist_invoked"] is True
    assert result["formal_workspace_mutated"] is False
    assert result["agent_controller"] is True


def test_candidate_dispatch_requires_advisor_proof(tmp_path: Path) -> None:
    request = _request(tmp_path, "candidate")
    recommendation = _recommendation("candidate")
    result = dispatch_local_assist(
        request=request,
        recommendation=recommendation,
        recommendation_receipt=_receipt(request, recommendation),
        calibration={"status": "CALIBRATED"},
        advisor_canary={"status": "BLOCKED"},
        service=_service(),
    )
    assert result["status"] == "BLOCKED"
    assert result["failure_reason"] == "advisor_canary_not_proven"
    assert result["local_assist_invoked"] is False


def test_candidate_dispatch_isolated_and_lineage_bound(tmp_path: Path) -> None:
    request = _request(tmp_path, "candidate")
    recommendation = _recommendation("candidate")
    result = dispatch_local_assist(
        request=request,
        recommendation=recommendation,
        recommendation_receipt=_receipt(request, recommendation),
        calibration={"status": "CALIBRATED"},
        advisor_canary={"status": "SUCCEEDED"},
        service=_service(),
    )
    assert result["status"] == "SUCCEEDED"
    assert result["candidate_generated"] is True
    assert result["formal_workspace_mutated"] is False
    assert result["task_id"] == request.task_id


def test_verified_dispatch_runs_terminal_verifier(tmp_path: Path) -> None:
    request = _request(tmp_path, "verified-subtask")
    recommendation = _recommendation("verified-subtask")
    result = dispatch_local_assist(
        request=request,
        recommendation=recommendation,
        recommendation_receipt=_receipt(request, recommendation),
        calibration={"status": "CALIBRATED"},
        candidate_canary={"status": "SUCCEEDED"},
        service=_service(),
    )
    assert result["status"] == "SUCCEEDED"
    assert result["verifier_status"] == "pass"
    assert result["automatic_dispatch"] is True
    assert result["claim_boundary"]["value_measured"] is False


def test_dispatch_requires_receipt_and_calibration(tmp_path: Path) -> None:
    request = _request(tmp_path, "advisor")
    recommendation = _recommendation("advisor")
    no_receipt = dispatch_local_assist(
        request=request,
        recommendation=recommendation,
        recommendation_receipt=None,
        calibration={"status": "CALIBRATED"},
        service=_service(),
    )
    no_calibration = dispatch_local_assist(
        request=request,
        recommendation=recommendation,
        recommendation_receipt=_receipt(request, recommendation),
        calibration={"status": "BLOCKED"},
        service=_service(),
    )
    assert no_receipt["failure_reason"] == "recommendation_receipt_missing"
    assert no_calibration["failure_reason"] == "calibration_not_passed"
