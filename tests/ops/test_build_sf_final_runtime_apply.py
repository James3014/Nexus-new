from __future__ import annotations

from scripts.ops.build_sf_final_runtime_apply import build_sf_final_runtime_apply


def _comparison(capability: str, current: str, candidate: str, token_delta: int, wall_delta: float) -> dict:
    return {
        "capability": capability,
        "current_skill_id": current,
        "candidate_skill_id": candidate,
        "verdict": "REPLACE_PRIMARY_LIVE_APPROVED",
        "candidate": {
            "status": "PASS",
            "delivery_status": "SUCCESS",
            "receipt_chain_pass": True,
            "trust_mismatch": False,
            "skill_mount_contract_status": "PASS",
            "infra_invalid_reason": "",
            "evidence_path": f"evidence/{candidate}.json",
            "receipt_path": f"receipt/{candidate}",
        },
        "delta": {"token_delta": token_delta, "wall_delta": wall_delta},
    }


def _status(skill_id: str, capability: str) -> dict:
    return _status_with_skill_status(skill_id, capability, "nexus_curated_candidate")


def _status_with_skill_status(skill_id: str, capability: str, skill_status: str) -> dict:
    return {
        "name": skill_id,
        "path": f"/repo/.agents/skills/{skill_id}/SKILL.md",
        "root": "test",
        "skill_status": skill_status,
        "test_level": "test",
        "action": "ablation_only_compare",
        "capability_mount": capability,
    }


def test_sf_final_runtime_apply_selects_best_clean_replacement_and_keeps_rest() -> None:
    result = build_sf_final_runtime_apply(
        current_overlay={
            "status": "PASS",
            "primary_skill_by_capability": {"repair_loop": "old-repair", "codeintel": "old-code"},
        },
        live_report={
            "summary": {"expected_candidate_count": 2, "comparison_count": 2, "pending_candidate_count": 0},
            "comparisons": [
                _comparison("repair_loop", "old-repair", "new-repair-a", -5, -10.0),
                _comparison("repair_loop", "old-repair", "new-repair-b", -10, -1.0),
            ],
        },
        status_reports=[
            {"skills": [_status("new-repair-a", "repair_loop"), _status("new-repair-b", "repair_loop")]},
            {"skills": [_status("old-code", "codeintel")]},
        ],
    )

    assert result["decision"]["status"] == "PASS"
    assert result["decision"]["summary"]["applied_replacement_count"] == 1
    assert result["overlay"]["primary_skill_by_capability"] == {
        "codeintel": "old-code",
        "repair_loop": "new-repair-b",
    }
    assert result["skill_status"]["summary"]["skill_count"] == 2
    applied = result["decision"]["applied_primary"][0]
    assert applied["selection_rule"] == "min_token_delta_then_wall_delta_among_clean_live_approved"


def test_sf_final_runtime_apply_blocks_missing_status() -> None:
    result = build_sf_final_runtime_apply(
        current_overlay={"status": "PASS", "primary_skill_by_capability": {"repair_loop": "old-repair"}},
        live_report={
            "summary": {"expected_candidate_count": 1, "comparison_count": 1, "pending_candidate_count": 0},
            "comparisons": [_comparison("repair_loop", "old-repair", "new-repair", -5, -1.0)],
        },
        status_reports=[{"skills": []}],
    )

    assert result["decision"]["status"] == "RETURN"
    assert result["overlay"]["runtime_update_allowed"] is False
    assert "repair_loop:new-repair:missing_skill_status" in result["decision"]["blockers"]


def test_sf_final_runtime_apply_blocks_same_capability_reject_conflict() -> None:
    result = build_sf_final_runtime_apply(
        current_overlay={"status": "PASS", "primary_skill_by_capability": {"repair_loop": "old-repair"}},
        live_report={
            "summary": {"expected_candidate_count": 1, "comparison_count": 1, "pending_candidate_count": 0},
            "comparisons": [_comparison("repair_loop", "old-repair", "new-repair", -5, -1.0)],
        },
        status_reports=[{"skills": [_status("new-repair", "repair_loop")]}],
        catalog_verdict_report={
            "skill_verdicts": [
                {
                    "skill_id": "new-repair",
                    "capability": "repair_loop",
                    "runtime_eligible": False,
                    "verdict": "reject",
                }
            ]
        },
    )

    assert result["decision"]["status"] == "RETURN"
    assert result["overlay"]["runtime_update_allowed"] is False
    assert "repair_loop:new-repair:same_capability_reject_conflict" in result["decision"]["blockers"]


