"""P4-I7/R4: E2E Committee Routed Tool Receipt Tests.

P4-R4: Real E2E receipt tests with fake producer (no FakeCtx for closure).
FakeCtx retained only for schema test (not closure proof).
"""
from __future__ import annotations

import os
import tempfile
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    evaluate_and_execute,
)
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.receipt import build_repair_receipt


# ── Shared helpers ──

_VALID_PATCH = "def foo():\n    return 42\n"


def _valid_candidate(model: str = "qwen") -> dict:
    return {
        "candidate_patch": _VALID_PATCH,
        "format": "UNIFIED_DIFF",
        "model": model,
        "candidate_id": f"cand-{model}",
    }


def _e2e_request(**overrides):
    defaults = {
        "task_id": "p4-e2e-r4",
        "repo_root": "/tmp",
        "target_file": "foo.py",
        "difficulty": "hard",
        "execution_topology": "cloud_with_local_assist",
        "p3_route_status": "shadow_stage5_escalation_recommended",
        "hard_case_escalation_reason": "retry_failed",
        "source_hash": "abc123",
        "evidence_refs": ("patch.diff", "verification_report.txt"),
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
    }
    defaults.update(overrides)
    return CommitteeRoutedToolRequest(**defaults)


# ── P3 Pipeline Integration Tests (no FakeCtx) ──


class PatchProvider:
    """Fake P3 provider."""
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


def test_p4_e2e_hard_activates_p3_stages():
    """P4-I7: hard task → P3 stages activated."""
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
    """P4-I7: medium task → no committee."""
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
        assert meta.get("p4_committee_invoked") is None or meta.get("p4_committee_invoked") is False
    finally:
        _cleanup_env()


def test_p4_e2e_local_only_no_committee():
    """P4-I7: local_only → no committee."""
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
    """P4-I7: flag off → no committee."""
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
        assert meta.get("p4_committee_invoked") is None or meta.get("p4_committee_invoked") is False
    finally:
        _cleanup_env()


# ── Real E2E Receipt Tests (P4-R4: non-FakeCtx) ──


@pytest.fixture(autouse=True)
def setup_p4_env():
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    yield
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_p4_e2e_receipt_full_success():
    """P4-R4: Full success path with real producer — all receipt fields populated.

    This test goes through evaluate_and_execute with a fake committee
    candidate producer, NOT FakeCtx.
    """
    def producer(req):
        return [_valid_candidate(model="qwen")]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _e2e_request(repo_root=tmpdir)
        result = evaluate_and_execute(request, candidate_producer=producer)

        assert result.receipt_fragment.get("p4_candidate_producer_present") is True
        assert result.receipt_fragment.get("p4_candidate_producer_invoked") is True
        assert result.receipt_fragment.get("p4_raw_candidate_count") == 1

        assert result.candidate_count >= 1
        assert result.canonical_candidate_count >= 1
        assert result.raw_candidate_count >= 1
        assert result.winner_found is True
        assert result.selected_candidate_apply_status == "applied"
        assert result.selected_candidate_verifier_status == "pass"
        assert result.receipt_fragment.get("p4_selected_candidate_hash_matches_applied") is True
        assert result.receipt_fragment.get("p4_committee_claim_gate_passed") is True
        assert result.receipt_fragment.get("committee_member_demand_wiring_status") == "WIRED"
        assert len(result.receipt_fragment.get("committee_member_demands", [])) == 3
        assert all(
            item["route_authority"] == "CapabilityPlanner"
            for item in result.receipt_fragment["committee_member_demands"]
        )
        assert result.solved_by_committee is True
        assert result.receipt_fragment.get("p4_fail_closed") is not True


def test_p4_e2e_malformed_only_fail_closed():
    """P4-R4: All malformed candidates → fail closed."""
    def producer(req):
        return [{"candidate_patch": "", "format": "UNIFIED_DIFF", "model": "qwen"}]

    request = _e2e_request()
    result = evaluate_and_execute(request, candidate_producer=producer)
    assert result.winner_found is False
    assert result.solved_by_committee is False
    assert result.receipt_fragment.get("p4_fail_closed") is True


def test_p4_e2e_hash_mismatch_fail_closed():
    """P4-R4: Hash mismatch → fail closed."""
    def producer(req):
        return [{
            "candidate_patch": "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
            "format": "SEARCH_REPLACE",
            "model": "qwen",
        }]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _e2e_request(repo_root=tmpdir)
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.winner_found is True
        assert result.receipt_fragment.get("p4_selected_candidate_hash_matches_applied") is False
        assert result.solved_by_committee is False
        assert result.receipt_fragment.get("p4_fail_closed") is True


def test_p4_e2e_verifier_fail_closed():
    """P4-R4: Verifier fails → fail closed."""
    def producer(req):
        return [{"candidate_patch": "def bad(:", "format": "UNIFIED_DIFF", "model": "qwen"}]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _e2e_request(repo_root=tmpdir)
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.selected_candidate_verifier_status == "fail"
        assert result.solved_by_committee is False
        assert result.receipt_fragment.get("p4_fail_closed") is True


def test_p4_e2e_flag_off_not_invoked():
    """P4-R4: P4 flag off → committee not invoked."""
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)
    request = _e2e_request()
    result = evaluate_and_execute(request, candidate_producer=lambda r: [_valid_candidate()])
    assert result.invocation_allowed is False
    assert result.invoked is False


def test_p4_e2e_medium_not_invoked():
    """P4-R4: medium difficulty → gate blocks → not invoked."""
    request = _e2e_request(difficulty="medium")
    result = evaluate_and_execute(request, candidate_producer=lambda r: [_valid_candidate()])
    assert result.invocation_allowed is False
    assert result.invoked is False


# ── Schema test (FakeCtx retained, NOT closure proof) ──


def test_p4_receipt_schema_fields_present():
    """P4-I7: FakeCtx schema test — all receipt fields present (not closure proof)."""
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
        expected = [
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
        for field in expected:
            assert field in receipt, f"Missing field: {field}"
        assert receipt["p4_committee_invoked"] is True
        assert receipt["p4_solved_by_committee"] is True
        assert receipt["public_claim_allowed"] is False
    finally:
        _cleanup_env()
