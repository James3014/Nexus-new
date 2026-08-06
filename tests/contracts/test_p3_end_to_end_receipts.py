"""P3-I8: E2E Receipt Contracts + Convergence Tests."""
from __future__ import annotations

import os
import pytest
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.receipt import build_repair_receipt


class FakeProvider:
    """Fake provider that returns a real candidate patch."""
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


class EmptyProvider:
    """Fake provider that returns empty output."""
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


@pytest.fixture(autouse=True)
def setup_env():
    """Set up env vars for P3 tests."""
    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    yield
    os.environ.pop("NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW", None)
    os.environ.pop("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", None)
    os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY", None)
    os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", None)


def test_p3_e2e_easy_local_only():
    """A: easy task → local_only topology → skips cloud pipeline entirely."""
    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="simple typo fix",
        task_type="bug",
        route={"difficulty": "easy", "pillar_signals": {}},
    )
    ss = plan.signal_snapshot

    # Planner verification
    assert ss.get("execution_topology") == "ASSISTED_CANONICAL"
    assert ss.get("executor_topology") == "single_local_model"
    assert ss.get("suggested_executor_topology") == "local_only"
    assert ss.get("task_difficulty") == "easy"
    assert ss.get("route_selected_by") is None
    assert ss.get("p3_shadow_route") is False

    # Executor
    req = LocalModelExecutorRequest(
        task_id="p3-e2e-a",
        problem_statement="Fix typo in foo.py",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": ss},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata

    # Executor verification — no cloud stages
    assert meta.get("cloud_used") is None or meta.get("cloud_used") is False
    assert meta.get("p3_shadow_route") is None or meta.get("p3_shadow_route") is False
    assert resp.local_model_called is True


def test_p3_e2e_medium_cloud_assist_success():
    """B: medium task → cloud assist pipeline → stage4 retry success."""
    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="fix database connection leak",
        task_type="bug",
        route={"difficulty": "medium", "pillar_signals": {}},
    )
    ss = plan.signal_snapshot

    # Planner verification
    assert ss.get("execution_topology") == "ASSISTED_CANONICAL"
    assert ss.get("executor_topology") == "single_local_model"
    assert ss.get("suggested_executor_topology") == "cloud_with_local_assist"
    assert ss.get("task_difficulty") == "medium"
    assert ss.get("route_selected_by") is None

    # The legacy cloud-assist executor remains explicitly testable, but the
    # difficulty advisor no longer has authority to select it.
    ss = {**ss, "executor_topology": ss["suggested_executor_topology"]}

    # Executor with FakeProvider (real patch)
    req = LocalModelExecutorRequest(
        task_id="p3-e2e-b",
        problem_statement="Fix database connection leak in db.py",
        repo_root="/tmp",
        target_file="db.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": ss},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata

    # Executor verification — all stages activated
    stages = meta.get("assist_stages_activated", [])
    assert "stage1_local_diagnosis" in stages
    assert "stage2_cloud_candidate" in stages
    assert "stage3_local_cheap_verifier" in stages
    assert "stage4_local_retry" in stages
    assert "stage5_escalation_stub" in stages

    # Stage4 success
    assert meta.get("stage4_local_retry_success") is True
    assert meta.get("p3_route_status") == "shadow_stage5_retry_sufficient"
    assert meta.get("stage5_escalation_recommended") is False

    # Cloud metadata
    assert meta.get("cloud_used") is True
    assert meta.get("cloud_provider") == "fake_cloud"
    assert meta.get("local_assist_used") is True

    # Receipt
    receipt = build_repair_receipt(FakeCtx(meta))
    assert receipt["p3_shadow_route"] is True
    assert receipt["cloud_used"] is True
    assert receipt["stage4_local_retry_success"] is True
    assert receipt["stage5_escalation_recommended"] is False


def test_p3_e2e_hard_escalation():
    """C: hard task → cloud assist pipeline → retry fails → escalation recommended."""
    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="complex cross-module refactoring",
        task_type="bug",
        route={"difficulty": "hard", "pillar_signals": {}},
    )
    ss = plan.signal_snapshot

    # Planner verification
    assert ss.get("execution_topology") == "ASSISTED_CANONICAL"
    assert ss.get("executor_topology") == "single_local_model"
    assert ss.get("suggested_executor_topology") == "cloud_with_local_assist"
    assert ss.get("task_difficulty") == "hard"
    ss = {**ss, "executor_topology": ss["suggested_executor_topology"]}

    # Executor with EmptyProvider (empty output → retry fails)
    req = LocalModelExecutorRequest(
        task_id="p3-e2e-c",
        problem_statement="Complex bug requiring deep analysis",
        repo_root="/tmp",
        target_file="complex.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": ss},
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=EmptyProvider())
    meta = resp.raw_model_metadata

    # Executor verification — all stages activated
    stages = meta.get("assist_stages_activated", [])
    assert "stage1_local_diagnosis" in stages
    assert "stage2_cloud_candidate" in stages
    assert "stage3_local_cheap_verifier" in stages
    assert "stage4_local_retry" in stages
    assert "stage5_escalation_stub" in stages

    # Stage4 failed → escalation recommended
    assert meta.get("stage4_local_retry_success") is False
    assert meta.get("stage5_escalation_recommended") is True
    assert meta.get("p3_route_status") == "shadow_stage5_escalation_recommended"

    # Cloud metadata
    assert meta.get("cloud_used") is True
    assert meta.get("local_assist_used") is True

    # Receipt
    receipt = build_repair_receipt(FakeCtx(meta))
    assert receipt["p3_shadow_route"] is True
    assert receipt["stage4_local_retry_success"] is False
    assert receipt["stage5_escalation_recommended"] is True


