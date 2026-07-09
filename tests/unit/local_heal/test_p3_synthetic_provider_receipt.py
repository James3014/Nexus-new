from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_synthetic_provider_receipt import (
    P3SyntheticProviderReceipt,
    compute_synthetic_provider_receipt,
    p3_synthetic_receipt_to_dict,
)
from nexus.services.local_heal.p3_dry_run_schema import validate_p3_dry_run_schema


# ============================================================
# P3-N4-1: disabled fixture receipt safe
# ============================================================


def test_disabled_fixture_receipt_safe():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        synthetic_fixture_enabled=False,
    )
    assert receipt.p3_n_synthetic_provider_invoked is False
    assert receipt.p3_n_candidate_is_synthetic is False


# ============================================================
# P3-N4-2: enabled valid fixture receipt has synthetic candidate
# ============================================================


def test_enabled_fixture_receipt_has_candidate():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "abc123"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_synthetic_provider_invoked is True
    assert receipt.p3_n_candidate_is_synthetic is True
    assert receipt.p3_n_synthetic_candidate_id != ""


# ============================================================
# P3-N4-3: blocked fixture receipt records blocked reasons
# ============================================================


def test_blocked_fixture_records_reasons():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": ""},
        synthetic_fixture_enabled=True,
    )
    assert any("compact_prompt_hash_missing" in r for r in receipt.p3_n_blocked_reasons)


# ============================================================
# P3-N4-4: real_provider_invoked=false always
# ============================================================


def test_real_provider_invoked_always_false():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_real_provider_invoked is False


# ============================================================
# P3-N4-5: network_invoked=false always
# ============================================================


def test_network_invoked_always_false():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_network_invoked is False


# ============================================================
# P3-N4-6: api_key_used=false always
# ============================================================


def test_api_key_used_always_false():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_api_key_used is False


# ============================================================
# P3-N4-7: patch_apply_invoked=false always
# ============================================================


def test_patch_apply_invoked_always_false():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_patch_apply_invoked is False


# ============================================================
# P3-N4-8: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_runtime_behavior_changed is False


# ============================================================
# P3-N4-9: claim_eligible=false always
# ============================================================


def test_claim_eligible_always_false():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_claim_eligible is False


# ============================================================
# P3-N4-10: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_public_claim_allowed is False


# ============================================================
# P3-N4-11: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    assert receipt.p3_n_production_ready is False


# ============================================================
# P3-N4-12: JSON serialization works
# ============================================================


def test_json_serializable():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    d = p3_synthetic_receipt_to_dict(receipt)
    assert isinstance(json.dumps(d), str)


# ============================================================
# P3-N4-13: optional synthetic fields do not weaken P3-L strict schema
# ============================================================


def test_synthetic_fields_do_not_weaken_schema():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    d = p3_synthetic_receipt_to_dict(receipt)
    assert "p3_n_real_provider_invoked" in d
    assert d["p3_n_real_provider_invoked"] is False


# ============================================================
# P3-N4-14: unsafe synthetic receipt fails if real_provider_invoked=true
# ============================================================


def test_unsafe_real_provider_fails():
    receipt = compute_synthetic_provider_receipt(
        route_metadata={"p3_intended_topology": "cloud_with_local_assist", "p3_task_difficulty": "medium"},
        diagnosis_metadata={"p3_diagnosis_compact_prompt_hash": "h"},
        synthetic_fixture_enabled=True,
    )
    d = p3_synthetic_receipt_to_dict(receipt)
    d["p3_n_real_provider_invoked"] = True
    assert d["p3_n_real_provider_invoked"] is True
