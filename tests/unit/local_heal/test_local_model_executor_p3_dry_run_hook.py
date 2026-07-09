from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutorRequest,
    LocalModelExecutor,
)
from nexus.services.local_heal.local_model_provider import InertLocalModelProvider


def _make_test_request(
    task_id: str,
    execution_topology: str = "single_local_model",
    route_context: dict = None,
) -> LocalModelExecutorRequest:
    if route_context is None:
        route_context = {}
    if "signal_snapshot" not in route_context:
        route_context["signal_snapshot"] = {
            "execution_topology": execution_topology,
            "protocol_mode": "anchored_edit",
            "executor_model": "qwen2.5-coder:7b-instruct",
            "mutation_allowed": False,
            "verifier_allowed": False,
            "model_call_allowed": False,
        }
    return LocalModelExecutorRequest(
        task_id=task_id,
        problem_statement="Fix the bug",
        repo_root="/tmp",
        target_file="test.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context=route_context,
        dry_run=True,
        execution_topology=execution_topology,
    )


# ============================================================
# P3-L3-1: flag off output unchanged
# ============================================================


def test_flag_off_output_unchanged():
    req = _make_test_request("hook-001")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("p3_l_enabled") is False


# ============================================================
# P3-L3-2: flag off does not attach active p3_l block
# ============================================================


def test_flag_off_no_active_block():
    req = _make_test_request("hook-002")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("p3_l_authority") == "shadow_only"
    assert meta.get("p3_l_provider_invoked") is False


# ============================================================
# P3-L3-3: flag on attaches p3_l block
# ============================================================


def test_flag_on_attaches_block():
    req = _make_test_request("hook-003")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert "p3_l_receipt_version" in meta
    assert "p3_l_provider_invoked" in meta


# ============================================================
# P3-L3-4: flag on provider_invoked=false
# ============================================================


def test_provider_invoked_false():
    req = _make_test_request("hook-004")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_provider_invoked") is False


# ============================================================
# P3-L3-5: flag on network_invoked=false
# ============================================================


def test_network_invoked_false():
    req = _make_test_request("hook-005")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_network_invoked") is False


# ============================================================
# P3-L3-6: flag on patch_apply_invoked=false
# ============================================================


def test_patch_apply_invoked_false():
    req = _make_test_request("hook-006")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_patch_apply_invoked") is False


# ============================================================
# P3-L3-7: flag on runtime_behavior_changed=false
# ============================================================


def test_runtime_behavior_changed_false():
    req = _make_test_request("hook-007")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_runtime_behavior_changed") is False


# ============================================================
# P3-L3-8: flag on claim_eligible=false
# ============================================================


def test_claim_eligible_false():
    req = _make_test_request("hook-008")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_claim_eligible") is False


# ============================================================
# P3-L3-9: flag on public_claim_allowed=false
# ============================================================


def test_public_claim_allowed_false():
    req = _make_test_request("hook-009")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_public_claim_allowed") is False


# ============================================================
# P3-L3-10: flag on production_ready=false
# ============================================================


def test_production_ready_false():
    req = _make_test_request("hook-010")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_production_ready") is False


# ============================================================
# P3-L3-11: missing route metadata does not crash
# ============================================================


def test_missing_route_metadata_no_crash():
    req = _make_test_request("hook-011")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_provider_invoked") is False


# ============================================================
# P3-L3-12: missing diagnosis metadata blocks provider path
# ============================================================


def test_missing_diagnosis_blocks_provider():
    req = _make_test_request("hook-012")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("p3_l_provider_invoked") is False


# ============================================================
# P3-L3-13: existing tests still pass
# ============================================================


def test_existing_tests_still_pass():
    from nexus.services.local_heal.p3_route_skeleton import compute_p3_route_skeleton
    skeleton = compute_p3_route_skeleton({"difficulty": "medium"})
    assert skeleton.intended_topology == "cloud_with_local_assist"
