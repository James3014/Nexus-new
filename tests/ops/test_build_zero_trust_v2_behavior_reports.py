from __future__ import annotations

from scripts.ops.build_zero_trust_v2_behavior_evidence import build_zero_trust_v2_behavior_evidence
from scripts.ops.build_zero_trust_v2_behavior_promotion_report import build_zero_trust_v2_behavior_promotion_report
from scripts.ops.build_zero_trust_v2_final_rollout_completion import build_zero_trust_v2_final_rollout_completion
from scripts.ops.build_zero_trust_v2_manual_trial import build_zero_trust_v2_manual_trial
from scripts.ops.build_zero_trust_v2_p0_rollout import build_zero_trust_v2_p0_rollout


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



def test_behavior_evidence_blocks_missing_bundle() -> None:
    result = build_zero_trust_v2_behavior_evidence(
        backlog={
            "items": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "priority": "P1",
                    "evidence_refs": ["/tmp/not-present-v2-evidence.json"],
                }
            ]
        }
    )

    candidate = result["candidates"][0]
    assert result["summary"]["candidate_count"] == 1
    assert candidate["status"] == "BLOCKED"
    assert "EVIDENCE_BUNDLE_NOT_FOUND" in candidate["failed_security_contract_rules"]


def test_behavior_evidence_imports_clean_m45_runtime_signed_receipts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")
    result = build_zero_trust_v2_behavior_evidence(
        backlog={"items": []},
        m45_m52={
            "m45_behavior_run_results": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "priority": "P1",
                    "run_id": f"run-{index}",
                    "evidence_bundle": _signed_bundle(tmp_path, f"run-{index}", "codeintel", "code-skill"),
                    "clean_v2_receipt": True,
                    "runtime_signed_receipt_verified": True,
                    "eligible_behavior_rows": 1,
                    "blockers": [],
                }
                for index in range(1, 4)
            ]
        },
    )

    assert result["summary"]["candidate_count"] == 1
    assert result["summary"]["v2_behavior_ready_count"] == 1
    assert result["summary"]["v2_behavior_evidence_count"] == 3
    candidate = result["candidates"][0]
    assert candidate["status"] == "PASS"
    assert candidate["v2_behavior_evidence_count"] == 3
    assert candidate["runtime_signed_receipt_verified_count"] == 3
    assert candidate["failed_security_contract_rules"] == []


def test_behavior_promotion_requires_v2_behavior_count() -> None:
    result = build_zero_trust_v2_behavior_promotion_report(
        behavior_evidence={
            "candidates": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "priority": "P1",
                    "v2_behavior_evidence_count": 0,
                    "failed_security_contract_rules": [],
                }
            ]
        }
    )

    assert result["summary"]["ready_for_manual_apply_count"] == 0
    assert result["candidates"][0]["status"] == "BLOCKED"
    assert "INSUFFICIENT_V2_BEHAVIOR_EVIDENCE" in result["candidates"][0]["failed_security_contract_rules"]


def test_final_rollout_completion_gives_every_capability_a_verdict() -> None:
    result = build_zero_trust_v2_final_rollout_completion(
        runtime_apply={"applied_primary": [{"capability_id": "codeintel"}], "kept_primary": [{"capability_id": "xray"}]},
        promotion_report={
            "candidates": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "status": "BLOCKED",
                    "failed_security_contract_rules": ["INSUFFICIENT_V2_BEHAVIOR_EVIDENCE"],
                }
            ]
        },
    )

    assert result["summary"]["capability_count"] == 2
    assert result["summary"]["m12_3_complete"] is True
    assert result["summary"]["v2_unification_complete"] is False
    verdicts = {item["capability_id"]: item["v2_verdict"] for item in result["capabilities"]}
    assert verdicts == {"codeintel": "STRUCTURED_BLOCKED", "xray": "NO_V2_CANDIDATE_READY"}


def test_final_rollout_completion_requires_v2_default_apply_for_unification() -> None:
    result = build_zero_trust_v2_final_rollout_completion(
        runtime_apply={
            "summary": {"v2_default_applied_count": 1},
            "applied_primary": [{"capability_id": "codeintel"}],
        },
        promotion_report={
            "candidates": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "status": "READY_FOR_MANUAL_APPLY",
                    "failed_security_contract_rules": [],
                }
            ]
        },
    )

    assert result["summary"]["v2_unification_complete"] is True
    assert result["summary"]["runtime_mutation_allowed"] is True


