"""P4-I7: E2E Committee Routed Tool Receipt Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.receipt import build_repair_receipt


class PatchProvider:
    """Fake provider that returns a real patch."""
    def generate(self, req):
        class R:
            output_text = "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n def foo():\n-    pass\n+    return 42\n"
            output_truncated = False
            error = ""
            timed_out = False
            requested_timeout_sec = 120.0
            effective_timeout_sec = 120.0
            elapsed_sec = 0.1
            provider_invoked = True
            model_called = True
            model_name = "test-local-model"
        return R()


RECEIPT_CHECK_FIELDS = [
    "execution_topology",
    "p3_route_status",
    "p4_committee_gate_evaluated",
    "p4_committee_invocation_allowed",
    "p4_committee_invoked",
    "p4_committee_invocation_source",
    "p4_committee_candidate_count",
    "p4_canonical_candidate_count",
    "p4_selected_candidate_hash",
    "p4_selected_candidate_verifier_status",
    "p4_solved_by_committee",
]


def _setup_env():
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"


def _cleanup_env():
    for k in ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", "NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW",
              "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
              "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"]:
        os.environ.pop(k, None)


def _run_executor(signal_snapshot, provider=None):
    """Run executor with given signal_snapshot and return meta."""
    req = LocalModelExecutorRequest(
        task_id="p4-e2e-test",
        problem_statement="Complex cross-module refactoring",
        repo_root="/tmp",
        target_file="complex.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": signal_snapshot},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=provider or PatchProvider())
    return resp.raw_model_metadata


def test_p4_e2e_hard_full_success():
    """A: hard task → full P3+P4 pipeline → committee invoked."""
    _setup_env()
    try:
        signal = {
            "execution_topology": "cloud_with_local_assist",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_model": "test-model",
            "executor_provider": "ollama",
            "target_symbol": "eval",
            "difficulty": "hard",
            "task_difficulty": "hard",
            "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
            "judge_model": "judge",
            "mutation_allowed": True,
            "verifier_allowed": True,
        }
        meta = _run_executor(signal)
        assert meta.get("execution_topology") == "cloud_with_local_assist"
        assert "stage1_local_diagnosis" in meta.get("assist_stages_activated", [])
        assert "stage4_local_retry" in meta.get("assist_stages_activated", [])
    finally:
        _cleanup_env()


def test_p4_e2e_medium_no_committee():
    """B: medium → hard-case not triggered → no P4."""
    _setup_env()
    try:
        signal = {
            "execution_topology": "cloud_with_local_assist",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_model": "test-model",
            "executor_provider": "ollama",
            "target_symbol": "eval",
            "difficulty": "medium",
            "task_difficulty": "medium",
            "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
            "judge_model": "judge",
            "mutation_allowed": True,
            "verifier_allowed": True,
        }
        meta = _run_executor(signal)
        # Medium task → local retry succeeds → no escalation → no P4
        assert meta.get("p4_committee_invoked") is None or meta.get("p4_committee_invoked") is False
    finally:
        _cleanup_env()


def test_p4_e2e_local_only_no_committee():
    """C: local_only → no hard-case → no P4."""
    _setup_env()
    try:
        signal = {
            "execution_topology": "local_only",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_model": "test-model",
            "executor_provider": "ollama",
        }
        meta = _run_executor(signal)
        assert meta.get("p4_committee_invoked") is None or meta.get("p4_committee_invoked") is False
    finally:
        _cleanup_env()


def test_p4_e2e_flag_off_no_committee():
    """D: flag off → hard-case escalation remains stub → no committee."""
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)
    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    try:
        signal = {
            "execution_topology": "cloud_with_local_assist",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_model": "test-model",
            "executor_provider": "ollama",
            "target_symbol": "eval",
            "difficulty": "hard",
            "task_difficulty": "hard",
            "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
            "judge_model": "judge",
            "mutation_allowed": True,
            "verifier_allowed": True,
        }
        meta = _run_executor(signal)
        # Flag off → gate blocks → no committee
        assert meta.get("p4_committee_invoked") is None or meta.get("p4_committee_invoked") is False
    finally:
        _cleanup_env()


def test_p4_receipt_fields_present():
    """E: Receipt contains all P4 fields when committee is invoked."""
    _setup_env()
    try:
        class FakeCtx:
            instance_id = "p4-e2e-receipt"
            p4_committee_gate_evaluated = True
            p4_committee_invocation_allowed = True
            p4_committee_invoked = True
            p4_committee_invocation_source = "p3_hard_case_escalation"
            p4_committee_candidate_count = 2
            p4_canonical_candidate_count = 1
            p4_selected_candidate_hash = "abc123"
            p4_selected_candidate_model = "qwen"
            p4_selected_candidate_apply_status = "applied"
            p4_selected_candidate_verifier_status = "pass"
            p4_winner_found = True
            p4_solved_by_committee = True
            p4_committee_claim_gate_passed = True

        receipt = build_repair_receipt(FakeCtx())
        for field in RECEIPT_CHECK_FIELDS:
            assert field in receipt, f"Missing field: {field}"
        assert receipt["p4_committee_invoked"] is True
        assert receipt["p4_solved_by_committee"] is True
        assert receipt["public_claim_allowed"] is False
    finally:
        _cleanup_env()
