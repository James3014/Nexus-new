from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_dry_run_receipt import (
    P3DryRunReceipt,
    compute_p3_dry_run_receipt,
    p3_dry_run_receipt_to_dict,
)


# ============================================================
# P3-L2-1: shadow_only receipt is safe
# ============================================================


def test_shadow_only_receipt_safe():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "local_only", "p3_task_difficulty": "easy"},
        guard_state="shadow_only",
    )
    assert receipt.p3_l_enabled is False
    assert receipt.p3_l_authority == "shadow_only"
    assert receipt.p3_l_runtime_behavior_changed is False


# ============================================================
# P3-L2-2: local_only dry-run does not build provider request
# ============================================================


def test_local_only_no_provider_request():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "local_only", "p3_task_difficulty": "easy"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_provider_request_built is False
    assert receipt.p3_l_receipt_complete is True


# ============================================================
# P3-L2-3: medium cloud builds request but does not invoke
# ============================================================


def test_medium_cloud_builds_no_invoke():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_provider_request_built is True
    assert receipt.p3_l_provider_invoked is False
    assert receipt.p3_l_network_invoked is False


# ============================================================
# P3-L2-4: hard cloud builds request but does not invoke
# ============================================================


def test_hard_cloud_builds_no_invoke():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "hard"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "def456"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_provider_request_built is True
    assert receipt.p3_l_provider_invoked is False


# ============================================================
# P3-L2-5: missing env guard downgrades/blocks safely
# ============================================================


def test_missing_env_guard_downgrades():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        guard_state="shadow_only",
        env_guard_override=False,
    )
    assert receipt.p3_l_env_guard_present is False
    assert receipt.p3_l_provider_invoked is False


# ============================================================
# P3-L2-6: missing compact prompt hash blocks provider path
# ============================================================


def test_missing_prompt_hash_blocks():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": ""},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert any("compact_prompt_hash_missing" in r for r in receipt.p3_l_blocked_reasons)


# ============================================================
# P3-L2-7: provider_invoked=false always
# ============================================================


def test_provider_invoked_always_false():
    for state in ("shadow_only", "env_guarded_dry_run"):
        receipt = compute_p3_dry_run_receipt(
            route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
            diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
            guard_state=state,
            env_guard_override=True,
        )
        assert receipt.p3_l_provider_invoked is False


# ============================================================
# P3-L2-8: network_invoked=false always
# ============================================================


def test_network_invoked_always_false():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_network_invoked is False


# ============================================================
# P3-L2-9: api_key_used=false always
# ============================================================


def test_api_key_used_always_false():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_api_key_used is False


# ============================================================
# P3-L2-10: local_model_invoked=false always
# ============================================================


def test_local_model_invoked_always_false():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_local_model_invoked is False


# ============================================================
# P3-L2-11: patch_apply_invoked=false always
# ============================================================


def test_patch_apply_invoked_always_false():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_patch_apply_invoked is False


# ============================================================
# P3-L2-12: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_runtime_behavior_changed is False


# ============================================================
# P3-L2-13: claim_eligible=false always
# ============================================================


def test_claim_eligible_always_false():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_claim_eligible is False


# ============================================================
# P3-L2-14: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_public_claim_allowed is False


# ============================================================
# P3-L2-15: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    assert receipt.p3_l_production_ready is False


# ============================================================
# P3-L2-16: JSON serialization works
# ============================================================


def test_json_serializable():
    receipt = compute_p3_dry_run_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        guard_state="env_guarded_dry_run",
        env_guard_override=True,
    )
    d = p3_dry_run_receipt_to_dict(receipt)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