def test_sf_final_runtime_apply_warns_cross_capability_reject_conflict() -> None:
    result = build_sf_final_runtime_apply(
        current_overlay={"status": "PASS", "primary_skill_by_capability": {"research_control_plane": "old-research"}},
        live_report={
            "summary": {"expected_candidate_count": 1, "comparison_count": 1, "pending_candidate_count": 0},
            "comparisons": [_comparison("research_control_plane", "old-research", "browserbase-fetch", -5, -1.0)],
        },
        status_reports=[{"skills": [_status("browserbase-fetch", "research_control_plane")]}],
        catalog_verdict_report={
            "skill_verdicts": [
                {
                    "skill_id": "browserbase-fetch",
                    "capability": "xray",
                    "runtime_eligible": False,
                    "verdict": "reject",
                }
            ]
        },
    )

    assert result["decision"]["status"] == "PASS"
    assert result["decision"]["reject_conflict_warnings"] == [
        {
            "capability_id": "research_control_plane",
            "skill_id": "browserbase-fetch",
            "reject_capability": "xray",
            "reject_verdict": "reject",
            "reject_runtime_eligible": False,
            "reason": "cross_capability_reject_conflict",
        }
    ]


def test_sf_final_runtime_apply_marks_external_reference_as_requiring_curation() -> None:
    result = build_sf_final_runtime_apply(
        current_overlay={"status": "PASS", "primary_skill_by_capability": {"research": "old-research"}},
        live_report={
            "summary": {"expected_candidate_count": 1, "comparison_count": 1, "pending_candidate_count": 0},
            "comparisons": [_comparison("research", "old-research", "external-research", -5, -1.0)],
        },
        status_reports=[{"skills": [_status_with_skill_status("external-research", "research", "external_reference_candidate")]}],
    )

    assert result["decision"]["status"] == "PASS"
    assert result["decision"]["summary"]["external_reference_applied_count"] == 1
    assert result["decision"]["summary"]["requires_curation_count"] == 1
    assert result["decision"]["summary"]["runtime_review_scope"] == "overlay_only"
    assert result["decision"]["applied_primary"][0]["requires_curation"] is True
    assert result["decision"]["applied_primary"][0]["runtime_review_scope"] == "overlay_only_requires_curation"
    assert result["overlay"]["requires_curation_count"] == 1
    assert result["skill_status"]["skills"][0]["requires_curation"] is True


def test_sf_final_runtime_apply_marks_overlay_as_v1_diagnostic_only() -> None:
    result = build_sf_final_runtime_apply(
        current_overlay={"status": "PASS", "primary_skill_by_capability": {"research": "old-research"}},
        live_report={
            "summary": {"expected_candidate_count": 1, "comparison_count": 1, "pending_candidate_count": 0},
            "comparisons": [_comparison("research", "old-research", "new-research", -5, -1.0)],
        },
        status_reports=[{"skills": [_status("new-research", "research")]}],
    )

    assert result["decision"]["status"] == "PASS"
    assert result["decision"]["summary"]["security_contract_version"] == "v1_diagnostic_only"
    assert result["decision"]["summary"]["promotion_credit_source"] == "none"
    assert result["decision"]["summary"]["v1_evidence_count"] == 1
    assert result["decision"]["summary"]["v2_evidence_count"] == 0
    assert result["decision"]["summary"]["v2_trust_mismatch_count"] == 0
    assert result["decision"]["summary"]["requires_sandbox_attestation"] is True
    assert result["decision"]["summary"]["sandbox_attestation_status"] == "missing_not_required_for_overlay_only"
    assert result["decision"]["summary"]["v2_promotion_eligible"] is False
    applied = result["decision"]["applied_primary"][0]
    assert applied["security_contract_version"] == "v1_diagnostic_only"
    assert applied["promotion_credit_source"] == "none"
    assert applied["v2_promotion_eligible"] is False
    assert result["skill_status"]["skills"][0]["v2_evidence_count"] == 0
