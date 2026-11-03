from __future__ import annotations

from nexus.learning.zero_trust_v2_sandbox import sandbox_attestation_signature
from scripts.ops.build_zero_trust_v2_promotion_report import build_zero_trust_v2_promotion_report


def _signed_attestation() -> dict:
    body = {
        "issuer": "nexus.runner",
        "sandbox_mode": "macos_sandbox",
        "status": "PASS",
        "network_disabled": True,
        "workspace_isolated": True,
        "tmp_isolated": True,
        "teardown_status": "PASS",
    }
    signature = sandbox_attestation_signature(attestation_body=body, signing_secret="fake-secret-3249")
    return {**body, "signature": signature}


def _candidate_row(**overrides: object) -> dict:
    row = {
        "capability_id": "codeintel",
        "skill_id": "code-skill",
        "arm_type": "candidate_skill_v2",
        "security_contract_version": "v2",
        "promotion_credit_source": "v2_only",
        "v2_evidence_count": 0,
        "v2_trust_mismatch_count": 0,
        "risk_flags": ["requires_curation"],
    }
    row.update(overrides)
    return row


def test_zero_trust_v2_promotion_report_blocks_unexecuted_v2_rows() -> None:
    result = build_zero_trust_v2_promotion_report(replay_matrix={"rows": [_candidate_row()]})

    assert result["status"] == "PASS"
    assert result["summary"]["candidate_arm_count"] == 1
    assert result["summary"]["ready_for_manual_apply_count"] == 0
    assert result["summary"]["blocked_count"] == 1
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["summary"]["manual_apply_required"] is False
    candidate = result["candidates"][0]
    assert candidate["status"] == "BLOCKED"
    assert "insufficient_v2_evidence" in candidate["reasons"]
    assert "missing_runtime_signed_receipt" in candidate["reasons"]


def test_zero_trust_v2_promotion_report_accepts_only_complete_v2_evidence() -> None:
    result = build_zero_trust_v2_promotion_report(
        replay_matrix={
            "rows": [
                _candidate_row(
                    v2_evidence_count=3,
                    negative_control_blocked_count=1,
                    receipt_provenance="runtime_signed",
                    receipt_signature="sig",
                    sandbox_attestation=_signed_attestation(),
                    baseline_sandwich={"baseline_delta_status": "CLEAN"},
                    cleanup_attestation={"teardown_status": "PASS"},
                )
            ]
        },
        signing_secret="fake-secret-3249",
    )

    assert result["summary"]["ready_for_manual_apply_count"] == 1
    assert result["summary"]["blocked_count"] == 0
    assert result["summary"]["manual_apply_required"] is True
    assert result["candidates"][0]["status"] == "READY_FOR_MANUAL_APPLY"


def test_zero_trust_v2_promotion_report_ignores_baseline_and_negative_control_arms() -> None:
    result = build_zero_trust_v2_promotion_report(
        replay_matrix={
            "rows": [
                _candidate_row(arm_type="capability_only_v2"),
                _candidate_row(arm_type="wrong_or_quarantined_skill_v2"),
                _candidate_row(arm_type="shadow_candidate_v2"),
            ]
        }
    )

    assert result["summary"]["candidate_arm_count"] == 1
    assert result["candidates"][0]["arm_type"] == "shadow_candidate_v2"
