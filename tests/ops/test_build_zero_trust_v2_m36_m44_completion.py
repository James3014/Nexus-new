from __future__ import annotations

from scripts.ops.build_zero_trust_v2_m36_m44_completion import build_zero_trust_v2_m36_m44_completion


def _m28_m35() -> dict:
    return {
        "summary": {
            "m33_p0_ready_for_execution_count": 5,
            "m34_p1_p2_ready_for_execution_count": 14,
        },
        "selected_canary_candidate": {"capability_id": "policy_capability_gate", "skill_id": "browse"},
        "m29_three_run_plan": [
            {
                "run_index": 1,
                "command": ["uv", "run", "python", "scripts/bench/capability_ab_runner.py"],
                "expected_evidence_bundle": ".nexus/reports/ztv2/run-01/evidence_bundle.json",
            },
            {
                "run_index": 2,
                "command": ["uv", "run", "python", "scripts/bench/capability_ab_runner.py"],
                "expected_evidence_bundle": ".nexus/reports/ztv2/run-02/evidence_bundle.json",
            },
            {
                "run_index": 3,
                "command": ["uv", "run", "python", "scripts/bench/capability_ab_runner.py"],
                "expected_evidence_bundle": ".nexus/reports/ztv2/run-03/evidence_bundle.json",
            },
        ],
    }


def test_m36_m44_records_preflight_pass_without_unlocking_promotion() -> None:
    result = build_zero_trust_v2_m36_m44_completion(
        m28_m35=_m28_m35(),
        preflight={"status": "PASS", "failures": [], "warnings": ["worktree_dirty_recorded"]},
    )

    assert result["status"] == "PASS"
    assert result["summary"]["m36_preflight_status"] == "PASS"
    assert result["summary"]["m37_blocker_repair_complete"] is True
    assert result["summary"]["m38_signed_behavior_run_plan_count"] == 3
    assert result["summary"]["m39_clean_v2_receipt_count"] == 0
    assert result["summary"]["m42_p0_ready_for_execution_count"] == 5
    assert result["summary"]["m43_p1_p2_ready_for_execution_count"] == 14
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["summary"]["promotion_credit_allowed"] is False
    assert result["m38_signed_behavior_execution_gate"]["status"] == "READY_TO_RUN"
    assert result["m39_receipt_import_gate"]["status"] == "BLOCKED"
    assert result["m44_v1_path_closure_gate"]["status"] == "BLOCKED"


def test_m36_m44_blocks_execution_when_preflight_fails() -> None:
    result = build_zero_trust_v2_m36_m44_completion(
        m28_m35=_m28_m35(),
        preflight={"status": "FAIL", "failures": ["expected_capabilities_unknown:policy_capability_gate"], "warnings": []},
    )

    assert result["status"] == "BLOCKED"
    assert result["summary"]["m37_blocker_repair_complete"] is False
    assert result["m38_signed_behavior_execution_gate"]["status"] == "BLOCKED"
    assert "m36_preflight_not_passed" in result["m38_signed_behavior_execution_gate"]["blockers"]
    assert result["m37_blocker_repair_gate"]["blockers"] == ["expected_capabilities_unknown:policy_capability_gate"]
