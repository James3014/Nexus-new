"""P3-I5: Stage 3 Local Cheap Verifier Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    _p3_stage3_cheap_verifier,
)
from nexus.services.local_heal.receipt import build_repair_receipt


def test_cheap_verifier_empty_patch_fails():
    """P3-I5: Empty patch fails verification."""
    req = LocalModelExecutorRequest(
        task_id="p3-s3-1",
        problem_statement="test",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {}},
    )
    result = _p3_stage3_cheap_verifier("", req)
    assert result["stage3_verifier_performed"] is True
    assert result["stage3_verifier_passed"] is False
    assert result["stage3_verifier_reason"] == "empty_patch"
    assert result["stage3_verifier_model"] == "deterministic"


def test_cheap_verifier_nonempty_patch_passes():
    """P3-I5: Non-empty patch with structural markers passes."""
    req = LocalModelExecutorRequest(
        task_id="p3-s3-2",
        problem_statement="test",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {}},
    )
    patch = "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n def foo():\n-    pass\n+    return 42\n"
    result = _p3_stage3_cheap_verifier(patch, req)
    assert result["stage3_verifier_performed"] is True
    assert result["stage3_verifier_passed"] is True
    assert result["stage3_verifier_reason"] == "basic_checks_passed"


def test_cheap_verifier_trash_content_fails():
    """P3-I5: Trash content (no markers, short) fails."""
    req = LocalModelExecutorRequest(
        task_id="p3-s3-3",
        problem_statement="test",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {}},
    )
    result = _p3_stage3_cheap_verifier("xyz", req)
    assert result["stage3_verifier_performed"] is True
    assert result["stage3_verifier_passed"] is False
    assert result["stage3_verifier_reason"] == "patch_too_short"


def test_cheap_verifier_destructive_content_fails():
    """P3-I5: Destructive content (rm -rf) fails."""
    req = LocalModelExecutorRequest(
        task_id="p3-s3-4",
        problem_statement="test",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {}},
    )
    result = _p3_stage3_cheap_verifier("rm -rf /tmp/*", req)
    assert result["stage3_verifier_performed"] is True
    assert result["stage3_verifier_passed"] is False
    assert "destructive_content" in result["stage3_verifier_reason"]


def test_executor_shadow_runs_verifier():
    """P3-I5: Executor runs stage3 verifier in shadow topology."""
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
        task_id="p3-s3-5",
        problem_statement="Fix zeta function",
        repo_root="/tmp",
        target_file="zeta.py",
        selected_capabilities=(),
        evidence_refs=("patch.diff",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "cloud_with_local_assist",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "target_symbol": "eval",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    assert meta.get("stage3_verifier_performed") is True
    assert meta.get("stage3_verifier_model") == "deterministic"
    assert "stage3_local_cheap_verifier" in meta.get("assist_stages_activated", [])
    # P3-I6: executor now falls through to local model, so route status is stage4
    assert meta.get("p3_route_status") in ("shadow_stage3_verifier_blocked", "shadow_stage4_retry_complete", "shadow_stage4_retry_failed")


def test_executor_shadow_verifier_blocked():
    """P3-I5: Empty candidate → verifier blocks → route status reflects."""
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
        task_id="p3-s3-6",
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
    # P3-I6: executor falls through to local model
    assert meta.get("p3_route_status") in ("shadow_stage3_verifier_blocked", "shadow_stage4_retry_complete", "shadow_stage4_retry_failed")


def test_executor_shadow_verifier_meta_in_receipt():
    """P3-I5: Verifier fields appear in receipt."""
    class FakeCtx:
        instance_id = "p3-s3-7"
        stage3_verifier_performed = True
        stage3_verifier_passed = False
        stage3_verifier_reason = "empty_patch"
        stage3_verifier_model = "deterministic"

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["stage3_verifier_performed"] is True
    assert receipt["stage3_verifier_passed"] is False
    assert receipt["stage3_verifier_reason"] == "empty_patch"
    assert receipt["stage3_verifier_model"] == "deterministic"
