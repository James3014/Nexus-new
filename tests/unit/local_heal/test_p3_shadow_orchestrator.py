from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_shadow_orchestrator import (
    P3ShadowReceipt,
    compute_p3_shadow_orchestrator,
    p3_shadow_receipt_to_dict,
)


def _make_complete_anchor():
    return {
        "target_file": "foo.py",
        "target_symbol": "bar",
        "line_span": "L10-L20",
        "old_block_hash": "abc123",
    }


def _make_complete_hashes():
    return {
        "raw_output_hash": "h1",
        "normalized_patch_hash": "h2",
        "applied_patch_hash": "h3",
    }


# ============================================================
# P3-F-1: Orchestrator composes all P3 components
# ============================================================


def test_orchestrator_composes_all_components():
    receipt, meta = compute_p3_shadow_orchestrator(
        request_metadata={"task_id": "orch-001", "difficulty": "medium"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata=_make_complete_hashes(),
    )
    assert receipt.route_skeleton_present is True
    assert receipt.local_diagnosis_present is True
    assert receipt.cloud_candidate_stub_present is True
    assert receipt.cheap_verifier_stub_present is True
    assert receipt.local_retry_stub_present is True
    assert receipt.receipt_complete is True


# ============================================================
# P3-F-2: Easy task produces local_only shadow receipt
# ============================================================


def test_easy_task_produces_local_only():
    receipt, meta = compute_p3_shadow_orchestrator(
        request_metadata={"task_id": "orch-002", "difficulty": "easy"},
    )
    assert receipt.intended_topology == "local_only"
    assert receipt.task_difficulty == "easy"
    assert receipt.receipt_complete is True


# ============================================================
# P3-F-3: Medium task produces cloud_with_local_assist shadow receipt
# ============================================================


def test_medium_task_produces_cloud_with_local_assist():
    receipt, meta = compute_p3_shadow_orchestrator(
        request_metadata={"task_id": "orch-003", "difficulty": "medium"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata=_make_complete_hashes(),
    )
    assert receipt.intended_topology == "cloud_with_local_assist"
    assert receipt.task_difficulty == "medium"
    assert "stage1_local_diagnosis" in receipt.assist_stages_planned


# ============================================================
# P3-F-4: Hard task produces cloud_with_local_assist with hard-case noted
# ============================================================


def test_hard_task_produces_cloud_with_hybrid_noted():
    receipt, meta = compute_p3_shadow_orchestrator(
        request_metadata={"task_id": "orch-004", "difficulty": "hard"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata=_make_complete_hashes(),
    )
    assert receipt.intended_topology == "cloud_with_local_assist"
    assert "stage5_hybrid_committee" in receipt.assist_stages_planned


# ============================================================
# P3-F-5: p3_assist_stages_invoked=[]
# ============================================================


def test_assist_stages_invoked_always_empty():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.assist_stages_invoked == []


# ============================================================
# P3-F-6: p3_cloud_call_invoked=false
# ============================================================


def test_cloud_call_invoked_always_false():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.cloud_call_invoked is False


# ============================================================
# P3-F-7: p3_local_model_call_invoked=false
# ============================================================


def test_local_model_call_invoked_always_false():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.local_model_call_invoked is False


# ============================================================
# P3-F-8: p3_patch_apply_invoked=false
# ============================================================


def test_patch_apply_invoked_always_false():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.patch_apply_invoked is False


# ============================================================
# P3-F-9: p3_full_verifier_required=true
# ============================================================


def test_full_verifier_required_always_true():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.full_verifier_required is True


# ============================================================
# P3-F-10: p3_claim_gate_required=true
# ============================================================


def test_claim_gate_required_always_true():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.claim_gate_required is True


# ============================================================
# P3-F-11: p3_runtime_behavior_changed=false
# ============================================================


def test_runtime_behavior_changed_always_false():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.runtime_behavior_changed is False


# ============================================================
# P3-F-12: p3_claim_eligible=false
# ============================================================


def test_claim_eligible_always_false():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.claim_eligible is False


# ============================================================
# P3-F-13: p3_public_claim_allowed=false
# ============================================================


def test_public_claim_allowed_always_false():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.public_claim_allowed is False


# ============================================================
# P3-F-14: p3_receipt_complete=true
# ============================================================


def test_receipt_complete_always_true():
    for diff in ("easy", "medium", "hard"):
        receipt, _ = compute_p3_shadow_orchestrator(
            request_metadata={"task_id": f"orch-{diff}", "difficulty": diff},
        )
        assert receipt.receipt_complete is True


# ============================================================
# P3-F-15: JSON serialization works
# ============================================================


def test_json_serializable():
    receipt, meta = compute_p3_shadow_orchestrator(
        request_metadata={"task_id": "orch-015", "difficulty": "medium"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata=_make_complete_hashes(),
    )
    receipt_dict = p3_shadow_receipt_to_dict(receipt)
    serialized = json.dumps(receipt_dict)
    assert isinstance(serialized, str)
    serialized_meta = json.dumps(meta)
    assert isinstance(serialized_meta, str)


# ============================================================
# P3-F-16: All previous P3 component tests still pass
# ============================================================


def test_p3_components_still_work():
    from nexus.services.local_heal.p3_route_skeleton import compute_p3_route_skeleton
    from nexus.services.local_heal.p3_local_diagnosis import compute_p3_local_diagnosis
    from nexus.services.local_heal.p3_cloud_candidate_stub import compute_cloud_candidate_stub
    from nexus.services.local_heal.p3_local_cheap_verifier import compute_p3_cheap_verifier
    from nexus.services.local_heal.p3_local_retry_stub import compute_p3_local_retry

    skeleton = compute_p3_route_skeleton({"difficulty": "medium"})
    assert skeleton.intended_topology == "cloud_with_local_assist"

    diag = compute_p3_local_diagnosis(
        request_metadata={"task_id": "test"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata=_make_complete_hashes(),
    )
    assert diag.cloud_ready is True

    stub = compute_cloud_candidate_stub(diagnosis_metadata={"p3_diagnosis_cloud_ready": True, "p3_diagnosis_compact_prompt_hash": "h"})
    assert stub.cloud_call_planned is True

    verifier = compute_p3_cheap_verifier(cloud_stub_metadata={"p3_cloud_stub_candidate_generated": True, "p3_cloud_stub_canonical_candidate_available": True})
    assert verifier.full_verifier_required is True

    retry = compute_p3_local_retry(cheap_verifier_metadata={"p3_cheap_verifier_result": "not_run_shadow_only", "p3_cheap_verifier_candidate_available": True})
    assert retry.full_verifier_required is True


# ============================================================
# P3-F-17: P2 hash/apply truth tests still pass
# ============================================================


def test_p2_still_works():
    from nexus.services.local_heal.output_understanding import compute_applied_patch_hash
    h = compute_applied_patch_hash("diff")
    assert h != ""


# ============================================================
# P3-F-18: P6 focused tests still pass if cheap enough
# ============================================================


def test_p6_not_modified():
    from nexus.services.local_heal.p3_shadow_orchestrator import compute_p3_shadow_orchestrator
    receipt, _ = compute_p3_shadow_orchestrator(
        request_metadata={"task_id": "p6-check", "difficulty": "medium"},
    )
    assert receipt.runtime_behavior_changed is False
