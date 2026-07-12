from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from nexus.services.local_assist_service import (
    LocalAssistRequest,
    LocalAssistService,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.local_heal.local_model_executor import LocalModelExecutorResponse


def _snapshot() -> dict[str, object]:
    return {
        "route_truth_source": "CapabilityPlanner",
        "execution_topology": "single_local_model",
        "protocol_mode": "unified_diff",
        "model_call_allowed": True,
        "executor_provider": "ollama",
        "executor_model": "qwen2.5-coder:7b",
    }


def _request(tmp_path: Path, action: str = "advisor") -> LocalAssistRequest:
    return LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id="assist-test-001",
        parent_task_id="agent-task-001",
        workspace_root=str(tmp_path),
        workspace_revision="test-revision",
        task_statement="Inspect the target and report the safest bounded next action.",
        action=action,
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("tests/services/test_local_assist_service.py",),
        verifier_command=(sys.executable, "-c", "print('verified')") if action == "verified-subtask" else (),
        risk_budget="low",
        time_budget=10.0,
        requested_role="advisor" if action == "advisor" else "candidate",
        mutation_policy="isolated_only",
        planner_snapshot=_snapshot(),
    )


def test_request_rejects_missing_planner_snapshot(tmp_path: Path) -> None:
    request = _request(tmp_path)
    invalid = request.__class__(**{**request.__dict__, "planner_snapshot": {}})

    with pytest.raises(ValueError, match="missing_planner_snapshot"):
        LocalAssistService().handle(invalid)


def test_advisor_records_invocation_and_delivery(tmp_path: Path) -> None:
    request = _request(tmp_path)
    provider = InjectedLocalModelProvider(lambda _: "diagnosis: target is the bounded localization point")

    response = LocalAssistService(provider=provider).handle(request)

    assert response.status == "SUCCEEDED"
    assert response.local_model_invoked is True
    assert response.output_delivered is True
    assert response.agent_consumed is False
    assert response.outcome_contributed is False
    assert response.provider == "injected"
    assert response.receipt_path
    receipt = json.loads(Path(response.receipt_path).read_text(encoding="utf-8"))
    assert receipt["provider_call_count"] == 1
    assert receipt["receipt_complete"] is True


def test_candidate_isolated_without_formal_workspace_mutation(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("def target():\n    return 1\n", encoding="utf-8")
    request = _request(tmp_path, "candidate")
    provider = InjectedLocalModelProvider(
        lambda _: "--- a/target.py\n+++ b/target.py\n@@ -1,1 +1,1 @@\n def target():\n-    return 1\n+    return 2\n"
    )

    response = LocalAssistService(provider=provider).handle(request)

    assert response.status == "SUCCEEDED"
    assert response.candidate_summary["candidate_count"] == 1
    assert response.candidate_summary["isolation_status"] == "isolated"
    assert target.read_text(encoding="utf-8") == "def target():\n    return 1\n"
    assert response.local_model_invoked is True
    assert response.planner_selected is True


def test_verified_subtask_requires_and_records_deterministic_verifier(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("def target():\n    return 1\n", encoding="utf-8")
    request = _request(tmp_path, "verified-subtask")
    provider = InjectedLocalModelProvider(
        lambda _: "--- a/target.py\n+++ b/target.py\n@@ -1,1 +1,1 @@\n def target():\n-    return 1\n+    return 2\n"
    )

    response = LocalAssistService(provider=provider).handle(request)

    assert response.verifier_summary["verifier_reached"] is True
    assert response.verifier_summary["verifier_status"] == "pass"
    assert response.claim_boundary["agent_consumed"] is False
    assert response.claim_boundary["value_measured"] is False


def test_executor_response_keeps_selected_and_invoked_distinct(tmp_path: Path) -> None:
    request = _request(tmp_path, "candidate")

    def fake_executor(*_args, **_kwargs):
        return LocalModelExecutorResponse(
            invoked=True,
            local_model_called=True,
            candidate_patch="",
            candidate_hash="empty",
            reasoning_summary="no_candidate",
            raw_model_metadata={},
            provider="ollama",
            model_name="qwen2.5-coder:7b",
            error="",
            timeout=False,
            evidence_refs=request.evidence_refs,
        )

    response = LocalAssistService(
        provider=InjectedLocalModelProvider(lambda _: "unused"),
        executor_runner=fake_executor,
    ).handle(request)

    assert response.local_model_invoked is True
    assert response.planner_selected is True
    assert response.output_delivered is False
    assert response.status == "FAILED"
