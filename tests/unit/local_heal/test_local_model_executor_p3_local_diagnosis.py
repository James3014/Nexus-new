from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_local_diagnosis import (
    compute_p3_local_diagnosis,
    p3_diagnosis_to_dict,
)
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


def test_executor_returns_p3_diagnosis_metadata():
    req = _make_test_request("diag-task-001")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert "p3_local_diagnosis_enabled" in meta
    assert "p3_diagnosis_cloud_ready" in meta


def test_p3_diagnosis_shadow_only_in_executor():
    req = _make_test_request("diag-task-002")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta["p3_local_diagnosis_authority"] == "shadow_only"
    assert meta["p3_diagnosis_cloud_call_invoked"] is False
    assert meta["p3_diagnosis_runtime_behavior_changed"] is False


def test_p3_diagnosis_json_serializable():
    req = _make_test_request("diag-task-003")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    serialized = json.dumps(resp.raw_model_metadata)
    assert isinstance(serialized, str)


def test_p3_diagnosis_standalone():
    diag = compute_p3_local_diagnosis(
        request_metadata={"task_id": "standalone-001"},
        anchor_metadata={"target_file": "foo.py", "target_symbol": "bar"},
        hash_chain_metadata={"raw_output_hash": "h1", "normalized_patch_hash": "h2", "applied_patch_hash": "h3"},
    )
    assert diag.cloud_ready is True
    meta = p3_diagnosis_to_dict(diag)
    assert meta["p3_diagnosis_cloud_ready"] is True
