"""P3-I6: Stage 4 Local Retry After Cloud Fail Tests."""
from __future__ import annotations

import hashlib
import pytest
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


def test_stage4_fallback_generates_candidate():
    """P3-I6: Local retry generates candidate after cloud stages."""
    req = LocalModelExecutorRequest(
        task_id="p3-s4-1",
        problem_statement="Fix foo function",
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
                "target_symbol": "foo",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    assert meta.get("p3_stage4_local_retry_performed") is True
    assert meta.get("stage4_local_retry_success") is True
    assert meta.get("p3_route_status") in ("shadow_stage4_retry_complete", "shadow_stage5_retry_sufficient")
    assert "stage4_local_retry" in meta.get("assist_stages_activated", [])


def test_stage4_meta_includes_cloud_stages():
    """P3-I6: Stage4 meta includes all cloud stages."""
    req = LocalModelExecutorRequest(
        task_id="p3-s4-2",
        problem_statement="Fix foo",
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
                "target_symbol": "foo",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    stages = meta.get("assist_stages_activated", [])
    assert "stage1_local_diagnosis" in stages
    assert "stage2_cloud_candidate" in stages
    assert "stage3_local_cheap_verifier" in stages
    assert "stage4_local_retry" in stages
    assert meta.get("cloud_used") is True
    assert meta.get("local_assist_used") is True


def test_stage4_receipt_fields_present():
    """P3-I6: Receipt contains stage4 fields."""
    class FakeCtx:
        instance_id = "p3-s4-3"
        p3_stage4_local_retry = True
        p3_stage4_local_retry_performed = True
        stage4_local_retry_model = "test-model"
        stage4_local_retry_candidate_patch = "patch content"
        stage4_local_retry_candidate_hash = "abc123"
        stage4_local_retry_success = True

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["p3_stage4_local_retry"] is True
    assert receipt["p3_stage4_local_retry_performed"] is True
    assert receipt["stage4_local_retry_model"] == "test-model"
    assert receipt["stage4_local_retry_candidate_patch"] == "patch content"
    assert receipt["stage4_local_retry_candidate_hash"] == "abc123"
    assert receipt["stage4_local_retry_success"] is True


def test_stage4_fallback_empty_candidate():
    """P3-I6: Empty local model output → retry failed."""
    req = LocalModelExecutorRequest(
        task_id="p3-s4-4",
        problem_statement="Fix foo",
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
                "target_symbol": "foo",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=EmptyProvider())
    meta = resp.raw_model_metadata
    assert meta.get("p3_stage4_local_retry_performed") is True
    assert meta.get("stage4_local_retry_success") is False
    assert meta.get("p3_route_status") in ("shadow_stage4_retry_failed", "shadow_stage5_escalation_recommended")


def test_stage4_does_not_run_when_not_cloud_topology():
    """P3-I6: Stage4 does not run when topology is not cloud_with_local_assist."""
    req = LocalModelExecutorRequest(
        task_id="p3-s4-5",
        problem_statement="Fix foo",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "target_symbol": "foo",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    assert meta.get("p3_stage4_local_retry_performed") is None or meta.get("p3_stage4_local_retry_performed") is False
    assert meta.get("cloud_used") is None or meta.get("cloud_used") is False
