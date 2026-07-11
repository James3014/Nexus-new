from __future__ import annotations

import hashlib
from unittest.mock import patch

from nexus.services.local_heal.local_armor_attempt_receipt import (
    build_local_armor_attempt_receipt,
)
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


def _good_metadata() -> dict:
    return {
        "execution_topology": "localheal_pipeline",
        "selected_capabilities_used": [
            "local_model_executor",
            "repair_loop",
            "artifact_gate",
            "claim_gate",
            "delivery_gate",
        ],
        "protocol_mode": "anchored_edit",
        "protocol_normalization": {"protocol_used": "pipeline_result", "normalized": False},
        "source_anchor_present": True,
        "source_anchor_source": "locked_search",
        "source_anchor_hash": "abc123",
        "target_file": "pkg/mod.py",
        "target_symbol": "func",
        "locked_search_present": True,
        "failure_feedback_present": False,
        "final_authority": "NexusVerifier",
        "localheal_pipeline_actual_execution": True,
        "localheal_pipeline_availability_only": False,
        "localheal_pipeline_run_called": True,
        "pipeline_final_patch": "--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@ -1 +1 @@\n-old\n+new\n",
        "candidate_output_isolated": True,
        "selected_candidate_hash": "hash1",
        "applied_patch_hash": "hash1",
        "selected_candidate_hash_matches_applied": True,
        "verifier_result": "pass",
        "solved": True,
        "gate_results": {
            "artifact_gate": {"invoked": True, "evidence_present": True, "gate_passed": True, "outcome_contributed": True},
            "claim_gate": {"invoked": True, "evidence_present": True, "gate_passed": True, "outcome_contributed": True},
            "delivery_gate": {"invoked": True, "evidence_present": True, "gate_passed": True, "outcome_contributed": True},
        },
    }


def test_attempt_receipt_passes_only_with_runtime_truth_chain():
    receipt = build_local_armor_attempt_receipt(
        task_id="task-1",
        metadata=_good_metadata(),
        local_model_called=True,
        evidence_refs=("ref:1",),
        provider="ollama",
        model_name="qwen2.5-coder:7b",
        planner_snapshot={
            "execution_topology": "localheal_pipeline",
            "selected_executor": "local_model",
            "executor_model": "qwen2.5-coder:7b",
            "protocol_mode": "anchored_edit",
            "difficulty": "medium",
            "routing_tier": "L1_green_lane",
            "profile_selected": "STANDARD",
        },
    )

    assert receipt["attempt_gate_passed"] is True
    assert receipt["blocked_reasons"] == []
    assert receipt["claim_eligible"] is False
    assert receipt["public_claim_allowed"] is False
    assert receipt["production_ready"] is False
    assert receipt["capability_receipts"][0]["name"] == "local_model_executor"
    assert receipt["capability_receipts"][1]["name"] == "repair_loop"
    assert receipt["profile_transition"]["planner_selected_profile"] == "STANDARD"
    assert receipt["profile_transition"]["final_profile"] == "STANDARD"
    assert receipt["attempt_xray"]["planner_snapshot"]["routing_tier"] == "L1_green_lane"
    assert receipt["attempt_xray"]["runtime_trace"]["verifier_result"] == "pass"


def test_attempt_receipt_fails_closed_when_path_a_is_availability_only():
    metadata = _good_metadata()
    metadata["localheal_pipeline_actual_execution"] = False
    metadata["localheal_pipeline_availability_only"] = True
    metadata["solved"] = False
    metadata["verifier_result"] = "not_run"

    receipt = build_local_armor_attempt_receipt(
        task_id="task-2",
        metadata=metadata,
        local_model_called=True,
        evidence_refs=("ref:2",),
        provider="ollama",
        model_name="qwen2.5-coder:7b",
    )

    assert receipt["attempt_gate_passed"] is False
    assert "not_solved" in receipt["blocked_reasons"]
    assert "verifier_result:not_run" in receipt["blocked_reasons"]
    assert "causality:localheal_pipeline_availability_only" in receipt["blocked_reasons"]
    assert receipt["attempt_xray"]["runtime_trace"]["solved"] is False


def test_attempt_receipt_preserves_explicit_profile_transition_history():
    metadata = _good_metadata()
    metadata["initial_execution_profile"] = "LITE"
    metadata["final_execution_profile"] = "STANDARD"
    metadata["profile_transition_history"] = ["LITE", "STANDARD"]
    metadata["profile_escalation_count"] = 1
    metadata["profile_escalation_reasons"] = ["verification_failed"]

    receipt = build_local_armor_attempt_receipt(
        task_id="task-3",
        metadata=metadata,
        local_model_called=True,
        evidence_refs=("ref:3",),
        provider="ollama",
        model_name="qwen2.5-coder:7b",
        planner_snapshot={"profile_selected": "LITE"},
    )

    transition = receipt["profile_transition"]
    assert transition["planner_selected_profile"] == "LITE"
    assert transition["initial_profile"] == "LITE"
    assert transition["final_profile"] == "STANDARD"
    assert transition["transition_history"] == ["LITE", "STANDARD"]
    assert transition["escalation_count"] == 1
    assert transition["transition_evidence_complete"] is True


