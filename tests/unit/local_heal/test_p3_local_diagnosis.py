from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_local_diagnosis import (
    P3LocalDiagnosis,
    compute_p3_local_diagnosis,
    p3_diagnosis_to_dict,
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


def _make_failure():
    return {
        "failure_class": "search_mismatch",
        "failure_summary": "SEARCH block not found in source",
        "verifier_summary": "not_run",
    }


# ============================================================
# P3-B-1: Builds compact diagnosis with complete anchor
# ============================================================


def test_builds_compact_diagnosis_with_complete_anchor():
    diag = compute_p3_local_diagnosis(
        request_metadata={"task_id": "task-001"},
        p3_skeleton={"p3_task_difficulty": "medium"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata=_make_complete_hashes(),
        failure_metadata=_make_failure(),
    )
    assert diag.enabled is True
    assert diag.authority == "shadow_only"
    assert diag.target_file == "foo.py"
    assert diag.target_symbol == "bar"
    assert diag.anchor_status == "available"
    assert diag.hash_chain_status == "complete"
    assert diag.cloud_ready is True


# ============================================================
# P3-B-2: Missing anchor produces cloud_ready=false
# ============================================================


def test_missing_anchor_produces_cloud_ready_false():
    diag = compute_p3_local_diagnosis(
        request_metadata={"task_id": "task-002"},
        anchor_metadata={},
        hash_chain_metadata=_make_complete_hashes(),
    )
    assert diag.anchor_status == "missing"
    assert diag.cloud_ready is False
    assert "missing_anchor" in diag.reason


# ============================================================
# P3-B-3: Incomplete hash chain produces cloud_ready=false
# ============================================================


def test_incomplete_hash_chain_produces_cloud_ready_false():
    diag = compute_p3_local_diagnosis(
        request_metadata={"task_id": "task-003"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata={"raw_output_hash": "h1", "normalized_patch_hash": "", "applied_patch_hash": ""},
    )
    assert diag.hash_chain_status == "incomplete"
    assert diag.cloud_ready is False
    assert "incomplete_hash_chain" in diag.reason


# ============================================================
# P3-B-4: compact_prompt_hash is deterministic
# ============================================================


def test_compact_prompt_hash_deterministic():
    meta = {"task_id": "task-004"}
    anchor = _make_complete_anchor()
    hashes = _make_complete_hashes()
    d1 = compute_p3_local_diagnosis(meta, anchor_metadata=anchor, hash_chain_metadata=hashes)
    d2 = compute_p3_local_diagnosis(meta, anchor_metadata=anchor, hash_chain_metadata=hashes)
    assert d1.compact_prompt_hash == d2.compact_prompt_hash
    assert d1.compact_prompt == d2.compact_prompt


# ============================================================
# P3-B-5: compact prompt does not include unrelated full file content
# ============================================================


def test_compact_prompt_no_full_file_content():
    diag = compute_p3_local_diagnosis(
        request_metadata={"task_id": "task-005"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata=_make_complete_hashes(),
    )
    assert len(diag.compact_prompt) <= 500
    assert "import " not in diag.compact_prompt or "File:" in diag.compact_prompt


# ============================================================
# P3-B-6: cloud_call_invoked=false always
# ============================================================


def test_cloud_call_invoked_always_false():
    for diff in ("easy", "medium", "hard"):
        diag = compute_p3_local_diagnosis(
            request_metadata={"task_id": f"task-{diff}"},
            p3_skeleton={"p3_task_difficulty": diff},
            anchor_metadata=_make_complete_anchor() if diff != "easy" else {},
            hash_chain_metadata=_make_complete_hashes() if diff != "easy" else {},
        )
        assert diag.cloud_call_invoked is False


# ============================================================
# P3-B-7: runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    for diff in ("easy", "medium", "hard"):
        diag = compute_p3_local_diagnosis(
            request_metadata={"task_id": f"task-{diff}"},
            p3_skeleton={"p3_task_difficulty": diff},
        )
        assert diag.runtime_behavior_changed is False


# ============================================================
# P3-B-8: claim_eligible=false
# ============================================================


def test_claim_eligible_always_false():
    diag = compute_p3_local_diagnosis(request_metadata={"task_id": "task-008"})
    assert diag.claim_eligible is False


# ============================================================
# P3-B-9: public_claim_allowed=false
# ============================================================


def test_public_claim_allowed_always_false():
    diag = compute_p3_local_diagnosis(request_metadata={"task_id": "task-009"})
    assert diag.public_claim_allowed is False


# ============================================================
# P3-B-10: JSON serialization works
# ============================================================


def test_json_serialization():
    diag = compute_p3_local_diagnosis(
        request_metadata={"task_id": "task-010"},
        anchor_metadata=_make_complete_anchor(),
        hash_chain_metadata=_make_complete_hashes(),
    )
    meta = p3_diagnosis_to_dict(diag)
    serialized = json.dumps(meta)
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["p3_diagnosis_cloud_ready"] is True


# ============================================================
# P3-B-11: Existing P3-A route skeleton tests still pass
# ============================================================


def test_p3_a_still_works():
    from nexus.services.local_heal.p3_route_skeleton import compute_p3_route_skeleton
    skeleton = compute_p3_route_skeleton({"difficulty": "medium"})
    assert skeleton.intended_topology == "cloud_with_local_assist"
    assert skeleton.authority == "shadow_only"


# ============================================================
# P3-B-12: Existing P2 hash/apply truth tests still pass
# ============================================================


def test_p2_hash_truth_still_works():
    from nexus.services.local_heal.output_understanding import (
        compute_applied_patch_hash,
        verify_hash_chain,
    )
    h = compute_applied_patch_hash("some diff")
    assert h != ""
    assert verify_hash_chain("h1", "h2", "h3") is True
