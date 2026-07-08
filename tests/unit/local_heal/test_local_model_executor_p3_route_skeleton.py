from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutorRequest,
    LocalModelExecutor,
    _resolve_execution_topology,
)
from nexus.services.local_heal.local_model_provider import InertLocalModelProvider


def _make_test_request(
    task_id: str,
    execution_topology: str = "single_local_model",
    target_file: str = "test.py",
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
        target_file=target_file,
        selected_capabilities=(),
        evidence_refs=(),
        route_context=route_context,
        dry_run=True,
        execution_topology=execution_topology,
    )


# ============================================================
# P3-A-14: local_model_executor default behavior unchanged
# ============================================================


def test_local_model_executor_includes_p3_skeleton_in_metadata():
    """Verify P3 skeleton metadata is present in executor response."""
    req = _make_test_request("test-task-001")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    
    meta = resp.raw_model_metadata
    assert "p3_route_skeleton_enabled" in meta
    assert "p3_route_authority" in meta
    assert "p3_task_difficulty" in meta
    assert "p3_intended_topology" in meta
    assert "p3_cloud_used" in meta
    assert "p3_cloud_call_invoked" in meta
    assert "p3_runtime_behavior_changed" in meta
    assert "p3_claim_eligible" in meta
    assert "p3_public_claim_allowed" in meta
    assert "p3_reason" in meta


def test_p3_skeleton_shadow_only_in_executor():
    """Verify P3 skeleton is shadow-only in executor response."""
    req = _make_test_request("test-task-002")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    
    meta = resp.raw_model_metadata
    assert meta["p3_route_skeleton_enabled"] is True
    assert meta["p3_route_authority"] == "shadow_only"
    assert meta["p3_cloud_used"] is False
    assert meta["p3_cloud_call_invoked"] is False
    assert meta["p3_runtime_behavior_changed"] is False
    assert meta["p3_claim_eligible"] is False
    assert meta["p3_public_claim_allowed"] is False


def test_p3_skeleton_metadata_json_serializable():
    """Verify P3 skeleton metadata is JSON serializable."""
    req = _make_test_request("test-task-003")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    
    meta = resp.raw_model_metadata
    serialized = json.dumps(meta)
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["p3_route_skeleton_enabled"] is True


def test_p3_skeleton_with_explicit_difficulty():
    """Verify P3 skeleton respects explicit difficulty in route_context."""
    req = _make_test_request(
        "test-task-004",
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "mutation_allowed": False,
                "verifier_allowed": False,
                "model_call_allowed": False,
            },
            "difficulty": "hard",
        },
    )
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    
    meta = resp.raw_model_metadata
    assert meta["p3_task_difficulty"] == "hard"
    assert meta["p3_intended_topology"] == "cloud_with_local_assist"
    assert meta["p3_hybrid_committee_planned"] is True


def test_p3_skeleton_easy_task_in_executor():
    """Verify P3 skeleton for easy task in executor response."""
    req = _make_test_request(
        "test-task-005",
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "mutation_allowed": False,
                "verifier_allowed": False,
                "model_call_allowed": False,
            },
            "difficulty": "easy",
        },
    )
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    
    meta = resp.raw_model_metadata
    assert meta["p3_task_difficulty"] == "easy"
    assert meta["p3_intended_topology"] == "local_only"
    assert meta["p3_hybrid_committee_planned"] is False


def test_p3_skeleton_does_not_override_p2_hash_truth():
    """Verify P3 skeleton does not override P2 hash/apply truth fields."""
    req = _make_test_request("test-task-006")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    
    meta = resp.raw_model_metadata
    p3_fields = [
        "p3_route_skeleton_enabled",
        "p3_route_authority",
        "p3_task_difficulty",
        "p3_intended_topology",
    ]
    p2_fields = [
        "selected_candidate_hash",
        "applied_patch_hash",
        "selected_candidate_hash_matches_applied",
    ]
    for field in p3_fields:
        assert field in meta
    for field in p2_fields:
        if field in meta:
            assert meta[field] is not None or meta[field] == ""


def test_p3_skeleton_does_not_change_solved_state():
    """Verify P3 skeleton does not change solved state."""
    req = _make_test_request("test-task-007")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    
    meta = resp.raw_model_metadata
    assert meta["p3_runtime_behavior_changed"] is False
    assert meta["p3_cloud_used"] is False
    assert meta["p3_cloud_call_invoked"] is False
