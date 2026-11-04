from __future__ import annotations

from nexus.learning.zero_trust_v2_physical_runner import run_zero_trust_v2_physical_rows
from nexus.learning.zero_trust_v2_promotion import evaluate_zero_trust_v2_promotion_candidate
from nexus.learning.zero_trust_v2_receipts import build_runtime_signed_receipt
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


def _with_receipt(row: dict, kind: str, secret: str = _PROD_SECRET) -> dict:
    """The runtime-signed receipt the physical runner attaches (#3355)."""
    return {
        **row,
        **build_runtime_signed_receipt(
            run_id="run-1",
            row_id=row["row_id"],
            arm_id=row["arm_type"],
            capability_id=row["capability_id"],
            skill_id=row["skill_id"],
            source_skill_id=row["source_skill_id"],
            evidence_kind=kind,
            artifact_hash=(row.get("sandbox_attestation") or {}).get("artifact_hash", ""),
            raw_observation={},
            secret=secret,
        ),
    }


def _signed_row(row_id: str, *, secret: str = _PROD_SECRET, **over: object) -> dict:
    body = {
        **build_mock_sandbox_attestation(artifact_hash="artifact"),
        "sandbox_mode": "macos_sandbox",
    }
    body.pop("signature")
    row = {
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
    row = _with_receipt(row, "v2_evidence", secret)
    row.update(over)
    return row


def _negative_row(row_id: str, *, secret: str = _PROD_SECRET) -> dict:
    row = {
        "row_id": row_id,
        "capability_id": "codeintel",
        "skill_id": "wrong-skill",
        "source_skill_id": "code-skill",
        "arm_type": "wrong_or_quarantined_skill_v2",
        "v2_evidence_count": 0,
        "negative_control_blocked_count": 1,
    }
    return _with_receipt(row, "negative_control_block", secret)


def _accumulate_rows(rows: list[dict], **kwargs) -> dict:
    return build_zero_trust_v2_evidence_accumulation(
        physical_evidence={"rows": rows}, signing_secret=_PROD_SECRET, **kwargs
    )["candidates"][0]


def _accumulate(row: dict, **kwargs) -> dict:
    return build_zero_trust_v2_evidence_accumulation(
        physical_evidence={"rows": [row]}, signing_secret=_PROD_SECRET, **kwargs
    )["candidates"][0]


def test_evidence_accumulation_counts_correctly_signed_production_row() -> None:
    candidate = _accumulate_rows([_signed_row("ok"), _signed_row("ok-2"), _signed_row("ok-3"), _negative_row("neg")])

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


def test_3355_duplicate_signed_row_not_counted_twice() -> None:
    rows = [_signed_row("a"), _signed_row("a"), _signed_row("a"), _negative_row("neg")]

    candidate = _accumulate_rows(rows)

    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_evidence_count"] == 1
    assert candidate["duplicate_proof_count"] == 2


def test_3355_duplicate_negative_control_counts_once() -> None:
    rows = [_signed_row("a"), _signed_row("b"), _signed_row("c"), _negative_row("neg"), _negative_row("neg")]

    candidate = _accumulate_rows(rows)

    assert candidate["negative_control_blocked_count"] == 1
    assert candidate["duplicate_proof_count"] == 1


def test_3355_edited_count_columns_not_credited() -> None:
    rows = [_signed_row("a", v2_evidence_count=3, negative_control_blocked_count=1)]

    candidate = _accumulate_rows(rows)

    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_evidence_count"] == 1
    assert candidate["negative_control_blocked_count"] == 0
    assert candidate["unsigned_count_mismatch_row_refs"] == ["a"]


def test_3355_unsigned_negative_control_row_does_not_count() -> None:
    unsigned = {
        "row_id": "neg",
        "capability_id": "codeintel",
        "skill_id": "wrong-skill",
        "source_skill_id": "code-skill",
        "arm_type": "wrong_or_quarantined_skill_v2",
        "negative_control_blocked_count": 1,
    }

    candidate = _accumulate_rows([_signed_row("a"), _signed_row("b"), _signed_row("c"), unsigned])

    assert candidate["status"] == "BLOCKED"
    assert candidate["negative_control_blocked_count"] == 0
    assert candidate["rejected_row_refs"] == ["neg"]


def test_3355_negative_control_with_tampered_identity_does_not_count() -> None:
    for field, value in (("source_skill_id", "other-skill"), ("arm_type", "candidate_skill_v2"), ("row_id", "x")):
        negative = {**_negative_row("neg"), field: value}
        result = build_zero_trust_v2_evidence_accumulation(
            physical_evidence={"rows": [_signed_row("a"), _signed_row("b"), _signed_row("c"), negative]},
            signing_secret=_PROD_SECRET,
        )
        code_skill = next(c for c in result["candidates"] if c["skill_id"] == "code-skill")
        assert code_skill["status"] == "BLOCKED", field
        assert code_skill["negative_control_blocked_count"] == 0, field


def test_3355_receipt_hash_not_matching_inputs_is_rejected() -> None:
    row = _signed_row("a")
    row["receipt_signature_inputs"] = {**row["receipt_signature_inputs"], "row_id": "b"}
    row["row_id"] = "b"

    candidate = _accumulate_rows([row, _signed_row("c"), _signed_row("d"), _negative_row("neg")])

    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_evidence_count"] == 2
    assert candidate["rejected_row_refs"] == ["b"]


def test_3355_receipt_artifact_must_match_the_signed_attestation() -> None:
    row = _signed_row("a")
    other = _with_receipt({**row, "sandbox_attestation": {"artifact_hash": "other"}}, "v2_evidence")
    row = {**other, "sandbox_attestation": row["sandbox_attestation"]}

    candidate = _accumulate_rows([row, _signed_row("c"), _signed_row("d"), _negative_row("neg")])

    assert candidate["v2_evidence_count"] == 2
    assert candidate["rejected_row_refs"] == ["a"]


def _physical_probe(command, *, signing_secret, **_):
    attestation = {
        **build_mock_sandbox_attestation(artifact_hash="artifact"),
        "sandbox_mode": "macos_sandbox",
        "raw_observation": {"returncode": 0},
    }
    attestation.pop("signature")
    return {
        "status": "PASS",
        "promotion_eligible": True,
        "sandbox_attestation": {
            **attestation,
            "signature": sandbox_attestation_signature(attestation_body=attestation, signing_secret=signing_secret),
        },
    }


def _produced_rows() -> list[dict]:
    rows = [
        {
            "row_id": row_id,
            "capability_id": "codeintel",
            "skill_id": skill_id,
            "source_skill_id": "code-skill",
            "arm_type": arm_type,
        }
        for row_id, skill_id, arm_type in (
            ("cand-1", "code-skill", "candidate_skill_v2"),
            ("cand-2", "code-skill", "candidate_skill_v2"),
            ("cand-3", "code-skill", "candidate_skill_v2"),
            ("neg-1", "wrong-skill", "wrong_or_quarantined_skill_v2"),
        )
    ]
    return run_zero_trust_v2_physical_rows(
        rows,
        command=["/bin/true"],
        signing_secret=_PROD_SECRET,
        run_id="run-1",
        promotion_credit_allowed=True,
        sandbox_probe=_physical_probe,
    )


def test_3355_producer_to_accumulation_to_promotion_still_reaches_ready() -> None:
    produced = _produced_rows()

    candidate = _accumulate_rows(produced)

    assert candidate["status"] == "READY_FOR_MANUAL_APPLY"
    assert candidate["v2_evidence_count"] == 3
    assert candidate["negative_control_blocked_count"] == 1
    assert candidate["unsigned_count_mismatch_row_refs"] == []
    first = next(row for row in produced if row["row_id"] == "cand-1")
    verdict = evaluate_zero_trust_v2_promotion_candidate(first, min_v2_evidence_count=1, signing_secret=_PROD_SECRET)
    assert verdict["status"] == "READY_FOR_MANUAL_APPLY"


def test_3355_producer_signs_negative_control_identity() -> None:
    negative = next(row for row in _produced_rows() if row["row_id"] == "neg-1")

    inputs = negative["receipt_signature_inputs"]
    assert (inputs["row_id"], inputs["arm_id"], inputs["skill_id"], inputs["source_skill_id"], inputs["evidence_kind"]) == (
        "neg-1",
        "wrong_or_quarantined_skill_v2",
        "wrong-skill",
        "code-skill",
        "negative_control_block",
    )


def test_3355_promotion_evaluator_edited_counts_not_credited() -> None:
    row = _signed_row(
        "a",
        v2_evidence_count=3,
        negative_control_blocked_count=1,
        security_contract_version="v2",
        promotion_credit_source="v2_only",
        baseline_sandwich={"baseline_delta_status": "CLEAN"},
        cleanup_attestation={"teardown_status": "PASS"},
    )

    verdict = evaluate_zero_trust_v2_promotion_candidate(row, signing_secret=_PROD_SECRET)

    assert verdict["status"] != "READY_FOR_MANUAL_APPLY", verdict
    assert verdict["v2_evidence_count"] == 1


def _resigned(row: dict, run_id: str) -> dict:
    """The same row signed again under another round, as a later run would (#3362)."""
    return {
        **row,
        **build_runtime_signed_receipt(
            run_id=run_id,
            row_id=row["row_id"],
            arm_id=row["arm_type"],
            capability_id=row["capability_id"],
            skill_id=row["skill_id"],
            source_skill_id=row["source_skill_id"],
            evidence_kind="v2_evidence",
            artifact_hash=row["sandbox_attestation"]["artifact_hash"],
            raw_observation={},
            secret=_PROD_SECRET,
        ),
    }


def test_3362_same_row_signed_in_three_rounds_counts_once() -> None:
    first = _signed_row("a")
    rows = [first, _resigned(first, "run-2"), _resigned(first, "run-3"), _negative_row("neg")]
    assert len({row["receipt_signature"] for row in rows}) == 4

    candidate = _accumulate_rows(rows)

    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_evidence_count"] == 1
    assert candidate["duplicate_identity_count"] == 2
    assert candidate["duplicate_identity_row_refs"] == ["a", "a"]
    assert candidate["duplicate_proof_count"] == 0


def test_3362_distinct_rows_across_rounds_still_reach_ready() -> None:
    rows = [
        _signed_row("a"),
        _resigned(_signed_row("b"), "run-2"),
        _resigned(_signed_row("c"), "run-3"),
        _negative_row("neg"),
    ]

    candidate = _accumulate_rows(rows)

    assert candidate["status"] == "READY_FOR_MANUAL_APPLY"
    assert candidate["v2_evidence_count"] == 3
    assert candidate["duplicate_identity_count"] == 0


def test_3362_negative_mismatch_value_is_refused_not_summed() -> None:
    rows = [
        _signed_row("a", v2_trust_mismatch_count=1),
        _signed_row("b", v2_trust_mismatch_count=-1),
        _signed_row("c"),
        _signed_row("d"),
        _negative_row("neg"),
    ]

    candidate = _accumulate_rows(rows)

    assert candidate["status"] == "BLOCKED"
    assert candidate["v2_trust_mismatch_count"] == 1
    assert candidate["rejected_row_refs"] == ["b"]


def test_3362_non_integer_mismatch_value_is_refused() -> None:
    for value in ("0", 0.5, True):
        candidate = _accumulate_rows([
            _signed_row("a", v2_trust_mismatch_count=value),
            _negative_row("neg"),
        ])
        assert candidate["rejected_row_refs"] == ["a"], value
        assert candidate["v2_evidence_count"] == 0, value


def test_3362_repeated_row_still_adds_its_mismatch() -> None:
    first = _signed_row("a")
    base = [_signed_row("b"), _signed_row("c"), _negative_row("neg")]
    for repeat in (
        {**first, "v2_trust_mismatch_count": 1},
        {**_resigned(first, "run-2"), "v2_trust_mismatch_count": 1},
    ):
        candidate = _accumulate_rows([first, repeat, *base])
        assert candidate["v2_evidence_count"] == 3
        assert candidate["v2_trust_mismatch_count"] == 1
        assert candidate["status"] == "BLOCKED"