def test_attempt_receipt_marks_memory_as_invoked_when_query_executed():
    metadata = _good_metadata()
    metadata["selected_capabilities_used"] = ["local_model_executor", "memory", "repair_loop"]
    metadata["memory_retrieval_attempted"] = True
    metadata["memory_prompt_included"] = True
    metadata["memory_query_text_hash"] = "abc123"
    metadata["memory_selected_ids"] = ["lesson-1"]
    metadata["memory_selected_count"] = 1
    metadata["memory_trace_status"] = "TRACE_AVAILABLE"
    metadata["memory_retrieval_sources"] = ["LocalJsonlLessonStore", "FindingsMemoryLessonStore"]
    metadata["memory_no_match"] = False

    receipt = build_local_armor_attempt_receipt(
        task_id="task-memory",
        metadata=metadata,
        local_model_called=True,
        evidence_refs=("ref:memory",),
        provider="ollama",
        model_name="qwen2.5-coder:7b",
    )

    memory_receipt = next(item for item in receipt["capability_receipts"] if item["name"] == "memory")
    assert memory_receipt["invoked"] is True
    assert memory_receipt["evidence_present"] is True
    assert memory_receipt["gate_passed"] is True
    assert receipt["attempt_xray"]["runtime_trace"]["memory_selected_count"] == 1
    assert receipt["attempt_xray"]["runtime_trace"]["memory_trace_status"] == "TRACE_AVAILABLE"


def test_attempt_xray_preserves_backend_truth_for_lancedb():
    metadata = _good_metadata()
    metadata.update({
        "selected_capabilities_used": ["local_model_executor", "memory", "lancedb"],
        "memory_retrieval_attempted": True,
        "memory_lancedb_query_attempted": True,
        "memory_lancedb_query_succeeded": True,
        "memory_backend_receipts": [{
            "store": "MemoryRepositoryLessonStore",
            "backend": "lancedb",
            "query_attempted": True,
            "query_succeeded": True,
            "result_count": 0,
            "error": "",
        }],
        "memory_no_match": True,
    })

    receipt = build_local_armor_attempt_receipt(
        task_id="task-lancedb",
        metadata=metadata,
        local_model_called=True,
        evidence_refs=("ref:lancedb",),
        provider="ollama",
        model_name="qwen2.5-coder:7b",
    )

    runtime = receipt["attempt_xray"]["runtime_trace"]
    assert runtime["memory_lancedb_query_attempted"] is True
    assert runtime["memory_lancedb_query_succeeded"] is True
    assert runtime["memory_backend_receipts"][0]["result_count"] == 0


def test_attempt_receipt_exposes_committee_candidate_runtime_truth():
    metadata = _good_metadata()
    metadata["committee_candidates"] = [
        {
            "candidate_id": "candidate-1",
            "provider_called": True,
            "invoked": True,
            "selected": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "apply_status": "applied",
            "isolated_verifier_result": "pass",
        },
        {
            "candidate_id": "candidate-blocked",
            "provider_called": False,
            "invoked": False,
            "selected": False,
            "evidence_present": True,
            "gate_passed": False,
            "outcome_contributed": False,
            "apply_status": "none",
            "isolated_verifier_result": "none",
            "rejection_reason": "resource_policy_forbidden",
        },
    ]

    receipt = build_local_armor_attempt_receipt(
        task_id="task-committee-receipt",
        metadata=metadata,
        local_model_called=True,
        evidence_refs=("ref:committee",),
        provider="ollama",
        model_name="committee",
    )

    assert receipt["committee_candidate_receipts"] == [
        {
            "candidate_id": "candidate-1",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "apply_status": "applied",
            "verifier_result": "pass",
            "rejection_reason": "",
        },
        {
            "candidate_id": "candidate-blocked",
            "selected": False,
            "invoked": False,
            "evidence_present": True,
            "gate_passed": False,
            "outcome_contributed": False,
            "apply_status": "none",
            "verifier_result": "none",
            "rejection_reason": "resource_policy_forbidden",
        },
    ]


