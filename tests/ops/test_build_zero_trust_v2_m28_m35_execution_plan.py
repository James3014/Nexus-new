from __future__ import annotations

from scripts.ops.build_zero_trust_v2_m28_m35_execution_plan import build_zero_trust_v2_m28_m35_execution_plan


def _adapter(capability: str, skill: str, priority: str = "P0") -> dict:
    return {
        "capability_id": capability,
        "skill_id": skill,
        "priority": priority,
        "status": "READY_FOR_PHYSICAL_BEHAVIOR_RUN",
        "command": [
            "uv",
            "run",
            "python",
            "scripts/bench/capability_ab_runner.py",
            "--output-dir",
            ".nexus/reports/zero_trust_v2_behavior",
            "--task-id-filter",
            f"ztv2-{capability}",
        ],
        "runner_env": {"NEXUS_VALUE_HIDDEN_VERIFIER": "1"},
        "task_ref": {"manifest": "tasks.json", "task_id": f"ztv2-{capability}"},
    }


def test_m28_m35_plan_selects_p0_canary_and_builds_three_runs() -> None:
    result = build_zero_trust_v2_m28_m35_execution_plan(
        runner_matrix={"adapters": [_adapter("claim_gate", "skill-a"), _adapter("sandbox_replay", "skill-b")]},
        m20_m27={"summary": {"m21_ready_for_physical_behavior_run_count": 19}},
    )

    assert result["summary"]["m28_selected_canary_count"] == 1
    assert result["selected_canary_candidate"]["capability_id"] == "sandbox_replay"
    assert result["m28_preflight_hook"]["hook_status"] == "READY_TO_RUN_PRECHECK"
    assert "--preflight-only" in result["m28_preflight_hook"]["command"]
    assert len(result["m29_three_run_plan"]) == 3
    assert result["m29_three_run_plan"][0]["runner_env"]["NEXUS_VALUE_HIDDEN_VERIFIER"] == "1"
    assert result["summary"]["m33_p0_ready_for_execution_count"] == 2
    assert result["summary"]["m34_p1_p2_ready_for_execution_count"] == 17
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["summary"]["m29_signed_behavior_executed_count"] == result["summary"]["m30_existing_receipt_bundle_count"]
    assert result["m35_v1_path_closure_gate"]["status"] == "BLOCKED"


def test_m28_m35_plan_blocks_without_ready_p0_candidate() -> None:
    result = build_zero_trust_v2_m28_m35_execution_plan(
        runner_matrix={"adapters": [{"priority": "P0", "status": "BLOCKED"}]},
        m20_m27={"summary": {"m21_ready_for_physical_behavior_run_count": 0}},
    )

    assert result["summary"]["m28_selected_canary_count"] == 0
    assert result["m28_preflight_hook"]["hook_status"] == "BLOCKED"
    assert result["summary"]["m29_signed_behavior_run_plan_count"] == 0
    assert result["summary"]["v2_unification_complete"] is False
