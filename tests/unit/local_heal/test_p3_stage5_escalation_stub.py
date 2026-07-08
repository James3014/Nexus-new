"""P3-I7: Stage 5 Hard-Case Escalation Stub Tests."""
from __future__ import annotations

import os

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    _p3_stage5_escalation_decision,
)
from nexus.services.local_heal.receipt import build_repair_receipt


def test_escalation_recommended_when_retry_fails():
    result = _p3_stage5_escalation_decision(
        cloud_meta={"stage3_verifier_passed": True},
        local_retry_success=False,
    )
    assert result["stage5_escalation_performed"] is True
    assert result["stage5_escalation_recommended"] is True
    assert "retry_failed" in result["stage5_escalation_reason"]
    assert result["stage5_escalation_target"] == "committee"


def test_escalation_not_recommended_when_retry_succeeds():
    result = _p3_stage5_escalation_decision(
        cloud_meta={"stage3_verifier_passed": True},
        local_retry_success=True,
    )
    assert result["stage5_escalation_performed"] is True
    assert result["stage5_escalation_recommended"] is False
    assert result["stage5_escalation_reason"] == "local_retry_sufficient"


def test_escalation_recommended_when_verifier_blocked_and_retry_fails():
    result = _p3_stage5_escalation_decision(
        cloud_meta={"stage3_verifier_passed": False, "stage3_verifier_reason": "empty_patch"},
        local_retry_success=False,
        reason="empty_patch",
    )
    assert result["stage5_escalation_recommended"] is True
    assert "verifier_blocked_and_retry_failed" in result["stage5_escalation_reason"]
    assert "empty_patch" in result["stage5_escalation_reason"]


def test_escalation_not_recommended_no_cloud_meta():
    result = _p3_stage5_escalation_decision(
        cloud_meta=None,
        local_retry_success=False,
    )
    assert result["stage5_escalation_performed"] is True
    assert result["stage5_escalation_recommended"] is False


def test_executor_includes_stage5_in_flow():
    os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "single_local_model"
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_MODEL"] = "qwen2.5-coder:7b"
    try:
        planner = CapabilityPlanner()
        plan = planner.plan(task_desc="test", task_type="bug", route={"difficulty": "hard", "pillar_signals": {}})
        ss = plan.signal_snapshot
        assert ss.get("execution_topology") == "cloud_with_local_assist"
    finally:
        os.environ.pop("NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW", None)
        os.environ.pop("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", None)
        os.environ.pop("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", None)


def test_escalation_stub_does_not_call_committee():
    """Stage5 stub only records recommendation, never calls committee."""
    result = _p3_stage5_escalation_decision(
        cloud_meta={"stage3_verifier_passed": False},
        local_retry_success=False,
    )
    assert result["stage5_escalation_recommended"] is True
    assert result["stage5_escalation_target"] == "committee"


def test_escalation_receipt_fields():
    class FakeCtx:
        stage5_escalation_performed = True
        stage5_escalation_recommended = True
        stage5_escalation_reason = "verifier_blocked_and_retry_failed"
        stage5_escalation_target = "committee"

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["stage5_escalation_performed"] is True
    assert receipt["stage5_escalation_recommended"] is True
    assert receipt["stage5_escalation_reason"] == "verifier_blocked_and_retry_failed"
    assert receipt["stage5_escalation_target"] == "committee"


def test_executor_runs_stage5_and_updates_p3_status():
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
        task_id="p3-stage5-1",
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
    assert "stage5_escalation_performed" in meta
    assert "stage5_escalation_recommended" in meta
    assert "stage5_escalation_reason" in meta
    assert "stage5_escalation_target" in meta
    assert "stage5_escalation_stub" in meta.get("assist_stages_activated", [])
    assert meta.get("p3_route_status") in (
        "shadow_stage5_escalation_recommended",
        "shadow_stage5_retry_sufficient",
    )
