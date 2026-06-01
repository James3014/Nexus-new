from nexus.research.architecture_scout import ArchitectureRefactorExecutor, DistantScoutPlanner


def test_distant_scout_planner_changes_family_after_plateau():
    plateau = {
        "detected": True,
        "family": "flow:retry_delay",
        "reason": "discard_streak_same_family_low_variance",
        "next_lane": "DISTANT_SCOUT",
    }

    out = DistantScoutPlanner().plan(
        task_desc="fix websocket timeout race",
        plateau=plateau,
        asi_ledger=[
            {"family": "flow:retry_delay", "rollback_reason": "timeout still races"},
            {"family": "flow:retry_delay", "rollback_reason": "timeout still races"},
        ],
    )

    assert out["schema"] == "nexus_distant_scout_plan_v1"
    assert out["status"] == "READY"
    assert out["forbidden_families"] == ["flow:retry_delay"]
    assert out["recommended_family"] != "flow:retry_delay"
    assert "verification_commands" in out
    assert out["architecture_actions"]
    assert out["target_boundary"] == "repair_timeout_policy"
    assert out["bounded_refactor"]["requires_rollback_plan"] is True
    assert out["rollback_plan"]["restore_points"]
    assert out["gate_passed"] is True


def test_distant_scout_planner_skips_without_plateau():
    out = DistantScoutPlanner().plan(task_desc="simple typo", plateau={"detected": False})

    assert out["status"] == "SKIPPED"
    assert out["reason"] == "plateau_not_detected"


def test_architecture_refactor_executor_blocks_files_outside_scout_boundary():
    plan = DistantScoutPlanner().plan(
        task_desc="fix websocket timeout race",
        plateau={"detected": True, "family": "flow:retry_delay"},
    )

    out = ArchitectureRefactorExecutor().prepare(
        plan=plan,
        requested_files=["nexus/app/research_flow_service.py", "nexus/core/orchestrator.py"],
    )

    assert out["schema"] == "nexus_architecture_refactor_execution_v1"
    assert out["status"] == "BLOCKED"
    assert out["out_of_scope_files"] == ["nexus/core/orchestrator.py"]
    assert "target_outside_bounded_refactor" in out["failures"]


def test_architecture_refactor_executor_accepts_bounded_scout_contract():
    plan = DistantScoutPlanner().plan(
        task_desc="fix websocket timeout race",
        plateau={"detected": True, "family": "flow:retry_delay"},
    )

    out = ArchitectureRefactorExecutor().prepare(
        plan=plan,
        requested_files=["nexus/app/research_flow_service.py"],
    )

    assert out["status"] == "READY"
    assert out["rollback_ready"] is True
    assert out["requires_new_test"] is True
