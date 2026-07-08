from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_route_skeleton import (
    P3RouteSkeleton,
    compute_p3_route_skeleton,
    p3_skeleton_to_dict,
    _classify_task_difficulty,
    _plan_topology,
)


# ============================================================
# P3-A-1: Easy task produces local_only shadow topology
# ============================================================


def test_easy_task_produces_local_only_topology():
    skeleton = compute_p3_route_skeleton({"difficulty": "easy"})
    assert skeleton.task_difficulty == "easy"
    assert skeleton.intended_topology == "local_only"
    assert skeleton.cloud_used is False
    assert skeleton.cloud_call_invoked is False
    assert skeleton.runtime_behavior_changed is False
    assert skeleton.hybrid_committee_planned is False


def test_easy_task_from_task_id():
    skeleton = compute_p3_route_skeleton({"task_id": "easy_task_001"})
    assert skeleton.task_difficulty == "easy"
    assert skeleton.intended_topology == "local_only"


# ============================================================
# P3-A-2: Medium task produces cloud_with_local_assist shadow topology
# ============================================================


def test_medium_task_produces_cloud_with_local_assist_topology():
    skeleton = compute_p3_route_skeleton({"difficulty": "medium"})
    assert skeleton.task_difficulty == "medium"
    assert skeleton.intended_topology == "cloud_with_local_assist"
    assert skeleton.local_diagnosis_planned is True
    assert skeleton.cloud_candidate_generation_planned is True
    assert skeleton.local_cheap_verifier_planned is True
    assert skeleton.local_retry_planned is True
    assert skeleton.hybrid_committee_planned is False
    assert skeleton.cloud_used is False
    assert skeleton.cloud_call_invoked is False
    assert skeleton.runtime_behavior_changed is False


def test_medium_task_from_signal_snapshot():
    skeleton = compute_p3_route_skeleton({
        "route_context": {
            "signal_snapshot": {"task_difficulty": "medium"}
        }
    })
    assert skeleton.task_difficulty == "medium"
    assert skeleton.intended_topology == "cloud_with_local_assist"


# ============================================================
# P3-A-3: Hard task produces cloud_with_local_assist with hybrid planned
# ============================================================


def test_hard_task_produces_cloud_with_local_assist_with_hybrid():
    skeleton = compute_p3_route_skeleton({"difficulty": "hard"})
    assert skeleton.task_difficulty == "hard"
    assert skeleton.intended_topology == "cloud_with_local_assist"
    assert skeleton.local_diagnosis_planned is True
    assert skeleton.cloud_candidate_generation_planned is True
    assert skeleton.local_cheap_verifier_planned is True
    assert skeleton.local_retry_planned is True
    assert skeleton.hybrid_committee_planned is True
    assert "stage5_hybrid_committee" in skeleton.assist_stages_activated
    assert skeleton.cloud_used is False
    assert skeleton.cloud_call_invoked is False
    assert skeleton.runtime_behavior_changed is False


def test_hard_task_from_task_id():
    skeleton = compute_p3_route_skeleton({"task_id": "hard_complex_task"})
    assert skeleton.task_difficulty == "hard"
    assert skeleton.hybrid_committee_planned is True


# ============================================================
# P3-A-4: Unknown difficulty defaults to medium shadow-only
# ============================================================


def test_unknown_difficulty_defaults_to_medium():
    skeleton = compute_p3_route_skeleton({})
    assert skeleton.task_difficulty == "medium"
    assert skeleton.intended_topology == "cloud_with_local_assist"
    assert "difficulty_unknown_default_medium_shadow_only" in skeleton.reason


def test_empty_metadata_defaults_to_medium():
    skeleton = compute_p3_route_skeleton({"task_id": "", "difficulty": ""})
    assert skeleton.task_difficulty == "medium"


# ============================================================
# P3-A-5: p3_cloud_call_invoked=false always
# ============================================================


def test_cloud_call_invoked_always_false():
    for diff in ("easy", "medium", "hard"):
        skeleton = compute_p3_route_skeleton({"difficulty": diff})
        assert skeleton.cloud_call_invoked is False


# ============================================================
# P3-A-6: p3_cloud_used=false always
# ============================================================


def test_cloud_used_always_false():
    for diff in ("easy", "medium", "hard"):
        skeleton = compute_p3_route_skeleton({"difficulty": diff})
        assert skeleton.cloud_used is False


# ============================================================
# P3-A-7: p3_runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    for diff in ("easy", "medium", "hard"):
        skeleton = compute_p3_route_skeleton({"difficulty": diff})
        assert skeleton.runtime_behavior_changed is False


