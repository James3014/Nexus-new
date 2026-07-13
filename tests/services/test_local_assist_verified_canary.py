from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
from nexus.services.local_assist_verified_canary import run_verified_subtask_canary
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


def _request(tmp_path: Path, *, verifier_command: tuple[str, ...] | None = None) -> LocalAssistRequest:
    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    return LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id="m3-f-001",
        parent_task_id="agent-task-001",
        workspace_root=str(tmp_path),
        workspace_revision="rev-1",
        task_statement="Apply and verify a bounded candidate change.",
        action="verified-subtask",
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("tests/services/test_local_assist_verified_canary.py",),
        verifier_command=verifier_command or (sys.executable, "-c", "print('verified')"),
        risk_budget="medium",
        time_budget=10.0,
        requested_role="candidate",
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
        "action": "verified-subtask",
        "reason_codes": ["verifier_sensitive"],
        "task_risk": "medium",
        "confidence": 0.8,
        "mutation_allowed": False,
        "verifier_required": True,
        "candidate_budget": 1,
        "time_budget_sec": 180,
        "shadow_only": True,
        "route_truth_source": "CapabilityPlanner",
    }
    result.update(overrides)
    return result


def _service() -> LocalAssistService:
    return LocalAssistService(
        provider=InjectedLocalModelProvider(
            lambda _: "--- a/target.py\n+++ b/target.py\n@@ -1,2 +1,2 @@\n def target():\n-    return 1\n+    return 2\n"
        )
    )


def test_verified_subtask_runs_isolated_verifier_and_records_rollback(tmp_path: Path) -> None:
    result = run_verified_subtask_canary(
        request=_request(tmp_path),
        recommendation=_recommendation(),
        candidate_canary={"status": "SUCCEEDED"},
        source_revision="rev-1",
        service=_service(),
    )
    assert result["status"] == "SUCCEEDED"
    assert result["verifier_status"] == "pass"
    assert result["verifier_reached"] is True
    assert result["rollback_reference"]
    assert result["formal_workspace_mutated"] is False
    assert result["agent_review_required"] is True
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == "def target():\n    return 1\n"


def test_verifier_failure_is_terminal(tmp_path: Path) -> None:
    result = run_verified_subtask_canary(
        request=_request(tmp_path, verifier_command=(sys.executable, "-c", "raise SystemExit(1)")),
        recommendation=_recommendation(),
        candidate_canary={"status": "SUCCEEDED"},
        source_revision="rev-1",
        service=_service(),
    )
    assert result["status"] == "FAILED"
    assert result["failure_reason"] == "verifier_failed"
    assert result["verifier_status"] == "fail"
    assert result["fallback_attempted"] is False


def test_verified_canary_requires_candidate_proof_and_verifier(tmp_path: Path) -> None:
    cases = (
        ({"status": "BLOCKED"}, {}, "candidate_canary_not_proven"),
        ({"status": "SUCCEEDED"}, {"verifier_known": False}, "verifier_command_missing"),
        ({"status": "SUCCEEDED"}, {"rollback_reference_available": False}, "rollback_reference_missing"),
        ({"status": "SUCCEEDED"}, {"formal_workspace_mutation_allowed": True}, "formal_mutation_enabled"),
    )
    for candidate_canary, overrides, reason in cases:
        result = run_verified_subtask_canary(
            request=_request(tmp_path),
            recommendation=_recommendation(),
            candidate_canary=candidate_canary,
            source_revision="rev-1",
            service=_service(),
            **overrides,
        )
        assert result["status"] == "BLOCKED"
        assert result["failure_reason"] == reason
        assert result["local_assist_invoked"] is False


def test_wrong_action_and_stale_revision_fail_closed(tmp_path: Path) -> None:
    wrong_action = run_verified_subtask_canary(
        request=_request(tmp_path),
        recommendation=_recommendation(action="candidate"),
        candidate_canary={"status": "SUCCEEDED"},
        source_revision="rev-1",
        service=_service(),
    )
    stale = run_verified_subtask_canary(
        request=replace(_request(tmp_path), workspace_revision="rev-1"),
        recommendation=_recommendation(),
        candidate_canary={"status": "SUCCEEDED"},
        source_revision="rev-2",
        service=_service(),
    )
    assert wrong_action["failure_reason"] == "action_not_verified_subtask"
    assert stale["failure_reason"] == "workspace_revision_stale"