def test_executor_attaches_local_armor_attempt_receipt_for_localheal_pipeline():
    req = LocalModelExecutorRequest(
        task_id="attempt-receipt-integration",
        problem_statement="fix file",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor", "repair_loop"),
        evidence_refs=("ref:3",),
        dry_run=False,
        route_context={
            "target_symbol": "func",
            "difficulty": "easy",
            "local_armor_execution_profile": "STANDARD",
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "protocol_mode": "anchored_edit",
                "selected_executor": "local_model",
                "routing_tier": "L1_green_lane",
                "model_call_allowed": True,
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"

    with patch(
        "nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute"
    ) as mock_exec, patch(
        "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply"
    ) as mock_apply, patch(
        "nexus.services.local_heal.local_model_executor.run_isolated_verifier"
    ) as mock_verify:
        from nexus.services.local_heal.local_model_capability_executors import (
            CapabilityExecutionResult,
        )
        from nexus.services.local_heal.isolated_workspace_apply import (
            IsolatedApplyReceipt,
        )
        from nexus.services.local_heal.isolated_verifier import (
            IsolatedVerifierReceipt,
        )

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop",
            selected=True,
            invoked=True,
            gate_passed=True,
            outcome_contributed=True,
            evidence_present=True,
            failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text),
                "patch_synthesis_model_name": "qwen2.5-coder:7b",
                "patch_synthesis_model_called": True,
                "provider_invoked": True,
                "model_called": True,
                "localheal_pipeline_run_called": True,
                "localheal_pipeline_run_success": True,
                "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True,
                "orchestrator_run_reachable": True,
                "path_a_actual_execution": True,
            },
        )

        def _mock_apply(apply_req):
            return IsolatedApplyReceipt(
                task_id="attempt-receipt-integration",
                workspace_path="/tmp/ws",
                target_file="file.py",
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash=apply_req.selected_candidate_hash,
                applied_patch_hash=apply_req.selected_candidate_hash,
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )

        mock_apply.side_effect = _mock_apply
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="attempt-receipt-integration",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(
            req,
            provider=InjectedLocalModelProvider(lambda _: diff_text),
        )

    attempt_receipt = resp.raw_model_metadata.get("local_armor_attempt_receipt")
    assert isinstance(attempt_receipt, dict)
    assert attempt_receipt["schema"] == "nexus.local_heal.local_armor_attempt_receipt.v1"
    assert attempt_receipt["task_id"] == "attempt-receipt-integration"
    assert attempt_receipt["attempt_gate_passed"] is True
    assert attempt_receipt["profile_transition"]["planner_selected_profile"] == "STANDARD"
    assert attempt_receipt["attempt_xray"]["planner_snapshot"]["selected_executor"] == "local_model"
    assert attempt_receipt["attempt_xray"]["planner_snapshot"]["difficulty"] == "easy"
    assert attempt_receipt["attempt_xray"]["runtime_trace"]["patch_lifecycle_state"] == "verifier_passed"


def test_executor_memory_receipt_captures_prompt_influence():
    req = LocalModelExecutorRequest(
        task_id="memory-receipt-integration",
        problem_statement="fix normalize_score",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor", "memory"),
        evidence_refs=("ref:memory",),
        dry_run=False,
        route_context={
            "target_symbol": "normalize_score",
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "protocol_mode": "anchored_edit",
                "selected_executor": "local_model",
                "model_call_allowed": True,
            },
        },
    )

    class _FakeLesson:
        def __init__(self, summary: str) -> None:
            self.summary = summary

    class _FakeAdapter:
        def __init__(self, enabled: bool = True) -> None:
            self.last_metadata = {
                "query_text_hash": "hash-memory",
                "selected_ids": ["lesson-1"],
                "memory_evidence_ids": ["lesson-1"],
                "retrieval_sources": ["LocalJsonlLessonStore"],
                "source_errors": {},
                "source_counts": {"LocalJsonlLessonStore": 1},
                "accepted": 1,
                "primary_selected_id": "lesson-1",
                "no_memory_match": False,
                "rerank_mode": True,
                "anchor_symbol": "normalize_score",
                "anchor_file": "file.py",
            }

        def retrieve_reranked(self, **kwargs):
            return [_FakeLesson("Always clamp output, not input")]

    with patch(
        "nexus.services.local_heal.memory_retrieval_adapter.MemoryRetrievalAdapter",
        _FakeAdapter,
    ), patch(
        "nexus.services.local_heal.local_model_source_anchor.build_local_model_source_anchor"
    ) as mock_anchor:
        mock_anchor.return_value.span_hash = "anchorhash"
        mock_anchor.return_value.canonical_span_source = "ast_boundary"
        resp = LocalModelExecutor.run(
            req,
            provider=InjectedLocalModelProvider(lambda _: "<<<<<<< REPLACE\nreturn 1\n>>>>>>> REPLACE"),
        )

    attempt_receipt = resp.raw_model_metadata["local_armor_attempt_receipt"]
    memory_receipt = next(item for item in attempt_receipt["capability_receipts"] if item["name"] == "memory")
    assert memory_receipt["invoked"] is True
    assert attempt_receipt["attempt_xray"]["runtime_trace"]["memory_retrieval_attempted"] is True
    assert attempt_receipt["attempt_xray"]["runtime_trace"]["memory_prompt_included"] is True
    assert attempt_receipt["attempt_xray"]["runtime_trace"]["memory_selected_count"] == 1
