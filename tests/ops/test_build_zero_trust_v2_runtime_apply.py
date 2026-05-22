from __future__ import annotations

from scripts.ops.build_zero_trust_v2_runtime_apply import (
    build_zero_trust_v2_runtime_apply_artifacts,
    build_zero_trust_v2_runtime_apply_plan,
)


def test_zero_trust_v2_runtime_apply_blocks_when_no_ready_candidates() -> None:
    result = build_zero_trust_v2_runtime_apply_plan(
        promotion_report={
            "candidates": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "status": "BLOCKED",
                }
            ]
        }
    )

    assert result["status"] == "PASS"
    assert result["summary"]["ready_for_manual_apply_count"] == 0
    assert result["summary"]["patch_plan_count"] == 0
    assert result["summary"]["runtime_update_allowed"] is False
    assert result["summary"]["automatic_apply_allowed"] is False
    assert result["summary"]["public_benchmark_allowed"] is False
    assert result["patch_plan"] == []
    assert result["blockers"] == ["no_ready_v2_candidates"]


def test_zero_trust_v2_runtime_apply_produces_manual_only_patch_plan() -> None:
    result = build_zero_trust_v2_runtime_apply_plan(
        promotion_report={
            "candidates": [
                {
                    "capability_id": "research_control_plane",
                    "skill_id": "browserbase-fetch",
                    "status": "READY_FOR_MANUAL_APPLY",
                }
            ]
        }
    )

    assert result["summary"]["ready_for_manual_apply_count"] == 1
    assert result["summary"]["patch_plan_count"] == 1
    assert result["summary"]["runtime_update_allowed"] is False
    assert result["summary"]["automatic_apply_allowed"] is False
    assert result["summary"]["manual_operator_ack_required"] is True
    assert result["summary"]["revert_plan_required"] is True
    patch = result["patch_plan"][0]
    assert patch["action"] == "manual_runtime_overlay_update"
    assert patch["requires_operator_ack"] is True
    assert patch["requires_revert_plan"] is True
    assert result["blockers"] == ["manual_operator_ack_missing"]


def test_zero_trust_v2_runtime_apply_artifacts_apply_clean_v2_default_overlay() -> None:
    candidates = [
        {
            "capability_id": f"cap-{index:02d}",
            "skill_id": f"skill-{index:02d}",
            "priority": "P0" if index < 7 else ("P1" if index < 11 else "P2"),
            "status": "READY_FOR_MANUAL_APPLY",
            "v2_behavior_evidence_count": 3,
            "failed_security_contract_rules": [],
        }
        for index in range(34)
    ]
    runs = [
        {
            "capability_id": candidate["capability_id"],
            "skill_id": candidate["skill_id"],
            "priority": candidate["priority"],
            "evidence_bundle": f"bundle-{candidate['capability_id']}-{run_index}.json",
            "clean_v2_receipt": True,
            "runtime_signed_receipt_verified": True,
            "eligible_behavior_rows": 1,
            "blockers": [],
        }
        for candidate in candidates
        for run_index in range(1, 4)
    ]

    result = build_zero_trust_v2_runtime_apply_artifacts(
        promotion_report={"candidates": candidates},
        m45_m52={
            "summary": {"m45_clean_v2_receipt_count": 102, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": runs,
        },
        manual_trial={"status": "PASS", "summary": {"manual_apply_trial_ready": True}},
        rollout_report={
            "status": "PASS",
            "summary": {
                "candidate_count": 34,
                "promoted_count": 34,
                "p0_rollout_complete": True,
                "p1_p2_rollout_complete": True,
            },
        },
        current_overlay={
            "status": "PASS",
            "primary_skill_by_capability": {
                candidate["capability_id"]: candidate["skill_id"] for candidate in candidates
            },
        },
        current_skill_status={
            "skills": [{"name": candidate["skill_id"], "skill_status": "nexus_curated_candidate"} for candidate in candidates]
        },
    )

    decision = result["decision"]
    overlay = result["overlay"]
    assert decision["status"] == "PASS"
    assert decision["summary"]["capability_count"] == 34
    assert decision["summary"]["v2_default_applied_count"] == 34
    assert decision["summary"]["runtime_update_allowed"] is True
    assert overlay["status"] == "PASS"
    assert overlay["promotion_credit_source"] == "v2_only"
    assert overlay["v2_evidence_count"] == 102
    assert result["skill_status"]["summary"]["skill_count"] == 34
