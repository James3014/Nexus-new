from __future__ import annotations

from scripts.ops.build_zero_trust_v2_runtime_apply import (
    build_zero_trust_v2_runtime_apply_artifacts,
    build_zero_trust_v2_runtime_apply_plan,
)


def _signed_bundle(directory, run_id: str, capability_id: str, skill_id: str) -> str:
    """A bundle holding a receipt signed for (run_id, capability_id, skill_id) (#3366)."""
    import json

    from nexus.learning.zero_trust_v2_receipts import build_runtime_signed_receipt

    path = directory / f"{run_id}.json"
    receipt = build_runtime_signed_receipt(
        run_id=run_id,
        row_id=f"{run_id}:with_nexus",
        arm_id="candidate_skill_v2",
        capability_id=capability_id,
        skill_id=skill_id,
        artifact_hash=f"artifact-{run_id}",
        raw_observation={"row_counts": {"eligible_with_nexus": 1}},
        secret="test-secret",
    )
    path.write_text(
        json.dumps(
            {
                "row_counts": {"eligible_with_nexus": 1, "infra_invalid_with_nexus": 0},
                "rubric_contract": {"with_nexus": {"hard_fail_reasons": []}},
                "zero_trust_v2_runtime_receipt": receipt,
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def test_zero_trust_v2_runtime_apply_blocks_when_no_ready_candidates() -> None:
    result = build_zero_trust_v2_runtime_apply_plan(
        promotion_report={
            "candidates": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "status": "BLOCKED",
                }
            ]
        }
    )

    assert result["status"] == "PASS"
    assert result["summary"]["ready_for_manual_apply_count"] == 0
    assert result["summary"]["patch_plan_count"] == 0
    assert result["summary"]["runtime_update_allowed"] is False
    assert result["summary"]["automatic_apply_allowed"] is False
    assert result["summary"]["public_benchmark_allowed"] is False
    assert result["patch_plan"] == []
    assert result["blockers"] == ["no_ready_v2_candidates"]


def test_zero_trust_v2_runtime_apply_produces_manual_only_patch_plan() -> None:
    result = build_zero_trust_v2_runtime_apply_plan(
        promotion_report={
            "candidates": [
                {
                    "capability_id": "research_control_plane",
                    "skill_id": "browserbase-fetch",
                    "status": "READY_FOR_MANUAL_APPLY",
                }
            ]
        }
    )

    assert result["summary"]["ready_for_manual_apply_count"] == 1
    assert result["summary"]["patch_plan_count"] == 1
    assert result["summary"]["runtime_update_allowed"] is False
    assert result["summary"]["automatic_apply_allowed"] is False
    assert result["summary"]["manual_operator_ack_required"] is True
    assert result["summary"]["revert_plan_required"] is True
    patch = result["patch_plan"][0]
    assert patch["action"] == "manual_runtime_overlay_update"
    assert patch["requires_operator_ack"] is True
    assert patch["requires_revert_plan"] is True
    assert result["blockers"] == ["manual_operator_ack_missing"]


def test_zero_trust_v2_runtime_apply_artifacts_apply_clean_v2_default_overlay(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")
    candidates = [
        {
            "capability_id": f"cap-{index:02d}",
            "skill_id": f"skill-{index:02d}",
            "priority": "P0" if index < 7 else ("P1" if index < 11 else "P2"),
            "status": "READY_FOR_MANUAL_APPLY",
            "v2_behavior_evidence_count": 3,
            "failed_security_contract_rules": [],
        }
        for index in range(34)
    ]
    runs = [
        {
            "capability_id": candidate["capability_id"],
            "skill_id": candidate["skill_id"],
            "priority": candidate["priority"],
            "run_id": f"run-{candidate['capability_id']}-{run_index}",
            "evidence_bundle": _signed_bundle(
                tmp_path, f"run-{candidate['capability_id']}-{run_index}", candidate["capability_id"], candidate["skill_id"]
            ),
            "clean_v2_receipt": True,
            "runtime_signed_receipt_verified": True,
            "eligible_behavior_rows": 1,
            "blockers": [],
        }
        for candidate in candidates
        for run_index in range(1, 4)
    ]

    result = build_zero_trust_v2_runtime_apply_artifacts(
        promotion_report={"candidates": candidates},
        m45_m52={
            "summary": {"m45_clean_v2_receipt_count": 102, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": runs,
        },
        manual_trial={"status": "PASS", "summary": {"manual_apply_trial_ready": True}},
        rollout_report={
            "status": "PASS",
            "summary": {
                "candidate_count": 34,
                "promoted_count": 34,
                "p0_rollout_complete": True,
                "p1_p2_rollout_complete": True,
            },
        },
        current_overlay={
            "status": "PASS",
            "primary_skill_by_capability": {
                candidate["capability_id"]: candidate["skill_id"] for candidate in candidates
            },
        },
        current_skill_status={
            "skills": [{"name": candidate["skill_id"], "skill_status": "nexus_curated_candidate"} for candidate in candidates]
        },
    )

    decision = result["decision"]
    overlay = result["overlay"]
    assert decision["status"] == "PASS"
    assert decision["summary"]["capability_count"] == 34
    assert decision["summary"]["v2_default_applied_count"] == 34
    assert decision["summary"]["runtime_update_allowed"] is True
    assert overlay["status"] == "PASS"
    assert overlay["promotion_credit_source"] == "v2_only"
    assert overlay["v2_evidence_count"] == 102
    assert result["skill_status"]["summary"]["skill_count"] == 34


def _apply_inputs(tmp_path) -> dict:
    candidates = [
        {
            "capability_id": f"cap-{index:02d}",
            "skill_id": f"skill-{index:02d}",
            "priority": "P0",
            "status": "READY_FOR_MANUAL_APPLY",
            "v2_behavior_evidence_count": 3,
            "failed_security_contract_rules": [],
        }
        for index in range(34)
    ]
    runs = [
        {
            "run_id": f"run-{candidate['capability_id']}-{run_index}",
            "capability_id": candidate["capability_id"],
            "skill_id": candidate["skill_id"],
            "priority": candidate["priority"],
            "evidence_bundle": _signed_bundle(
                tmp_path, f"run-{candidate['capability_id']}-{run_index}", candidate["capability_id"], candidate["skill_id"]
            ),
            "clean_v2_receipt": True,
            "runtime_signed_receipt_verified": True,
            "eligible_behavior_rows": 1,
            "blockers": [],
        }
        for candidate in candidates
        for run_index in range(1, 4)
    ]
    return {
        "promotion_report": {"candidates": candidates},
        "m45_m52": {
            "summary": {"m45_clean_v2_receipt_count": 102, "m51_v2_ready_capability_count": 34},
            "m45_behavior_run_results": runs,
        },
        "manual_trial": {"status": "PASS", "summary": {"manual_apply_trial_ready": True}},
        "rollout_report": {
            "status": "PASS",
            "summary": {"candidate_count": 34, "promoted_count": 34, "p0_rollout_complete": True, "p1_p2_rollout_complete": True},
        },
        "current_overlay": {
            "status": "PASS",
            "primary_skill_by_capability": {item["capability_id"]: item["skill_id"] for item in candidates},
        },
        "current_skill_status": {"skills": [{"name": item["skill_id"]} for item in candidates]},
    }


def test_zero_trust_v2_runtime_apply_reverifies_inflated_m45_counts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")
    inputs = _apply_inputs(tmp_path)
    runs = inputs["m45_m52"]["m45_behavior_run_results"]
    # One capability's runs point at a missing bundle while the report keeps the flags and counts.
    for item in runs[:3]:
        item["evidence_bundle"] = str(tmp_path / "missing.json")
    inputs["m45_m52"]["summary"] = {"m45_clean_v2_receipt_count": 999, "m51_v2_ready_capability_count": 99}

    result = build_zero_trust_v2_runtime_apply_artifacts(**inputs)

    assert result["decision"]["status"] != "PASS"
    assert "clean_v2_receipt_count_lt_102" in result["decision"]["blockers"]
    assert "v2_ready_capability_count_lt_34" in result["decision"]["blockers"]
    assert "cap-00:skill-00:clean_v2_receipt_count_lt_3" in result["decision"]["blockers"]


def test_zero_trust_v2_runtime_apply_refuses_receipt_for_another_identity(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")
    inputs = _apply_inputs(tmp_path)
    runs = inputs["m45_m52"]["m45_behavior_run_results"]
    # cap-00's first run carries a bundle whose receipt was signed for cap-01's run.
    runs[0]["evidence_bundle"] = runs[3]["evidence_bundle"]

    result = build_zero_trust_v2_runtime_apply_artifacts(**inputs)

    assert result["decision"]["status"] != "PASS"
    assert "cap-00:skill-00:clean_v2_receipt_count_lt_3" in result["decision"]["blockers"]
