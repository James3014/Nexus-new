from __future__ import annotations

from scripts.ops.build_zero_trust_v2_behavior_runner_matrix import build_zero_trust_v2_behavior_runner_matrix
from scripts.ops.build_zero_trust_v2_m13_m19_completion import build_zero_trust_v2_m13_m19_completion


def test_behavior_runner_matrix_blocks_candidates_without_fresh_task_ref() -> None:
    result = build_zero_trust_v2_behavior_runner_matrix(
        backlog={
            "items": [
                {"capability_id": "codeintel", "skill_id": "code-skill", "priority": "P0"},
                {"capability_id": "xray", "skill_id": "xray-skill", "priority": "P1"},
            ]
        }
    )

    assert result["summary"]["candidate_count"] == 2
    assert result["summary"]["ready_for_physical_behavior_run_count"] == 0
    assert result["summary"]["blocked_count"] == 2
    assert all(item["hook_status"] == "BLOCKED" for item in result["adapters"])


def test_m13_m19_completion_keeps_unification_false_without_receipts() -> None:
    result = build_zero_trust_v2_m13_m19_completion(
        runner_matrix={
            "summary": {
                "candidate_count": 2,
                "p0_count": 1,
                "p1_count": 1,
                "p2_count": 0,
                "ready_for_physical_behavior_run_count": 0,
                "blocked_count": 2,
            }
        },
        m12_verdict={"summary": {"capability_count": 34}},
    )

    assert result["summary"]["m13_capability_ab_runner_adapter_complete"] is True
    assert result["summary"]["m19_v1_promotion_shutdown_boundary_complete"] is True
    assert result["summary"]["v2_unification_complete"] is False
    assert result["summary"]["runtime_mutation_allowed"] is False
