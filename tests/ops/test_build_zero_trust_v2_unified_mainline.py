from __future__ import annotations

from scripts.ops.build_zero_trust_v2_unified_mainline import build_zero_trust_v2_unified_mainline


def test_unified_mainline_blocks_on_unclean_canary_receipts() -> None:
    result = build_zero_trust_v2_unified_mainline(
        m45_m52={
            "summary": {"m45_clean_v2_receipt_count": 0, "m51_v2_ready_capability_count": 0},
            "m45_behavior_run_results": [
                {
                    "blockers": [
                        "missing_required_capability_receipts",
                        "missing_runtime_signed_v2_receipt",
                        "no_eligible_behavior_row",
                        "semantic_not_verified",
                    ]
                }
            ],
        }
    )

    assert result["status"] == "BLOCKED"
    assert result["summary"]["v2_unification_complete"] is False
    assert result["summary"]["runtime_mutation_allowed"] is False
    by_id = {item["milestone"]: item for item in result["milestones"]}
    assert by_id["M53"]["status"] == "BLOCKED"
    assert by_id["M54"]["status"] == "BLOCKED"
    assert by_id["M56"]["blockers"] == ["clean_v2_receipt_count_lt_3"]
    assert "missing_runtime_signed_v2_receipt" in result["root_blockers"]


def test_unified_mainline_stays_blocked_until_apply_and_smoke() -> None:
    result = build_zero_trust_v2_unified_mainline(
        m45_m52={
            "summary": {"m45_clean_v2_receipt_count": 3, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": [{"blockers": []}],
        }
    )

    assert result["status"] == "BLOCKED"
    assert result["summary"]["v2_unification_complete"] is False
    assert result["summary"]["runtime_mutation_allowed"] is False
    by_id = {item["milestone"]: item for item in result["milestones"]}
    assert by_id["M57"]["status"] == "BLOCKED"
    assert by_id["M63"]["status"] == "BLOCKED"


def test_unified_mainline_can_pass_after_apply_and_post_smoke() -> None:
    result = build_zero_trust_v2_unified_mainline(
        m45_m52={
            "summary": {"m45_clean_v2_receipt_count": 102, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": [{"blockers": []}],
        },
        manual_trial={"status": "PASS", "summary": {"manual_apply_trial_ready": True}},
        rollout={"status": "PASS", "summary": {"p0_rollout_complete": True, "p1_p2_rollout_complete": True}},
        runtime_apply={
            "status": "PASS",
            "summary": {"runtime_update_allowed": True, "v2_default_applied_count": 34},
        },
        post_apply_smoke={"status": "PASS", "summary": {"case_count": 34, "pass_count": 34}},
    )

    assert result["status"] == "PASS"
    assert result["summary"]["v2_unification_complete"] is True
    assert result["summary"]["runtime_mutation_allowed"] is True
    assert all(item["status"] == "PASS" for item in result["milestones"])
