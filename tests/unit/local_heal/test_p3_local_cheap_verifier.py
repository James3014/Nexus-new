from __future__ import annotations

import importlib.util


def _make_cloud_stub_with_candidate():
    return {
        "p3_cloud_stub_candidate_generated": True,
        "p3_cloud_stub_canonical_candidate_available": True,
        "p3_cloud_stub_candidate_raw_output_hash": "abc123",
        "p3_cloud_stub_blocked_reason": "",
    }


def _make_cloud_stub_without_candidate():
    return {
        "p3_cloud_stub_candidate_generated": False,
        "p3_cloud_stub_canonical_candidate_available": False,
        "p3_cloud_stub_candidate_raw_output_hash": "",
        "p3_cloud_stub_blocked_reason": "cloud_not_ready:missing_anchor",
    }


# ============================================================
# P3-D-1: Candidate available creates cheap_verifier_planned=true
# ============================================================


def test_candidate_available_plans_cheap_verifier() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-2: Missing candidate creates cheap_verifier_planned=false
# ============================================================


def test_missing_candidate_blocks_cheap_verifier() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-3: cheap_verifier_invoked=false always
# ============================================================


def test_cheap_verifier_invoked_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-4: full_verifier_required=true always
# ============================================================


def test_full_verifier_required_always_true() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-5: claim_gate_required=true always
# ============================================================


def test_claim_gate_required_always_true() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-6: solved_claim_allowed=false always
# ============================================================


def test_solved_claim_allowed_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-7: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-8: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-9: Metadata JSON serializable
# ============================================================


def test_metadata_json_serializable() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier") is None


# ============================================================
# P3-D-10: Existing P3-C tests still pass
# ============================================================


def test_p3_c_still_works() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_cloud_candidate_stub") is None


# ============================================================
# P3-D-11: Existing P2 hash/apply truth tests still pass
# ============================================================


def test_p2_still_works():
    from nexus.services.local_heal.output_understanding import compute_applied_patch_hash
    h = compute_applied_patch_hash("diff")
    assert h != ""
