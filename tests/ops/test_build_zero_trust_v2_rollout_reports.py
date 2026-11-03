from __future__ import annotations

from nexus.learning.zero_trust_v2_sandbox import (
    build_mock_sandbox_attestation,
    sandbox_attestation_signature,
)
from scripts.ops.build_zero_trust_v2_evidence_accumulation import (
    build_zero_trust_v2_evidence_accumulation,
)
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


_PROD_SECRET = "production-secret-for-accumulation-test"


def _signed_row(row_id: str, *, secret: str = _PROD_SECRET) -> dict:
    body = {
        **build_mock_sandbox_attestation(artifact_hash="artifact"),
        "sandbox_mode": "macos_sandbox",
    }
    body.pop("signature")
    return {
        "row_id": row_id,
        "capability_id": "codeintel",
        "skill_id": "code-skill",
        "source_skill_id": "code-skill",
        "arm_type": "candidate_skill_v2",
        "v2_evidence_count": 3,
        "v2_trust_mismatch_count": 0,
        "negative_control_blocked_count": 1,
        "sandbox_attestation": {**body, "signature": sandbox_attestation_signature(attestation_body=body, signing_secret=secret)},
    }


def _accumulate(row: dict, **kwargs) -> dict:
    return build_zero_trust_v2_evidence_accumulation(
        physical_evidence={"rows": [row]}, signing_secret=_PROD_SECRET, **kwargs
    )["candidates"][0]


def test_evidence_accumulation_counts_correctly_signed_production_row() -> None:
    candidate = _accumulate(_signed_row("ok"))

    assert candidate["status"] == "READY_FOR_MANUAL_APPLY"
    assert candidate["v2_evidence_count"] == 3


def test_evidence_accumulation_excludes_nonproduction_marked_row() -> None:
    candidate = _accumulate({**_signed_row("marked"), "nonproduction_secret": True})

    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_evidence_count"] == 0
    assert candidate["signature_rejected_row_count"] == 1


def test_evidence_accumulation_excludes_row_with_unverifiable_signature() -> None:
    row = _signed_row("tampered")
    row["sandbox_attestation"]["teardown_status"] = "PASS"
    row["sandbox_attestation"]["resource_limits"] = {"cpu": "changed"}

    candidate = _accumulate(row)

    assert candidate["status"] == "BLOCKED"
    assert candidate["signature_rejected_row_count"] == 1


def test_evidence_accumulation_without_secret_gives_no_credit() -> None:
    result = build_zero_trust_v2_evidence_accumulation(physical_evidence={"rows": [_signed_row("nosecret")]})

    assert result["summary"]["ready_for_manual_apply_count"] == 0


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