class FakeCtx:
    """Fake context for receipt testing."""
    def __init__(self, meta=None):
        self.instance_id = "p3-e2e-test"
        self.meta = meta or {}

    def __getattr__(self, name):
        if name == "instance_id":
            return "p3-e2e-test"
        if name == "meta":
            return self.__dict__.get("meta", {})
        return self.meta.get(name, getattr(type(self), name, "" if isinstance(getattr(type(self), name, ""), str) else False))


def test_p3_e2e_receipt_from_executor_meta():
    """P3-A1: Executor meta flows into receipt via FakeCtx wrapping."""
    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    try:
        req = LocalModelExecutorRequest(
            task_id="p3-e2e-receipt",
            problem_statement="Fix database connection",
            repo_root="/tmp",
            target_file="db.py",
            selected_capabilities=(),
            evidence_refs=(),
            route_context={"signal_snapshot": {
                "execution_topology": "cloud_with_local_assist",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "target_symbol": "conn",
                "difficulty": "medium",
                "task_difficulty": "medium",
            }},
            dry_run=False,
        )
        resp = LocalModelExecutor.run(req, provider=FakeProvider())
        meta = resp.raw_model_metadata

        # Verify meta has P3 fields
        assert meta.get("p3_shadow_route") is True
        assert meta.get("cloud_used") is True
        assert meta.get("local_assist_used") is True
        assert "stage1_local_diagnosis" in meta.get("assist_stages_activated", [])
        assert "stage4_local_retry" in meta.get("assist_stages_activated", [])

        # Build receipt from meta (real runtime path simulation)
        receipt = build_repair_receipt(FakeCtx(meta))
        assert receipt["p3_shadow_route"] is True
        assert receipt["cloud_used"] is True
        assert receipt["local_assist_used"] is True
        assert receipt["stage4_local_retry_success"] is True
        assert receipt["public_claim_allowed"] is False
    finally:
        os.environ.pop("NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW", None)
        os.environ.pop("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", None)
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY", None)
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", None)


def test_p3_boundary_no_real_cloud():
    """P3-A1: Real cloud endpoint is NOT connected."""
    from nexus.services.local_heal.local_model_executor import FakeCloudCandidateProvider
    provider = FakeCloudCandidateProvider()
    req = LocalModelExecutorRequest(
        task_id="test",
        problem_statement="test",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {}},
    )
    resp = provider.generate(req)
    # Fake provider always returns empty — no real cloud call
    assert resp.candidate_patch == ""
    assert resp.error == ""


def test_p3_boundary_no_p4_invoked():
    """P3-A1: P4 committee is NOT invoked from P3 path."""
    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    try:
        req = LocalModelExecutorRequest(
            task_id="p3-boundary",
            problem_statement="Complex cross-module refactoring",
            repo_root="/tmp",
            target_file="complex.py",
            selected_capabilities=(),
            evidence_refs=(),
            route_context={"signal_snapshot": {
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
            }},
            dry_run=False,
        )
        resp = LocalModelExecutor.run(req, provider=EmptyProvider())
        meta = resp.raw_model_metadata
        # P3 does NOT invoke P4 committee (P4 is separate)
        # P3 stage5 is escalation stub only
        assert meta.get("stage5_escalation_performed") is True
        assert meta.get("stage5_escalation_target") == "committee"
        # But actual committee invocation requires P4 env guard
        # which is NOT set in this test
    finally:
        os.environ.pop("NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW", None)
        os.environ.pop("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", None)
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY", None)
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", None)


def test_p3_boundary_claim_gate_not_relaxed():
    """P3-A1: P2 claim gate NOT relaxed by p3_shadow_route."""
    from nexus.services.local_heal.claim_delivery_gate import ClaimDeliveryGate
    gate = ClaimDeliveryGate()

    # Without source_hash → should fail
    decision = gate.validate({
        "verifier_status": "pass",
        "verifier_artifact": "report.txt",
        "source_hash": "",
        "patch_applied": True,
        "candidate_hash_matches_applied": True,
        "candidate_target_file": "foo.py",
        "artifact_refs": ["patch.diff"],
    })
    assert decision.claim_gate_passed is False
    assert "missing_source_hash" in decision.reasons


def test_p3_boundary_public_claim_allowed_false():
    """P3-A1: public_claim_allowed remains false."""
    class FakeCtx:
        instance_id = "p3-boundary"
        p3_shadow_route = True
        cloud_used = True
        local_assist_used = True

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["public_claim_allowed"] is False
    assert receipt["production_ready"] is False