# ============================================================
# P3-A-8: p3_public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    for diff in ("easy", "medium", "hard"):
        skeleton = compute_p3_route_skeleton({"difficulty": diff})
        assert skeleton.public_claim_allowed is False


# ============================================================
# P3-A-9: p3_claim_eligible=false for skeleton-only metadata
# ============================================================


def test_claim_eligible_always_false():
    for diff in ("easy", "medium", "hard"):
        skeleton = compute_p3_route_skeleton({"difficulty": diff})
        assert skeleton.claim_eligible is False


# ============================================================
# P3-A-10: Metadata is JSON serializable
# ============================================================


def test_metadata_is_json_serializable():
    for diff in ("easy", "medium", "hard"):
        skeleton = compute_p3_route_skeleton({"difficulty": diff})
        meta = p3_skeleton_to_dict(skeleton)
        serialized = json.dumps(meta)
        assert isinstance(serialized, str)
        deserialized = json.loads(serialized)
        assert deserialized["p3_task_difficulty"] == diff


# ============================================================
# P3-A-11: No P6 receipt fields are changed
# ============================================================


def test_no_p6_fields_in_skeleton():
    skeleton = compute_p3_route_skeleton({"difficulty": "medium"})
    meta = p3_skeleton_to_dict(skeleton)
    p6_fields = [
        "p6_quota_remaining",
        "p6_degradation_active",
        "p6_runtime_mutation_allowed",
    ]
    for field in p6_fields:
        assert field not in meta


# ============================================================
# P3-A-12: No P5 promotion fields are changed
# ============================================================


def test_no_p5_fields_in_skeleton():
    skeleton = compute_p3_route_skeleton({"difficulty": "medium"})
    meta = p3_skeleton_to_dict(skeleton)
    p5_fields = [
        "p5_diversity_selector_used",
        "p5_selection_strategy",
        "p5_promoted",
    ]
    for field in p5_fields:
        assert field not in meta


# ============================================================
# P3-A-13: Authority is always shadow_only
# ============================================================


def test_authority_always_shadow_only():
    for diff in ("easy", "medium", "hard"):
        skeleton = compute_p3_route_skeleton({"difficulty": diff})
        assert skeleton.authority == "shadow_only"


# ============================================================
# P3-A-14: Assist stages are correct for each difficulty
# ============================================================


def test_easy_task_no_assist_stages():
    skeleton = compute_p3_route_skeleton({"difficulty": "easy"})
    assert skeleton.assist_stages_activated == []


def test_medium_task_has_core_stages():
    skeleton = compute_p3_route_skeleton({"difficulty": "medium"})
    assert "stage1_local_diagnosis" in skeleton.assist_stages_activated
    assert "stage2_cloud_candidate_generation" in skeleton.assist_stages_activated
    assert "stage3_local_cheap_verifier" in skeleton.assist_stages_activated
    assert "stage4_local_retry" in skeleton.assist_stages_activated
    assert "stage5_hybrid_committee" not in skeleton.assist_stages_activated


def test_hard_task_has_all_stages():
    skeleton = compute_p3_route_skeleton({"difficulty": "hard"})
    assert "stage1_local_diagnosis" in skeleton.assist_stages_activated
    assert "stage2_cloud_candidate_generation" in skeleton.assist_stages_activated
    assert "stage3_local_cheap_verifier" in skeleton.assist_stages_activated
    assert "stage4_local_retry" in skeleton.assist_stages_activated
    assert "stage5_hybrid_committee" in skeleton.assist_stages_activated


# ============================================================
# P3-A-15: classify_task_difficulty edge cases
# ============================================================


def test_classify_explicit_easy():
    diff, reason = _classify_task_difficulty({"difficulty": "EASY"})
    assert diff == "easy"
    assert "explicit" in reason


def test_classify_explicit_hard():
    diff, reason = _classify_task_difficulty({"difficulty": "HARD"})
    assert diff == "hard"
    assert "explicit" in reason


def test_classify_invalid_difficulty_defaults():
    diff, reason = _classify_task_difficulty({"difficulty": "invalid"})
    assert diff == "medium"
    assert "unknown" in reason


def test_plan_topology_easy():
    topology, stages, reason = _plan_topology("easy")
    assert topology == "local_only"
    assert stages == []


def test_plan_topology_medium():
    topology, stages, reason = _plan_topology("medium")
    assert topology == "cloud_with_local_assist"
    assert "stage5_hybrid_committee" not in stages


def test_plan_topology_hard():
    topology, stages, reason = _plan_topology("hard")
    assert topology == "cloud_with_local_assist"
    assert "stage5_hybrid_committee" in stages
