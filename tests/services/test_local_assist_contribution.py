from __future__ import annotations

from nexus.services.local_assist_contribution import evaluate_contribution


def _receipt() -> dict[str, object]:
    return {
        "task_id": "m5-a-001",
        "output_delivered": True,
        "claim_boundary": {"output_consumed": True},
        "candidate_hashes": ["candidate-hash"],
    }


def test_receipt_existence_alone_is_not_contribution() -> None:
    result = evaluate_contribution(
        receipt=_receipt(),
        consumption={},
        causal_evidence={},
        contribution_type="candidate",
    )
    assert result["outcome_contributed"] is False
    assert result["reason"] == "receipt_only_insufficient"
    assert result["value_measured"] is False


def test_consumption_alone_is_not_contribution() -> None:
    result = evaluate_contribution(
        receipt=_receipt(),
        consumption={"receipt_identities": ["candidate-receipt"]},
        causal_evidence={},
        contribution_type="candidate",
    )
    assert result["outcome_contributed"] is False
    assert result["reason"] == "consumption_only_insufficient"


def test_adopted_candidate_with_hash_lineage_proves_contribution() -> None:
    result = evaluate_contribution(
        receipt=_receipt(),
        consumption={"receipt_identities": ["candidate-receipt"], "output_used": True},
        causal_evidence={
            "candidate_content_adopted": True,
            "accepted_content_hashes": ["candidate-hash"],
            "evidence_refs": ["agent:adoption", "test:verified"],
        },
        contribution_type="candidate",
        confidence=0.9,
    )
    assert result["outcome_contributed"] is True
    assert result["contribution_type"] == "candidate"
    assert result["accepted_content_hashes"] == ["candidate-hash"]
    assert result["claim_boundary"]["public_claim_allowed"] is False


def test_rejection_preventing_invalid_modification_can_contribute() -> None:
    result = evaluate_contribution(
        receipt=_receipt(),
        consumption={"receipt_identities": ["advisor-receipt"], "output_used": True},
        causal_evidence={
            "prevented_invalid_modification": True,
            "evidence_refs": ["agent:rejection", "test:invalid-patch"],
        },
        contribution_type="rejection",
    )
    assert result["outcome_contributed"] is True
    assert result["counterfactual_available"] is False


def test_missing_causal_link_keeps_explicit_false_claim() -> None:
    result = evaluate_contribution(
        receipt=_receipt(),
        consumption={"receipt_identities": ["candidate-receipt"], "output_used": True},
        causal_evidence={"candidate_content_adopted": True, "evidence_refs": []},
        contribution_type="candidate",
    )
    assert result["outcome_contributed"] is False
    assert result["reason"] == "causal_evidence_incomplete"
