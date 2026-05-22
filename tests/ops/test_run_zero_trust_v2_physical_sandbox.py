from __future__ import annotations

from scripts.ops.run_zero_trust_v2_physical_sandbox import run_zero_trust_v2_physical_sandbox_matrix


def _row(arm_type: str) -> dict:
    return {
        "row_id": f"row-{arm_type}",
        "capability_id": "codeintel",
        "skill_id": "code-skill",
        "source_skill_id": "code-skill",
        "arm_type": arm_type,
        "security_contract_version": "v2",
        "promotion_credit_source": "v2_only",
    }


def test_zero_trust_v2_physical_sandbox_matrix_is_runtime_non_mutating() -> None:
    result = run_zero_trust_v2_physical_sandbox_matrix(
        replay_matrix={"rows": [_row("capability_only_v2"), _row("wrong_or_quarantined_skill_v2")]},
        command=["/bin/echo", "ok"],
        signing_secret="secret",
        limit=2,
    )

    assert result["status"] == "PASS"
    assert result["summary"]["executed_row_count"] == 2
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["summary"]["automatic_apply_allowed"] is False
    assert result["summary"]["public_benchmark_allowed"] is False
    assert result["summary"]["probe_only"] is True
    assert result["summary"]["execution_status_counts"] == {"BASELINE_ONLY": 1, "BLOCKED_BY_POLICY": 1}
