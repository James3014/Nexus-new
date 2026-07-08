"""P4-I4: Committee Invocation from P3 Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.receipt import build_repair_receipt


class FakeProvider:
    """Fake provider that returns empty output (retry fails)."""
    def generate(self, req):
        class R:
            output_text = ""
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


class PatchProvider:
    """Fake provider that returns a real patch (retry succeeds)."""
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


@pytest.fixture(autouse=True)
def setup_env():
    """Set up env vars for P4 tests."""
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    yield
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)
    os.environ.pop("NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW", None)
    os.environ.pop("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", None)
    os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY", None)
    os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", None)


def _hard_case_signal_snapshot():
    return {
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


def test_p3_hard_case_invokes_p4_when_gate_passes():
    """P4-I4: Hard case with valid specs invokes P4 committee."""
    req = LocalModelExecutorRequest(
        task_id="p4-inv-1",
        problem_statement="Complex cross-module refactoring",
        repo_root="/tmp",
        target_file="complex.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": _hard_case_signal_snapshot()},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    assert meta.get("p4_committee_gate_evaluated") is True
    assert meta.get("p4_committee_invocation_allowed") is True
    assert meta.get("p4_committee_invoked") is True
    assert meta.get("p4_committee_invocation_source") == "p3_hard_case_escalation"
    assert "committee_routed_tool" in meta.get("assist_stages_activated", [])


def test_p3_hard_case_skips_p4_when_gate_blocks():
    """P4-I4: Hard case with missing specs → gate blocks."""
    signal = _hard_case_signal_snapshot()
    signal["proposer_specs"] = []  # insufficient
    req = LocalModelExecutorRequest(
        task_id="p4-inv-2",
        problem_statement="Complex bug",
        repo_root="/tmp",
        target_file="bug.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": signal},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    assert meta.get("p4_committee_gate_evaluated") is True
    assert meta.get("p4_committee_invocation_allowed") is False
    assert meta.get("p4_committee_invoked") is None or meta.get("p4_committee_invoked") is False
    assert "committee_gate_blocked" in meta.get("assist_stages_activated", [])


def test_p3_local_only_never_invokes_p4():
    """P4-I4: local_only topology never invokes P4."""
    req = LocalModelExecutorRequest(
        task_id="p4-inv-3",
        problem_statement="Simple typo fix",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {
            "execution_topology": "local_only",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_model": "test-model",
            "executor_provider": "ollama",
        }},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=PatchProvider())
    meta = resp.raw_model_metadata
    assert meta.get("p4_committee_gate_evaluated") is None or meta.get("p4_committee_gate_evaluated") is False
    assert meta.get("p4_committee_invoked") is None or meta.get("p4_committee_invoked") is False


def test_p3_medium_task_never_invokes_p4():
    """P4-I4: medium task never invokes P4 (difficulty gate blocks)."""
    signal = _hard_case_signal_snapshot()
    signal["difficulty"] = "medium"
    signal["task_difficulty"] = "medium"
    req = LocalModelExecutorRequest(
        task_id="p4-inv-4",
        problem_statement="Fix database connection",
        repo_root="/tmp",
        target_file="db.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": signal},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    # medium task → local retry succeeds → no escalation → no P4
    assert meta.get("p4_committee_invoked") is None or meta.get("p4_committee_invoked") is False


def test_p4_committee_invocation_source_in_receipt():
    """P4-I4: Invocation source appears in receipt."""
    class FakeCtx:
        instance_id = "p4-inv-5"
        p4_committee_invocation_source = "p3_hard_case_escalation"
        p4_committee_invoked = True

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p4_committee_invocation_source"] == "p3_hard_case_escalation"
    assert receipt["p4_committee_invoked"] is True


def test_p4_committee_invoked_is_false_when_not_allowed():
    """P4-I4: invoked is false when gate blocks."""
    class FakeCtx:
        instance_id = "p4-inv-6"
        p4_committee_invoked = False
        p4_committee_blocked_reason = "insufficient_proposer_specs"

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p4_committee_invoked"] is False


def test_assist_stages_activated_contains_committee_routed_tool():
    """P4-I4: assist_stages_activated includes committee_routed_tool."""
    req = LocalModelExecutorRequest(
        task_id="p4-inv-7",
        problem_statement="Complex cross-module refactoring",
        repo_root="/tmp",
        target_file="complex.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": _hard_case_signal_snapshot()},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    stages = meta.get("assist_stages_activated", [])
    assert "stage1_local_diagnosis" in stages
    assert "stage2_cloud_candidate" in stages
    assert "stage3_local_cheap_verifier" in stages
    assert "stage4_local_retry" in stages
    assert "stage5_escalation_stub" in stages
    assert "committee_routed_tool" in stages
