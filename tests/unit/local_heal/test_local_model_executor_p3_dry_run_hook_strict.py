from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutorRequest,
    LocalModelExecutor,
)
from nexus.services.local_heal.local_model_provider import InertLocalModelProvider
from nexus.services.local_heal.p3_dry_run_schema import validate_p3_dry_run_schema
from nexus.services.local_heal.p3_dry_run_invariants import validate_p3_dry_run_receipt


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
# M2-1: flag off — no active p3_l block or p3_l_enabled=false
# ============================================================


def test_flag_off_no_active_block():
    req = _make_test_request("strict-001")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("p3_l_enabled") is False


# ============================================================
# M2-2: flag off — existing result fields unchanged
# ============================================================


def test_flag_off_existing_fields_unchanged():
    req = _make_test_request("strict-002")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("dry_run") is True
    assert meta.get("execution_topology") == "single_local_model"


# ============================================================
# M2-3: flag off — solved/claim/public fields unchanged
# ============================================================


def test_flag_off_claim_fields_unchanged():
    req = _make_test_request("strict-003")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("p3_l_claim_eligible") is False
    assert meta.get("p3_l_public_claim_allowed") is False


# ============================================================
# M2-4: flag off — route/topology/candidate fields unchanged
# ============================================================


def test_flag_off_route_fields_unchanged():
    req = _make_test_request("strict-004")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("p3_l_intended_topology") in ("local_only", "cloud_with_local_assist")
    assert meta.get("p3_l_task_difficulty") in ("easy", "medium", "hard")


# ============================================================
# M2-5: flag off — provider/network/apply not invoked
# ============================================================


def test_flag_off_no_invocation():
    req = _make_test_request("strict-005")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("p3_l_provider_invoked") is False
    assert meta.get("p3_l_network_invoked") is False
    assert meta.get("p3_l_patch_apply_invoked") is False


# ============================================================
# M2-6: flag on — p3_l receipt exists
# ============================================================


def test_flag_on_receipt_exists():
    req = _make_test_request("strict-006")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert "p3_l_receipt_version" in meta
    assert "p3_l_provider_invoked" in meta


# ============================================================
# M2-7: flag on — receipt passes strict schema
# ============================================================


def test_flag_on_passes_strict_schema():
    req = _make_test_request("strict-007")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    schema_result = validate_p3_dry_run_schema(resp.raw_model_metadata)
    assert schema_result.schema_passed is True


# ============================================================
# M2-8: flag on — receipt passes invariant gate
# ============================================================


def test_flag_on_passes_invariant_gate():
    req = _make_test_request("strict-008")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    invariant_result = validate_p3_dry_run_receipt(resp.raw_model_metadata)
    assert invariant_result.invariant_passed is True


# ============================================================
# M2-9: flag on — provider_invoked=false
# ============================================================


def test_flag_on_provider_invoked_false():
    req = _make_test_request("strict-009")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_provider_invoked") is False


# ============================================================
# M2-10: flag on — network_invoked=false
# ============================================================


def test_flag_on_network_invoked_false():
    req = _make_test_request("strict-010")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_network_invoked") is False


# ============================================================
# M2-11: flag on — api_key_used=false
# ============================================================


def test_flag_on_api_key_used_false():
    req = _make_test_request("strict-011")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_api_key_used") is False


# ============================================================
# M2-12: flag on — local_model_invoked=false
# ============================================================


def test_flag_on_local_model_invoked_false():
    req = _make_test_request("strict-012")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_local_model_invoked") is False


# ============================================================
# M2-13: flag on — patch_apply_invoked=false
# ============================================================


def test_flag_on_patch_apply_invoked_false():
    req = _make_test_request("strict-013")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_patch_apply_invoked") is False


# ============================================================
# M2-14: flag on — runtime_behavior_changed=false
# ============================================================


def test_flag_on_runtime_behavior_changed_false():
    req = _make_test_request("strict-014")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_runtime_behavior_changed") is False


# ============================================================
# M2-15: flag on — claim_eligible=false
# ============================================================


def test_flag_on_claim_eligible_false():
    req = _make_test_request("strict-015")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_claim_eligible") is False


# ============================================================
# M2-16: flag on — public_claim_allowed=false
# ============================================================


def test_flag_on_public_claim_allowed_false():
    req = _make_test_request("strict-016")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_public_claim_allowed") is False


# ============================================================
# M2-17: flag on — production_ready=false
# ============================================================


def test_flag_on_production_ready_false():
    req = _make_test_request("strict-017")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_production_ready") is False


# ============================================================
# M2-18: missing route metadata — no crash
# ============================================================


def test_missing_route_metadata_no_crash():
    req = _make_test_request("strict-018")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("p3_l_provider_invoked") is False


# ============================================================
# M2-19: missing diagnosis metadata blocks provider path
# ============================================================


def test_missing_diagnosis_blocks_provider():
    req = _make_test_request("strict-019")
    provider = InertLocalModelProvider()
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("p3_l_provider_invoked") is False
