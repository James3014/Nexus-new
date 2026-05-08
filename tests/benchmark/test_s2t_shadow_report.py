from __future__ import annotations

from scripts.bench.s2t_shadow_report import (
    build_promoted_s2t_policy,
    build_s2t_shadow_report,
    build_s2t_trace_event,
)


def test_s2t_trace_event_marks_expensive_verified_self_heal_as_strict():
    event = build_s2t_trace_event(
        {
            "mode": "with_nexus",
            "task_id": "task-a",
            "trial_index": 1,
            "task_type": "public_feature",
            "fixture_kind": "fixture",
            "model_name": "gemini-3-flash-preview",
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "run_eligible": True,
            "route_risk_score": 35,
            "route_recommended_flow": "baseline",
            "chosen_flow": "hyper_sprint",
            "strategy_path": "hyper_direct_forced",
            "route_decision_schema_version": "nexus_route_decision_v1",
            "capability_plan_selected": ["artifact_gate", "claim_gate", "research"],
            "nexus_winner_source": "llm_self_heal",
            "model_calls": 2,
            "total_tokens": 90000,
            "wall_duration_sec": 80.0,
            "capability_claim_verified": True,
        }
    )

    assert event["schema"] == "nexus_s2t_trace_event_v1"
    assert event["selector_shadow"]["profile"] == "strict"
    assert event["selector_shadow"]["training_eligible"] is True
    assert event["cost"]["token_efficiency"] == "verified_but_expensive"
    assert event["candidate"]["high_cost_selected"] == ["research"]


def test_s2t_shadow_report_keeps_shadow_only_promotion_boundary():
    report = build_s2t_shadow_report(
        [
            {
                "mode": "with_nexus",
                "task_id": "task-a",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "model_calls": 2,
                "total_tokens": 90000,
                "nexus_winner_source": "llm_self_heal",
                "run_eligible": True,
            },
            {
                "mode": "without_nexus",
                "task_id": "task-a",
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "model_calls": 1,
                "total_tokens": 40000,
                "run_eligible": True,
            },
        ]
    )

    assert report["schema"] == "nexus_s2t_shadow_report_v1"
    assert report["scope"] == "shadow_only_no_runtime_decision_change"
    assert report["summary"]["with_nexus_rows"] == 1
    assert report["summary"]["selector_profile_counts"] == {"strict": 1}
    assert report["summary"]["self_heal_win_task_ids"] == ["task-a"]
    assert report["promotion_gate"]["requires_before_after_ab"] is True


def test_promoted_s2t_policy_stays_draft_until_before_after_ab():
    report = build_s2t_shadow_report(
        [
            {
                "mode": "with_nexus",
                "task_id": "task-a",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "model_calls": 2,
                "total_tokens": 90000,
                "nexus_winner_source": "llm_self_heal",
                "capability_plan_selected": ["claim_gate", "research"],
                "run_eligible": True,
            },
            {
                "mode": "with_nexus",
                "task_id": "task-b",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "model_calls": 1,
                "total_tokens": 30000,
                "run_eligible": True,
            },
        ]
    )

    policy = build_promoted_s2t_policy(report)

    assert policy["schema"] == "nexus_promoted_s2t_policy_draft_v1"
    assert policy["status"] == "DRAFT_SHADOW_ONLY"
    assert policy["promotion_requirements"]["same_model_before_after_ab"] is True
    assert policy["promotion_requirements"]["defensive_run_required"] is True
    assert policy["task_rules"]["task-a"]["recommended_action"] == "keep_strict_repair_selector"
    assert policy["task_rules"]["task-b"]["recommended_action"] == "prefer_lite_or_standard"
