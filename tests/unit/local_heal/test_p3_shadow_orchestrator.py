from __future__ import annotations

import importlib.util


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


def test_orchestrator_composes_all_components() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-2: Easy task produces local_only shadow receipt
# ============================================================


def test_easy_task_produces_local_only() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-3: Medium task produces cloud_with_local_assist shadow receipt
# ============================================================


def test_medium_task_produces_cloud_with_local_assist() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-4: Hard task produces cloud_with_local_assist with hard-case noted
# ============================================================


def test_hard_task_produces_cloud_with_hybrid_noted() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-5: p3_assist_stages_invoked=[]
# ============================================================


def test_assist_stages_invoked_always_empty() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-6: p3_cloud_call_invoked=false
# ============================================================


def test_cloud_call_invoked_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-7: p3_local_model_call_invoked=false
# ============================================================


def test_local_model_call_invoked_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-8: p3_patch_apply_invoked=false
# ============================================================


def test_patch_apply_invoked_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-9: p3_full_verifier_required=true
# ============================================================


def test_full_verifier_required_always_true() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-10: p3_claim_gate_required=true
# ============================================================


def test_claim_gate_required_always_true() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-11: p3_runtime_behavior_changed=false
# ============================================================


def test_runtime_behavior_changed_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-12: p3_claim_eligible=false
# ============================================================


def test_claim_eligible_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-13: p3_public_claim_allowed=false
# ============================================================


def test_public_claim_allowed_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-14: p3_receipt_complete=true
# ============================================================


def test_receipt_complete_always_true() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-15: JSON serialization works
# ============================================================


def test_json_serializable() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None


# ============================================================
# P3-F-16: All previous P3 component tests still pass
# ============================================================


def test_p3_components_still_work() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_cloud_candidate_stub") is None
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


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


def test_p6_not_modified() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_shadow_orchestrator") is None
