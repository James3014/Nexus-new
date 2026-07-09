from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_shadow_receipt import (
    P3ShadowReceipt,
    consolidate_p3_shadow_receipt,
    p3_shadow_receipt_to_dict,
)
from nexus.services.local_heal.p3_shadow_invariants import validate_p3_shadow_invariants


def _make_complete_component_metadata():
    return {
        "p3_route_skeleton_enabled": True,
        "p3_task_difficulty": "medium",
        "p3_intended_topology": "cloud_with_local_assist",
        "p3_local_diagnosis_enabled": True,
        "p3_diagnosis_cloud_ready": True,
        "p3_cloud_candidate_stub_enabled": True,
        "p3_cloud_stub_call_planned": True,
        "p3_cheap_verifier_enabled": True,
        "p3_cheap_verifier_planned": True,
        "p3_local_retry_enabled": True,
        "p3_local_retry_planned": True,
        "p3_shadow_orchestrator_enabled": True,
        "p3_shadow_authority": "shadow_only",
        "p3_cloud_call_invoked": False,
        "p3_local_model_call_invoked": False,
        "p3_patch_apply_invoked": False,
        "p3_runtime_behavior_changed": False,
        "p3_full_verifier_required": True,
        "p3_claim_gate_required": True,
        "p3_claim_eligible": False,
        "p3_public_claim_allowed": False,
        "p3_solved_claim_allowed": False,
    }


# ============================================================
# P3-J3-1: Complete valid metadata creates complete receipt
# ============================================================


def test_complete_metadata_creates_complete_receipt():
    metadata = _make_complete_component_metadata()
    invariant = validate_p3_shadow_invariants(metadata)
    receipt = consolidate_p3_shadow_receipt(metadata, invariant)
    assert receipt.p3_receipt_complete is True
    assert receipt.p3_invariant_passed is True
    assert receipt.p3_shadow_pipeline_present is True


# ============================================================
# P3-J3-2: Missing component creates blocked reason
# ============================================================


def test_missing_component_creates_blocked_reason():
    metadata = {
        "p3_route_skeleton_enabled": True,
        "p3_task_difficulty": "medium",
    }
    receipt = consolidate_p3_shadow_receipt(metadata)
    assert receipt.p3_receipt_complete is False
    assert receipt.p3_shadow_pipeline_present is False


# ============================================================
# P3-J3-3: cloud_call_invoked=true fails invariant
# ============================================================


def test_cloud_call_invoked_fails_invariant():
    metadata = _make_complete_component_metadata()
    metadata["p3_cloud_call_invoked"] = True
    invariant = validate_p3_shadow_invariants(metadata)
    receipt = consolidate_p3_shadow_receipt(metadata, invariant)
    assert receipt.p3_invariant_passed is False
    assert receipt.p3_receipt_complete is False


# ============================================================
# P3-J3-4: runtime_behavior_changed=true fails invariant
# ============================================================


def test_runtime_behavior_changed_fails_invariant():
    metadata = _make_complete_component_metadata()
    metadata["p3_runtime_behavior_changed"] = True
    invariant = validate_p3_shadow_invariants(metadata)
    receipt = consolidate_p3_shadow_receipt(metadata, invariant)
    assert receipt.p3_invariant_passed is False


# ============================================================
# P3-J3-5: public_claim_allowed=true fails invariant
# ============================================================


def test_public_claim_allowed_fails_invariant():
    metadata = _make_complete_component_metadata()
    metadata["p3_public_claim_allowed"] = True
    invariant = validate_p3_shadow_invariants(metadata)
    receipt = consolidate_p3_shadow_receipt(metadata, invariant)
    assert receipt.p3_invariant_passed is False


# ============================================================
# P3-J3-6: solved=true fails invariant
# ============================================================


def test_solved_fails_invariant():
    metadata = _make_complete_component_metadata()
    metadata["solved"] = True
    invariant = validate_p3_shadow_invariants(metadata)
    receipt = consolidate_p3_shadow_receipt(metadata, invariant)
    assert receipt.p3_invariant_passed is False


# ============================================================
# P3-J3-7: claim gate remains required
# ============================================================


def test_claim_gate_remains_required():
    metadata = _make_complete_component_metadata()
    receipt = consolidate_p3_shadow_receipt(metadata)
    assert receipt.p3_claim_gate_required is True


# ============================================================
# P3-J3-8: full verifier remains required
# ============================================================


def test_full_verifier_remains_required():
    metadata = _make_complete_component_metadata()
    receipt = consolidate_p3_shadow_receipt(metadata)
    assert receipt.p3_full_verifier_required is True


# ============================================================
# P3-J3-9: JSON serialization works
# ============================================================


def test_json_serializable():
    metadata = _make_complete_component_metadata()
    invariant = validate_p3_shadow_invariants(metadata)
    receipt = consolidate_p3_shadow_receipt(metadata, invariant)
    d = p3_shadow_receipt_to_dict(receipt)
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["p3_receipt_complete"] is True


# ============================================================
# P3-J3-10: Does not require runtime hook import
# ============================================================


def test_no_runtime_hook_import():
    import nexus.services.local_heal.p3_shadow_receipt as mod
    source = open(mod.__file__).read()
    assert "p6_runtime_hook" not in source


# ============================================================
# P3-J3-11: Does not require router import
# ============================================================


def test_no_router_import():
    import nexus.services.local_heal.p3_shadow_receipt as mod
    source = open(mod.__file__).read()
    assert "nexus.core.router" not in source


# ============================================================
# P3-J3-12: p3_public_claim_allowed=false in valid receipt
# ============================================================


def test_public_claim_allowed_false():
    metadata = _make_complete_component_metadata()
    receipt = consolidate_p3_shadow_receipt(metadata)
    assert receipt.p3_public_claim_allowed is False
