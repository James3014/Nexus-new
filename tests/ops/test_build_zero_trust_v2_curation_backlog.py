from __future__ import annotations

from scripts.ops.build_zero_trust_v2_curation_backlog import build_zero_trust_v2_curation_backlog


def _applied(capability: str, skill_id: str, *, source_status: str = "external_reference_candidate") -> dict:
    return {
        "capability_id": capability,
        "previous_skill_id": f"old-{capability}",
        "skill_id": skill_id,
        "source_status": source_status,
        "runtime_review_scope": "overlay_only_requires_curation",
        "security_contract_version": "v1_diagnostic_only",
        "promotion_credit_source": "none",
        "v1_evidence_count": 1,
        "v2_evidence_count": 0,
        "v2_trust_mismatch_count": 0,
        "requires_sandbox_attestation": True,
        "sandbox_attestation_status": "missing_not_required_for_overlay_only",
        "v2_promotion_eligible": False,
        "requires_curation": True,
        "evidence_refs": [f"evidence/{skill_id}.json"],
        "receipt_path": f"receipt/{skill_id}",
    }


def test_zero_trust_v2_curation_backlog_marks_applied_replacements_pending() -> None:
    result = build_zero_trust_v2_curation_backlog(
        runtime_apply_decision={
            "summary": {
                "applied_replacement_count": 2,
                "kept_primary_count": 1,
                "runtime_update_allowed": True,
                "public_benchmark_allowed": False,
            },
            "applied_primary": [
                _applied("research_control_plane", "browserbase-fetch"),
                _applied("codeintel", "gstack-qa"),
            ],
            "kept_primary": [
                {
                    "capability_id": "artifact_gate",
                    "skill_id": "sf-systematic-artifact_gate-differential-review-461fbd0c",
                    "decision": "runtime_primary_kept",
                }
            ],
            "reject_conflict_warnings": [
                {
                    "capability_id": "research_control_plane",
                    "skill_id": "browserbase-fetch",
                    "reject_capability": "xray",
                    "reject_verdict": "reject",
                    "reject_runtime_eligible": False,
                    "reason": "cross_capability_reject_conflict",
                }
            ],
        }
    )

    assert result["status"] == "PASS"
    assert result["summary"]["candidate_count"] == 3
    assert result["summary"]["kept_primary_count"] == 1
    assert result["summary"]["kept_primary_v2_coverage_count"] == 1
    assert result["summary"]["requires_curation_count"] == 2
    assert result["summary"]["v2_ready_count"] == 0
    assert result["summary"]["promotion_credit_source"] == "none"
    assert result["summary"]["runtime_update_allowed"] is True
    assert result["summary"]["public_benchmark_allowed"] is False
    assert {item["curation_status"] for item in result["items"]} == {"PENDING"}
    assert {item["v2_promotion_eligible"] for item in result["items"]} == {False}
    by_capability = {item["capability_id"]: item for item in result["items"]}
    assert by_capability["artifact_gate"]["coverage_lane"] == "kept_primary_v2_coverage"
    assert by_capability["artifact_gate"]["current_runtime_scope"] == "kept_primary_requires_v2_coverage"


def test_zero_trust_v2_curation_backlog_preserves_cross_capability_warning() -> None:
    result = build_zero_trust_v2_curation_backlog(
        runtime_apply_decision={
            "summary": {"applied_replacement_count": 1},
            "applied_primary": [_applied("research_control_plane", "browserbase-fetch")],
            "reject_conflict_warnings": [
                {
                    "capability_id": "research_control_plane",
                    "skill_id": "browserbase-fetch",
                    "reject_capability": "xray",
                    "reject_verdict": "reject",
                    "reject_runtime_eligible": False,
                    "reason": "cross_capability_reject_conflict",
                }
            ],
        }
    )

    item = result["items"][0]
    assert item["skill_id"] == "browserbase-fetch"
    assert item["priority"] == "P0"
    assert "cross_capability_reject_conflict" in item["risk_flags"]
    assert "reject_conflict_review" in item["required_next_steps"]
    assert item["reject_conflict_warnings"][0]["reject_capability"] == "xray"


def test_zero_trust_v2_curation_backlog_prioritizes_core_and_security_capabilities() -> None:
    result = build_zero_trust_v2_curation_backlog(
        runtime_apply_decision={
            "summary": {"applied_replacement_count": 3},
            "applied_primary": [
                _applied("policy_capability_gate", "policy-skill"),
                _applied("repair_loop", "repair-skill"),
                _applied("external_productivity", "productivity-skill"),
            ],
        }
    )

    by_capability = {item["capability_id"]: item for item in result["items"]}
    assert by_capability["policy_capability_gate"]["priority"] == "P0"
    assert by_capability["repair_loop"]["priority"] == "P1"
    assert by_capability["external_productivity"]["priority"] == "P2"
    assert result["summary"]["priority_counts"] == {"P0": 1, "P1": 1, "P2": 1}
