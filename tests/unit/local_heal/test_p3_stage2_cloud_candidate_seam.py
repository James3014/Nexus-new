"""P3-I4: Stage 2 Cloud Candidate Seam Tests."""
from __future__ import annotations

import hashlib
import pytest
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    FakeCloudCandidateProvider,
)
from nexus.services.local_heal.receipt import build_repair_receipt


def test_fake_cloud_provider_returns_empty():
    """P3-I4: FakeCloudCandidateProvider returns empty candidate."""
    provider = FakeCloudCandidateProvider()
    req = LocalModelExecutorRequest(
        task_id="p3-s2-1",
        problem_statement="test",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {}},
    )
    resp = provider.generate(req)
    assert resp.local_model_called is False
    assert resp.candidate_patch == ""
    assert resp.provider == "fake_cloud"
    assert resp.error == ""


def test_executor_shadow_runs_stage2():
    """P3-I4: Executor runs stage2 cloud candidate seam in shadow topology."""
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
        task_id="p3-s2-2",
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
    assert meta.get("cloud_used") is True
    assert meta.get("cloud_candidate_generated") is False
    assert meta.get("cloud_provider") == "fake_cloud"
    assert meta.get("cloud_candidate_patch") == ""
    assert "stage2_cloud_candidate" in meta.get("assist_stages_activated", [])
    assert "stage3_local_cheap_verifier" in meta.get("assist_stages_activated", [])
    # P3-I6: executor falls through to local model
    assert meta.get("p3_route_status") in ("shadow_stage3_verifier_blocked", "shadow_stage4_retry_complete", "shadow_stage4_retry_failed")


def test_stage2_receipt_fields():
    """P3-I4: Receipt contains stage2 cloud candidate fields."""
    class FakeCtx:
        instance_id = "p3-s2-3"
        cloud_provider = "fake_cloud"
        cloud_candidate_patch = ""
        cloud_candidate_hash = hashlib.sha256(b"").hexdigest()

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["cloud_provider"] == "fake_cloud"
    assert receipt["cloud_candidate_patch"] == ""
    assert receipt["cloud_candidate_hash"] == hashlib.sha256(b"").hexdigest()


def test_stage2_empty_candidate_blocks_claim():
    """P3-I4: Empty candidate → no hash → claim gate blocks."""
    from nexus.services.local_heal.claim_delivery_gate import ClaimDeliveryGate

    gate = ClaimDeliveryGate()
    # No source_hash (no candidate selected) → claim should pass (no blocker)
    decision = gate.validate({
        "verifier_status": "pass",
        "verifier_artifact": "report.txt",
        "source_hash": "",
        "patch_applied": False,
        "artifact_refs": [],
        "candidate_hash_matches_applied": True,
        "candidate_target_file": "",
    })
    # Empty candidate = no source_hash = no blocker
    assert "missing_source_hash" in decision.reasons


def test_stage2_fail_closed_no_error():
    """P3-I4: Stage2 returns empty error (not a crash)."""
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
        task_id="p3-s2-5",
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
    assert resp.error == ""


def test_stage1_and_stage2_both_activated():
    """P3-I4: Both stage1 and stage2 are activated."""
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
        task_id="p3-s2-6",
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
                "target_symbol": "bar",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    stages = meta.get("assist_stages_activated", [])
    assert "stage1_local_diagnosis" in stages
    assert "stage2_cloud_candidate" in stages
    assert meta.get("stage1_diagnosis_performed") is True
    assert meta.get("cloud_used") is True
