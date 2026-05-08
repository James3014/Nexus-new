from __future__ import annotations

from scripts.bench.refine_route_cost_policy_from_runs import refine_policy


def test_refine_route_cost_policy_keeps_only_verified_cost_improvements():
    policy = {
        "schema_version": "nexus_promoted_route_cost_policy.v1",
        "candidate_cap_overrides": {"kept": 1, "failed": 1, "slower": 1, "token_regressed": 1},
        "lite_route_tasks": ["kept", "slower"],
    }
    baseline_rows = {
        "kept": {"semantic_status": "VERIFIED", "wall_duration_sec": 10, "total_tokens": 100},
        "failed": {"semantic_status": "VERIFIED", "wall_duration_sec": 10, "total_tokens": 100},
        "slower": {"semantic_status": "VERIFIED", "wall_duration_sec": 10, "total_tokens": 100},
        "token_regressed": {"semantic_status": "VERIFIED", "wall_duration_sec": 10, "total_tokens": 100},
    }
    candidate_rows = {
        "kept": {"semantic_status": "VERIFIED", "wall_duration_sec": 8, "total_tokens": 90},
        "failed": {"semantic_status": "UNVERIFIED", "wall_duration_sec": 8, "total_tokens": 90},
        "slower": {"semantic_status": "VERIFIED", "wall_duration_sec": 12, "total_tokens": 90},
        "token_regressed": {"semantic_status": "VERIFIED", "wall_duration_sec": 8, "total_tokens": 110},
    }

    refined = refine_policy(baseline_rows=baseline_rows, candidate_rows=candidate_rows, policy=policy)

    assert refined["candidate_cap_overrides"] == {"kept": 1}
    assert refined["lite_route_tasks"] == ["kept"]
    assert refined["refinement"]["rejected_task_reasons"] == {
        "failed": "verified_delivery_not_preserved",
        "slower": "cost_not_improved",
        "token_regressed": "cost_not_improved",
    }
