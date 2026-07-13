from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

from nexus.services.local_assist_candidate_canary import (
    record_candidate_adoption,
    run_candidate_canary,
)
from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


def _request(tmp_path: Path) -> LocalAssistRequest:
    target = tmp_path / "target.py"
    target.write_text("def target():\n    return 1\n", encoding="utf-8")
    return LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id="m3-e-001",
        parent_task_id="agent-task-001",
        workspace_root=str(tmp_path),
        workspace_revision="rev-1",
        task_statement="Implement a bounded candidate change in the target.",
        action="candidate",
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("tests/services/test_local_assist_candidate_canary.py",),
        verifier_command=(sys.executable, "-c", "print('verified')"),
        risk_budget="low",
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
        "action": "candidate",
        "reason_codes": ["bounded_implementation"],
        "task_risk": "low",
        "confidence": 0.9,
        "mutation_allowed": False,
        "verifier_required": False,
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


def test_candidate_canary_isolates_and_records_agent_adoption(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = run_candidate_canary(
        request=request,
        recommendation=_recommendation(),
        advisor_canary={"status": "SUCCEEDED"},
        source_revision="rev-1",
        service=_service(),
    )
    assert result["status"] == "SUCCEEDED"
    assert result["candidate_generated"] is True
    assert result["formal_workspace_mutated"] is False
    assert result["adoption_decision"] == "pending"
    assert result["candidate_identity"]["selected_candidate_hash_matches_applied"] is True
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == "def target():\n    return 1\n"

    adopted = record_candidate_adoption(
        result,
        decision="adopted",
        consumed_candidate_hash=result["candidate_identity"]["selected_candidate_hash"],
    )
    assert adopted["adoption_decision"] == "adopted"
    assert adopted["formal_workspace_mutated"] is False
    assert adopted["claim_boundary"]["outcome_contributed"] is False


def test_candidate_canary_requires_advisor_and_isolation_preconditions(tmp_path: Path) -> None:
    cases = (
        ({"status": "BLOCKED"}, {}, "advisor_canary_not_proven"),
        ({"status": "SUCCEEDED"}, {"candidate_isolation_available": False}, "candidate_isolation_unavailable"),
        ({"status": "SUCCEEDED"}, {"formal_workspace_mutation_allowed": True}, "formal_mutation_enabled"),
        ({"status": "SUCCEEDED"}, {"target_bounded": False}, "target_scope_unbounded"),
        ({"status": "SUCCEEDED"}, {"verifier_known": False}, "verifier_command_missing"),
    )
    for advisor_canary, overrides, reason in cases:
        result = run_candidate_canary(
            request=_request(tmp_path),
            recommendation=_recommendation(),
            advisor_canary=advisor_canary,
            source_revision="rev-1",
            service=_service(),
            **overrides,
        )
        assert result["status"] == "BLOCKED"
        assert result["failure_reason"] == reason
        assert result["local_assist_invoked"] is False


def test_stale_candidate_and_bad_hash_fail_closed(tmp_path: Path) -> None:
    request = _request(tmp_path)
    stale = run_candidate_canary(
        request=request,
        recommendation=_recommendation(),
        advisor_canary={"status": "SUCCEEDED"},
        source_revision="rev-2",
        service=_service(),
    )
    assert stale["failure_reason"] == "workspace_revision_stale"

    result = run_candidate_canary(
        request=request,
        recommendation=_recommendation(),
        advisor_canary={"status": "SUCCEEDED"},
        source_revision="rev-1",
        service=_service(),
    )
    bad_hash = record_candidate_adoption(
        result,
        decision="adopted",
        consumed_candidate_hash="wrong-hash",
    )
    assert bad_hash["adoption_decision"] == "rejected"
    assert bad_hash["failure_reason"] == "candidate_hash_mismatch"


def test_non_candidate_recommendation_is_not_executed(tmp_path: Path) -> None:
    result = run_candidate_canary(
        request=replace(_request(tmp_path), action="candidate"),
        recommendation=_recommendation(action="advisor"),
        advisor_canary={"status": "SUCCEEDED"},
        source_revision="rev-1",
        service=_service(),
    )
    assert result["status"] == "BLOCKED"
    assert result["failure_reason"] == "action_not_candidate"
