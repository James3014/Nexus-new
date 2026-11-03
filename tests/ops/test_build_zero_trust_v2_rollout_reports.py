from __future__ import annotations

from scripts.ops.build_zero_trust_v2_evidence_accumulation import build_zero_trust_v2_evidence_accumulation
from scripts.ops.build_zero_trust_v2_rollout_status import build_zero_trust_v2_rollout_status
from scripts.ops.build_zero_trust_v2_unification_plan import build_zero_trust_v2_unification_plan


def test_evidence_accumulation_blocks_materialization_only_rows() -> None:
    result = build_zero_trust_v2_evidence_accumulation(
        physical_evidence={
            "summary": {"materialization_only": True},
            "rows": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "source_skill_id": "code-skill",
                    "arm_type": "candidate_skill_v2",
                    "v2_evidence_count": 0,
                    "v2_trust_mismatch_count": 0,
                    "negative_control_blocked_count": 1,
                }
            ],
        }
    )

    assert result["summary"]["candidate_count"] == 1
    assert result["summary"]["ready_for_manual_apply_count"] == 0
    assert result["candidates"][0]["status"] == "BLOCKED"


def test_unification_plan_keeps_runtime_locked_without_ready_candidates() -> None:
    result = build_zero_trust_v2_unification_plan(accumulation={"candidates": []})

    assert result["summary"]["patch_plan_count"] == 0
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["blockers"] == ["no_v2_ready_candidates"]


def test_rollout_status_reports_v2_readiness_per_capability() -> None:
    result = build_zero_trust_v2_rollout_status(
        runtime_apply={"applied_primary": [{"capability_id": "codeintel"}], "kept_primary": [{"capability_id": "xray"}]},
        unification_plan={"patch_plan": [{"capability_id": "codeintel", "skill_id": "code-skill"}]},
    )

    assert result["summary"]["capability_count"] == 2
    assert result["summary"]["v2_default_ready_count"] == 1
    assert result["summary"]["unification_complete"] is False
