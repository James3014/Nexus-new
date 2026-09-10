import pytest
from nexus.engine.capability_receipt_adapters import (
    MemoryReceiptAdapter,
    BeliefReceiptAdapter,
    ResearchReceiptAdapter,
    LanceDBReceiptAdapter,
    SemanticSearcherReceiptAdapter,
    IntentIntakeReceiptAdapter,
    StateTransitionReceiptAdapter,
    SwarmQuietMomentReceiptAdapter,
)


@pytest.fixture
def valid_verifier_proof():
    return {
        "verifier_status": "PASS",
        "verifier_artifact": "sha256:1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
        "source_hash": "src_hash_12345",
        "task_id": "task_abc",
        "verifier_task_id": "task_abc",
    }


def test_claim_verified_alone_does_not_grant_outcome_contributed():
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True  # Retains capability-local advisory signal
    assert receipt.outcome_contributed is False  # Must NOT contribute without verifier proof


def test_foreign_task_verifier_fails_closed():
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "verifier_status": "PASS",
        "verifier_artifact": "sha256:1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
        "source_hash": "src_hash_12345",
        "task_id": "task_local",
        "verifier_task_id": "task_foreign",
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_mismatched_source_hash_fails_closed():
    payload = {
        "belief_refs": ["belief:1"],
        "belief_gate_passed": True,
        "verifier_status": "PASS",
        "verifier_artifact": "sha256:1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
        "source_hash": "src_hash_local",
        "verifier_source_hash": "src_hash_other",
    }
    adapter = BeliefReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_unverified_intent_and_state_and_quiet_moment_do_not_contribute():
    intent_adapter = IntentIntakeReceiptAdapter()
    intent_receipt = intent_adapter.build(claim_verified=True, payload={"interaction_mode": "direct"})
    assert intent_receipt.gate_passed is True
    assert intent_receipt.outcome_contributed is False

    state_adapter = StateTransitionReceiptAdapter()
    state_receipt = state_adapter.build(claim_verified=True, payload={"gate_passed": True})
    assert state_receipt.gate_passed is True
    assert state_receipt.outcome_contributed is False

    quiet_adapter = SwarmQuietMomentReceiptAdapter()
    quiet_payload = {
        "quiet_moment": {
            "schema_version": "nexus_quiet_moment.v1",
            "production_writes_allowed": False,
            "allowed_actions": ["observe", "report", "rollback"],
            "observe": {"status": "ok"},
            "rollback": {"status": "ok"},
        }
    }
    quiet_receipt = quiet_adapter.build(claim_verified=True, payload=quiet_payload)
    assert quiet_receipt.gate_passed is True
    assert quiet_receipt.outcome_contributed is False


def test_valid_verifier_proof_grants_outcome_contributed(valid_verifier_proof):
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        **valid_verifier_proof,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is True


from nexus.engine.capability_receipt_adapters import (
    AutoreasonReceiptAdapter,
    DDTreeReceiptAdapter,
    HyperReceiptAdapter,
    UltraReviewReceiptAdapter,
    SwarmReceiptAdapter,
)

@pytest.mark.parametrize(
    "adapter_cls,valid_base_payload",
    [
        (MemoryReceiptAdapter, {"memory_hits": 1, "memory_refs": ["m:1"], "memory_gate_passed": True}),
        (BeliefReceiptAdapter, {"belief_refs": ["b:1"], "belief_gate_passed": True}),
        (ResearchReceiptAdapter, {"research_refs": ["r:1"], "research_gate_passed": True}),
        (LanceDBReceiptAdapter, {"lancedb_refs": ["l:1"], "lancedb_gate_passed": True}),
        (SemanticSearcherReceiptAdapter, {"semantic_searcher_refs": ["s:1"], "semantic_searcher_gate_passed": True}),
        (AutoreasonReceiptAdapter, {"winner": "c1", "enabled": True, "claim_verified": True}),
        (DDTreeReceiptAdapter, {"enabled": True, "eligible": True, "actual_saved_steps": 2, "selected_candidate_ids": ["c1"]}),
        (HyperReceiptAdapter, {"hyper_used": True, "winner_source": "test"}),
        (UltraReviewReceiptAdapter, {"invoked": True, "report_path": "report.json", "gate_passed": True}),
        (SwarmReceiptAdapter, {"swarm_used": True, "swarm_report": {"evidence_count": 1, "evidence_refs": ["sw:1"]}}),
    ],
)
def test_ten_adapters_require_verifier_proof_for_outcome_contributed(
    adapter_cls, valid_base_payload, valid_verifier_proof
):
    adapter = adapter_cls()
    # 1. Negative control: without verifier proof, outcome_contributed must be False
    receipt_no_proof = adapter.build(claim_verified=True, payload=dict(valid_base_payload))
    assert receipt_no_proof.gate_passed is True
    assert receipt_no_proof.outcome_contributed is False

    # 2. Positive control: with valid verifier proof, outcome_contributed must be True
    with_proof = {**valid_base_payload, **valid_verifier_proof}
    receipt_with_proof = adapter.build(claim_verified=True, payload=with_proof)
    assert receipt_with_proof.gate_passed is True
    assert receipt_with_proof.outcome_contributed is True