def test_manual_trial_blocks_without_ready_candidate() -> None:
    result = build_zero_trust_v2_manual_trial(promotion_report={"candidates": [{"status": "BLOCKED"}]})

    assert result["summary"]["trial_patch_plan_count"] == 0
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["blockers"] == ["no_v2_ready_candidate_for_manual_trial"]


def test_manual_trial_acknowledges_ready_candidates_for_apply() -> None:
    result = build_zero_trust_v2_manual_trial(
        promotion_report={
            "candidates": [
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "status": "READY_FOR_MANUAL_APPLY",
                }
            ]
        },
        operator_ack="active_goal",
    )

    assert result["status"] == "PASS"
    assert result["summary"]["manual_apply_trial_ready"] is True
    assert result["summary"]["runtime_mutation_allowed"] is True
    assert result["blockers"] == []


def test_p0_rollout_structures_blocked_candidates() -> None:
    result = build_zero_trust_v2_p0_rollout(
        promotion_report={
            "candidates": [
                {
                    "capability_id": "claim_gate",
                    "skill_id": "claim-skill",
                    "priority": "P0",
                    "status": "BLOCKED",
                    "failed_security_contract_rules": ["INSUFFICIENT_V2_BEHAVIOR_EVIDENCE"],
                }
            ]
        }
    )

    assert result["summary"]["p0_rollout_complete"] is False
    assert result["summary"]["p0_structured_blocked_count"] == 1
    assert result["items"][0]["p0_rollout_status"] == "STRUCTURED_BLOCKED"


def test_p0_rollout_promotes_p0_and_p1_p2_after_manual_ack() -> None:
    result = build_zero_trust_v2_p0_rollout(
        promotion_report={
            "candidates": [
                {
                    "capability_id": "claim_gate",
                    "skill_id": "claim-skill",
                    "priority": "P0",
                    "status": "READY_FOR_MANUAL_APPLY",
                    "failed_security_contract_rules": [],
                },
                {
                    "capability_id": "codeintel",
                    "skill_id": "code-skill",
                    "priority": "P1",
                    "status": "READY_FOR_MANUAL_APPLY",
                    "failed_security_contract_rules": [],
                },
            ]
        },
        manual_trial={"status": "PASS", "summary": {"manual_apply_trial_ready": True}},
    )

    assert result["summary"]["candidate_count"] == 2
    assert result["summary"]["promoted_count"] == 2
    assert result["summary"]["p0_rollout_complete"] is True
    assert result["summary"]["p1_p2_rollout_complete"] is True
    assert {item["rollout_status"] for item in result["items"]} == {"V2_PROMOTED_TO_DEFAULT_OVERLAY"}


def _m45_runs(tmp_path, *, capability_for_run=None) -> list[dict]:
    runs = []
    for index in range(1, 4):
        signed_capability = (capability_for_run or {}).get(index, "codeintel")
        runs.append(
            {
                "run_id": f"run-{index}",
                "capability_id": "codeintel",
                "skill_id": "code-skill",
                "priority": "P1",
                "evidence_bundle": _signed_bundle(tmp_path, f"run-{index}", signed_capability, "code-skill"),
                "clean_v2_receipt": True,
                "runtime_signed_receipt_verified": True,
                "eligible_behavior_rows": 1,
                "blockers": [],
            }
        )
    return runs


def test_behavior_evidence_reverifies_flags_instead_of_trusting_them(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")
    runs = _m45_runs(tmp_path)
    runs[2]["evidence_bundle"] = str(tmp_path / "missing.json")

    result = build_zero_trust_v2_behavior_evidence(backlog={"items": []}, m45_m52={"m45_behavior_run_results": runs})

    candidate = result["candidates"][0]
    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_behavior_evidence_count"] == 2
    assert candidate["runtime_signed_receipt_verified_count"] == 2


def test_behavior_evidence_refuses_receipt_signed_for_another_identity(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")
    runs = _m45_runs(tmp_path, capability_for_run={2: "other_capability"})

    result = build_zero_trust_v2_behavior_evidence(backlog={"items": []}, m45_m52={"m45_behavior_run_results": runs})

    candidate = result["candidates"][0]
    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_behavior_evidence_count"] == 2
    assert "runtime_signed_v2_receipt_identity_mismatch" in candidate["failed_security_contract_rules"]


def test_behavior_evidence_counts_a_copied_bundle_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")
    runs = _m45_runs(tmp_path)
    for item in runs:
        item["run_id"] = "run-1"
        item["evidence_bundle"] = runs[0]["evidence_bundle"]

    result = build_zero_trust_v2_behavior_evidence(backlog={"items": []}, m45_m52={"m45_behavior_run_results": runs})

    candidate = result["candidates"][0]
    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_behavior_evidence_count"] == 1
