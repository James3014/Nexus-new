"""P3-I1: Cloud-with-Local-Assist Shadow Routing Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.receipt import build_repair_receipt


def test_p3_shadow_planner_injects_signal_fields():
    """P3-I1: Planner injects shadow routing fields when flag is enabled."""
    from nexus.engine.capability_planner import CapabilityPlanner

    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    try:
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bug", route={"pillar_signals": {}})
        ss = plan.signal_snapshot
        assert ss.get("p3_shadow_route") is True
        assert ss.get("execution_topology") == "cloud_with_local_assist"
        assert ss.get("cloud_used") is False
        assert ss.get("cloud_candidate_generated") is False
        assert ss.get("local_assist_used") is False
        assert ss.get("assist_stages_activated") == []
        assert ss.get("p3_route_status") == "shadow_no_cloud_endpoint"
    finally:
        os.environ.pop("NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW", None)
        os.environ.pop("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", None)
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", None)


def test_p3_shadow_executor_does_not_crash():
    """P3-I1: Executor handles cloud_with_local_assist topology without crash."""
    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = ""
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = False
                model_called = False
                model_name = ""
            return R()

    req = LocalModelExecutorRequest(
        task_id="p3-shadow-1",
        problem_statement="test",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "cloud_with_local_assist",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.invoked is False
    assert resp.raw_model_metadata.get("execution_topology") == "cloud_with_local_assist"
    assert resp.raw_model_metadata.get("p3_shadow_route") is True
    assert resp.raw_model_metadata.get("cloud_used") is True
    assert resp.raw_model_metadata.get("local_assist_used") is True
    assert resp.raw_model_metadata.get("p3_route_status") == "shadow_stage3_verifier_blocked"


def test_p3_shadow_receipt_contains_fields():
    """P3-I1: Receipt contains shadow routing fields."""
    class FakeCtx:
        instance_id = "p3-shadow-2"
        p3_shadow_route = True
        cloud_used = False
        cloud_candidate_generated = False
        local_assist_used = False
        assist_stages_activated = []
        p3_route_status = "shadow_no_cloud_endpoint"

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p3_shadow_route"] is True
    assert receipt["cloud_used"] is False
    assert receipt["cloud_candidate_generated"] is False
    assert receipt["local_assist_used"] is False
    assert receipt["assist_stages_activated"] == []
    assert receipt["p3_route_status"] == "shadow_no_cloud_endpoint"


def test_p3_shadow_flag_off_preserves_existing_topology():
    """P3-I1: When flag is off, existing topology behavior is preserved."""
    os.environ.pop("NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW", None)
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    try:
        from nexus.engine.capability_planner import CapabilityPlanner
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bug", route={"pillar_signals": {}})
        ss = plan.signal_snapshot
        assert ss.get("p3_shadow_route") is None or ss.get("p3_shadow_route") is False
        assert ss.get("execution_topology") == "single_local_model"
    finally:
        os.environ.pop("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", None)
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY", None)
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", None)


def test_p3_shadow_no_cloud_endpoint_fail_closed():
    """P3-I1: No cloud endpoint → fail-closed state."""
    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = ""
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = False
                model_called = False
                model_name = ""
            return R()

    req = LocalModelExecutorRequest(
        task_id="p3-shadow-3",
        problem_statement="test",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "cloud_with_local_assist",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    assert meta.get("cloud_used") is True
    assert meta.get("cloud_candidate_generated") is False
    assert meta.get("p3_route_status") == "shadow_stage3_verifier_blocked"
    assert resp.local_model_called is False


def test_p3_shadow_claim_gate_not_relaxed():
    """P3-I1: Shadow route does NOT relax claim gate."""
    from nexus.services.local_heal.claim_delivery_gate import ClaimDeliveryGate

    gate = ClaimDeliveryGate()
    decision = gate.validate({
        "verifier_status": "pass",
        "verifier_artifact": "report.txt",
        "source_hash": "abc",
        "patch_applied": True,
        "artifact_refs": ["patch.diff"],
        "candidate_hash_matches_applied": True,
        "candidate_target_file": "foo.py",
    })
    assert decision.claim_gate_passed is True

    # Shadow route should NOT change this behavior
    decision_shadow = gate.validate({
        "verifier_status": "pass",
        "verifier_artifact": "report.txt",
        "source_hash": "abc",
        "patch_applied": True,
        "artifact_refs": ["patch.diff"],
        "candidate_hash_matches_applied": True,
        "candidate_target_file": "foo.py",
        "p3_shadow_route": True,
    })
    assert decision_shadow.claim_gate_passed is True
