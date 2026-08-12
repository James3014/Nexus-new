from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from nexus.orchestrator.acceptance_loop import (
    AcceptanceDecision,
    CandidateAcceptanceRequest,
    IndependentReviewReceipt,
    reduce_candidate_acceptance,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

COMMIT = "a" * 40
TREE = "b" * 40
STATE = "c" * 64
DIFF = "d" * 64
RECEIPT = "e" * 64
ARTIFACT = "f" * 64


def _request(*, candidate_class: str = "GENERAL") -> CandidateAcceptanceRequest:
    return CandidateAcceptanceRequest(
        task_id="task-1",
        attempt_id="attempt-1",
        implementer_id="worker-1",
        candidate_commit_sha=COMMIT,
        candidate_tree_sha=TREE,
        candidate_state_hash=STATE,
        candidate_diff_hash=DIFF,
        verified_receipt_hash=RECEIPT,
        candidate_class=candidate_class,
    )


def _review(**changes: Any) -> IndependentReviewReceipt:
    values: dict[str, Any] = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "reviewer_id": "reviewer-1",
        "candidate_commit_sha": COMMIT,
        "candidate_tree_sha": TREE,
        "candidate_state_hash": STATE,
        "candidate_diff_hash": DIFF,
        "verified_receipt_hash": RECEIPT,
        "verifier_artifact_hash": ARTIFACT,
        "review_status": "PASS",
        "exit_code": 0,
    }
    values.update(changes)
    return IndependentReviewReceipt(**values)


def _sha256_ref(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _verified_repair_evidence() -> dict[str, Any]:
    refs = {gate: f"sha256:{gate * 64}" for gate in ("a", "b", "c")}
    gate_refs = {gate: refs[value] for gate, value in zip(("g1", "g2", "g3"), refs)}
    adequacy: dict[str, Any] = {
        "schema": "nexus.world_c.adequacy_projection.v1",
        "task_id": "repair-1",
        "status": "VERIFIED_REPAIR",
        "reasons": [],
        "upstream_evidence_refs": gate_refs,
        "upstream_evidence": {gate: {"ref": ref} for gate, ref in gate_refs.items()},
        "world_c_receipt_hash": "sha256:" + "d" * 64,
        "root_receipt_hash": "sha256:" + "e" * 64,
        "world_c_receipt_valid": True,
        "root_receipt_valid": True,
        "public_claim_allowed": False,
    }
    adequacy["adequacy_hash"] = _sha256_ref(adequacy)
    mutation = {
        "schema_version": "nexus_issue16_mutation_assurance.v1",
        "decision": "REQUIRED",
        "required": True,
        "status": "PASS",
        "passed": True,
        "failures": [],
    }
    payloads = {"adequacy": adequacy, "mutation": mutation}
    receipts: dict[str, dict[str, Any]] = {}
    receipt_refs: list[str] = []
    for kind, payload in payloads.items():
        ref = _sha256_ref(payload)
        receipt_refs.append(ref)
        receipts[kind] = {"ref": ref, "content_hash": ref, "payload": payload}
    return {
        "calibration_case": "correct",
        "upstream_receipt_refs": receipt_refs,
        "upstream_receipts": receipts,
        "patch_applied": True,
        "patch_sha": "patch-sha",
        "base_sha": "base-sha",
        "candidate_sha": "candidate-sha",
        "compile_passed": True,
        "hidden_verifier_passed": True,
        "behavioral_verifier_passed": True,
        "regression_passed": True,
        "mutation_assurance_passed": True,
        "public_claim_allowed": False,
    }


def test_exact_general_candidate_is_accepted_without_promotion() -> None:
    result = reduce_candidate_acceptance(_request(), _review())

    assert result.decision is AcceptanceDecision.ACCEPT
    assert result.reasons == ()
    assert result.approval_performed is False
    assert result.integration_performed is False
    assert result.merge_performed is False
    assert result.public_claim_allowed is False


def test_reviewer_cannot_be_candidate_implementer() -> None:
    result = reduce_candidate_acceptance(_request(), _review(reviewer_id="worker-1"))
    assert result.decision is AcceptanceDecision.BLOCK
    assert "reviewer_is_implementer" in result.reasons


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "wrong-task"),
        ("attempt_id", "wrong-attempt"),
        ("candidate_commit_sha", "1" * 40),
        ("candidate_tree_sha", "2" * 40),
        ("candidate_state_hash", "3" * 64),
        ("candidate_diff_hash", "4" * 64),
        ("verified_receipt_hash", "5" * 64),
    ],
)
def test_exact_candidate_binding_mismatch_blocks(field: str, value: str) -> None:
    result = reduce_candidate_acceptance(_request(), _review(**{field: value}))
    assert result.decision is AcceptanceDecision.BLOCK
    assert f"{field}_mismatch" in result.reasons


def test_independent_review_defect_is_repairable() -> None:
    result = reduce_candidate_acceptance(
        _request(), _review(review_status="DEFECT", reasons=("verifier_fixture_defect",))
    )
    assert result.decision is AcceptanceDecision.REPAIRABLE
    assert result.reasons == ("verifier_fixture_defect",)


def test_verified_repair_requires_current_issue16_evidence() -> None:
    result = reduce_candidate_acceptance(_request(candidate_class="VERIFIED_REPAIR"), _review())
    assert result.decision is AcceptanceDecision.BLOCK
    assert any(reason.startswith("verified_repair:") for reason in result.reasons)


def test_verified_repair_consumes_existing_reducer_semantics() -> None:
    result = reduce_candidate_acceptance(
        _request(candidate_class="VERIFIED_REPAIR"),
        _review(),
        verified_repair_evidence=_verified_repair_evidence(),
    )
    assert result.decision is AcceptanceDecision.ACCEPT


def test_bare_zero_exit_cannot_promote_descriptive_repair() -> None:
    result = reduce_candidate_acceptance(
        _request(candidate_class="VERIFIED_REPAIR"),
        _review(exit_code=0, reasons=("descriptive reproduction only",)),
        verified_repair_evidence={"compile_passed": True},
    )
    assert result.decision is AcceptanceDecision.BLOCK


def test_service_projection_is_read_only_and_typed() -> None:
    output = SelfHostedTaskService.evaluate_candidate_acceptance(_request(), _review())
    assert output["decision"] == "ACCEPT"
    assert output["approval_performed"] is False
    assert output["integration_performed"] is False
    assert output["merge_performed"] is False
