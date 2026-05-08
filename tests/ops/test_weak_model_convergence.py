from scripts.ops.weak_model_convergence import (
    GateThresholds,
    build_feature_policy_candidate,
    build_holdout_plan,
    build_report,
)


def test_build_report_blocks_costly_skip_baseline_candidate() -> None:
    cost_truth = {
        "reference_model": "gpt55_bare",
        "weak_model_name": "flash_skip_baseline",
        "rows": [
            {
                "name": "gpt55_bare",
                "verified": 3,
                "eligible": 4,
                "verified_rate": 0.75,
                "vs_reference_tokens_ratio": 1.0,
            },
            {
                "name": "flash_skip_baseline",
                "verified": 4,
                "eligible": 4,
                "verified_rate": 1.0,
                "vs_reference_tokens_ratio": 3.1,
            },
        ],
        "weak_model_decision": {"weak_vs_reference_wall_ratio": 4.4},
    }
    failed_paths: list[str] = []

    report = build_report(cost_truth, None, failed_paths)

    assert report["gate"]["same_or_better_quality"] is True
    assert report["gate"]["launchable"] is False
    assert "token_cost_above_launch_gate" in report["gate"]["blockers"]
    assert "wall_time_above_launch_gate" in report["gate"]["blockers"]
    assert "best_path_requires_non_default_skip_llm_baseline" in report["gate"]["blockers"]
    assert "holdout_validation_missing" in report["gate"]["blockers"]
    assert report["feature_policy_candidate"]["runtime_match_uses_task_id"] is False


def test_build_report_passes_default_candidate_inside_cost_gate() -> None:
    cost_truth = {
        "reference_model": "gpt55_bare",
        "weak_model_name": "flash_candidate",
        "rows": [
            {
                "name": "gpt55_bare",
                "verified": 3,
                "eligible": 4,
                "verified_rate": 0.75,
                "vs_reference_tokens_ratio": 1.0,
            },
            {
                "name": "flash_candidate",
                "verified": 4,
                "eligible": 4,
                "verified_rate": 1.0,
                "vs_reference_tokens_ratio": 1.8,
            },
        ],
        "weak_model_decision": {"weak_vs_reference_wall_ratio": 2.0},
    }

    report = build_report(
        cost_truth,
        {"holdout_validated": True, "rows": []},
        [],
        GateThresholds(max_token_ratio=2.0, max_wall_ratio=2.5),
    )

    assert report["gate"]["launchable"] is True
    assert report["p11_p19_status"]["p40_closure_decision"] == "launchable_candidate"


def test_feature_policy_candidate_uses_task_ids_as_evidence_only() -> None:
    policy = build_feature_policy_candidate(
        [
            {
                "task_id": "task-a",
                "student_bare_verified": True,
                "recommendation": "slim_student_runtime_path",
                "student_high_cost_selected": ["research"],
            },
            {
                "task_id": "task-b",
                "student_bare_verified": False,
                "recommendation": "nexus_required_but_student_runtime_too_heavy",
                "student_high_cost_selected": [],
            },
        ]
    )

    assert policy["runtime_match_uses_task_id"] is False
    assert policy["task_ids_are_evidence_only"] == ["task-a", "task-b"]
    rule_names = {rule["name"] for rule in policy["rules"]}
    assert {"bare_verified_lite_route", "nexus_required_standard_route", "high_cost_research_cap"} <= rule_names
    for rule in policy["rules"]:
        assert "task_id" not in rule["match"]


def test_holdout_plan_excludes_tuning_tasks_without_task_id_runtime_match() -> None:
    plan = build_holdout_plan(
        task_manifest={
            "tasks": [
                {"id": "tune-a"},
                {"id": "holdout-a"},
                {"id": "tune-b"},
                {"id": "holdout-b"},
                {"id": "holdout-c"},
            ]
        },
        excluded_task_ids={"tune-a", "tune-b"},
        max_tasks=2,
    )

    assert plan["runtime_match_uses_task_id"] is False
    assert plan["excluded_task_ids"] == ["tune-a", "tune-b"]
    assert plan["task_ids"] == ["holdout-a", "holdout-b"]
    assert plan["required_before_promotion"] is True
