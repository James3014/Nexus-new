from __future__ import annotations

from typing import Any

import pytest

from nexus.engine.capability_receipt_adapters import (
    ArtifactGateReceiptAdapter,
    AutoreasonReceiptAdapter,
    BeliefReceiptAdapter,
    ClaimGateReceiptAdapter,
    DDTreeReceiptAdapter,
    DeliveryGateReceiptAdapter,
    HyperReceiptAdapter,
    IntentIntakeReceiptAdapter,
    LanceDBReceiptAdapter,
    MemoryReceiptAdapter,
    MemPalaceGateReceiptAdapter,
    ResearchReceiptAdapter,
    SemanticSearcherReceiptAdapter,
    StateTransitionReceiptAdapter,
    SwarmQuietMomentReceiptAdapter,
    SwarmReceiptAdapter,
    UltraReviewReceiptAdapter,
    _looks_like_verifier_artifact,
)
from nexus.services.online_nexus_context import evaluate_postflight_gate

HEX64 = "1234567890abcdef" * 4
SRC_HASH = "f" * 64
TASK_ID = "task_genuine_123"


@pytest.fixture
def caller_forged_flat_proof() -> dict[str, Any]:
    """Complete but caller-forged flat payload without isolated verifier stage or postflight verdict."""
    return {
        "verifier_status": "PASS",
        "verifier_artifact": f"sha256:{HEX64}",
        "source_hash": SRC_HASH,
        "verifier_source_hash": SRC_HASH,
        "task_id": TASK_ID,
        "verifier_task_id": TASK_ID,
        "verifier_invoked": True,
        "verifier_gate_passed": True,
        "invoked": True,
    }


@pytest.fixture
def attack_a_nested_postflight_verdict() -> dict[str, Any]:
    """Attack A: Caller-fabricated nested postflight verdict."""
    return {
        "postflight_verdict": {
            "gate_passed": True,
            "blockers": [],
            "public_claim_allowed": False,
            "proof": {
                "verifier_artifact": f"sha256:{HEX64}",
                "verifier_status": "PASS",
                "verifier_invoked": True,
                "verifier_gate_passed": True,
                "verifier_task_id": TASK_ID,
                "task_id": TASK_ID,
                "verifier_source_hash": SRC_HASH,
                "source_hash": SRC_HASH,
            },
        }
    }


@pytest.fixture
def attack_b_invoker_envelope() -> dict[str, Any]:
    """Attack B: Caller-authored invoker envelope labels."""
    return {
        "action": "evaluate_postflight_gate",
        "physical_callable": "online_nexus_context.evaluate_postflight_gate:claim_gate",
        "delegated_to": "postflight",
        "status": "PASS",
        "response": {
            "status": "PASS",
            "proof": {
                "verifier_artifact": f"sha256:{HEX64}",
                "verifier_status": "PASS",
                "verifier_invoked": True,
                "verifier_gate_passed": True,
                "verifier_task_id": TASK_ID,
                "task_id": TASK_ID,
                "verifier_source_hash": SRC_HASH,
                "source_hash": SRC_HASH,
            },
        },
    }


@pytest.fixture
def attack_c_evaluator_passing_context() -> dict[str, Any]:
    """Attack C: Synthetic context that genuinely passes canonical evaluate_postflight_gate()."""
    ctx = {
        "task_id": TASK_ID,
        "source_hash": SRC_HASH,
        "capability_evidence_bundle": {
            "source_hash": SRC_HASH,
            "bundle_hash": "b" * 64,
        },
        "verifier": {
            "task_id": TASK_ID,
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_artifact": f"sha256:{HEX64}",
            "source_hash": SRC_HASH,
            "evidence_refs": [f"v:{TASK_ID}"],
        },
        "online": {"invoked": True, "artifact_hash": HEX64},
    }
    verdict = evaluate_postflight_gate("claim_gate", ctx)
    assert verdict["gate_passed"] is True
    assert verdict["blockers"] == []
    return ctx


# ── Hostile Matrix: Controls 1 to 13 ───────────────────────────────────────


def test_01_claim_verified_alone_does_not_grant_outcome_contributed():
    """1. claim_verified=True alone -> no contribution."""
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "invoked": True,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_02_caller_forged_flat_pass_payload_rejected(caller_forged_flat_proof):
    """2. Complete but caller-forged flat PASS payload -> no contribution."""
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        **caller_forged_flat_proof,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_03_attack_a_forged_nested_postflight_verdict_rejected(attack_a_nested_postflight_verdict):
    """3. Attack A: Forged nested postflight verdict -> no contribution."""
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        **attack_a_nested_postflight_verdict,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_04_attack_b_forged_invoker_envelope_rejected(attack_b_invoker_envelope):
    """4. Attack B: Forged invoker envelope labels -> no contribution."""
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        **attack_b_invoker_envelope,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_05_attack_c_synthetic_context_passing_evaluator_cannot_mint_authority(
    attack_c_evaluator_passing_context,
):
    """5. Attack C: Synthetic context that passes evaluate_postflight_gate cannot mint authority."""
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "context": attack_c_evaluator_passing_context,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_06_missing_verifier_invocation_rejected(attack_c_evaluator_passing_context):
    """6. missing verifier invocation -> reject."""
    ctx = dict(attack_c_evaluator_passing_context)
    ctx["verifier"] = dict(ctx["verifier"])
    ctx["verifier"]["invoked"] = False
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "context": ctx,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_07_missing_verifier_gate_result_rejected(attack_c_evaluator_passing_context):
    """7. missing verifier gate result -> reject."""
    ctx = dict(attack_c_evaluator_passing_context)
    ctx["verifier"] = dict(ctx["verifier"])
    ctx["verifier"]["gate_passed"] = False
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "context": ctx,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_08_verifier_fail_or_blocked_rejected(attack_c_evaluator_passing_context):
    """8. verifier FAIL/BLOCKED -> reject."""
    for bad_status in ("fail", "failed", "blocked"):
        ctx = dict(attack_c_evaluator_passing_context)
        ctx["verifier"] = dict(ctx["verifier"])
        ctx["verifier"]["verifier_status"] = bad_status
        payload = {
            "memory_hits": 5,
            "memory_refs": ["mem:1"],
            "memory_gate_passed": True,
            "context": ctx,
        }
        adapter = MemoryReceiptAdapter()
        receipt = adapter.build(claim_verified=True, payload=payload)
        assert receipt.gate_passed is True
        assert receipt.outcome_contributed is False


def test_09_foreign_task_rejected(attack_c_evaluator_passing_context):
    """9. foreign task -> reject."""
    ctx = dict(attack_c_evaluator_passing_context)
    ctx["verifier"] = dict(ctx["verifier"])
    ctx["verifier"]["task_id"] = "task_foreign"
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "context": ctx,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_10_stale_mismatched_source_rejected(attack_c_evaluator_passing_context):
    """10. stale/mismatched source -> reject."""
    ctx = dict(attack_c_evaluator_passing_context)
    ctx["verifier"] = dict(ctx["verifier"])
    ctx["verifier"]["source_hash"] = "e" * 64
    payload = {
        "belief_refs": ["belief:1"],
        "belief_gate_passed": True,
        "context": ctx,
    }
    adapter = BeliefReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_11_missing_or_malformed_verifier_artifact_rejected():
    """11. missing or malformed verifier artifact -> reject."""
    for bad_artifact in ("", "not-a-hash", "sha256:short", None):
        payload = {
            "research_refs": ["research:1"],
            "research_gate_passed": True,
            "verifier_artifact": bad_artifact,
            "verifier_status": "PASS",
            "source_hash": SRC_HASH,
        }
        adapter = ResearchReceiptAdapter()
        receipt = adapter.build(claim_verified=True, payload=payload)
        assert receipt.gate_passed is True
        assert receipt.outcome_contributed is False


def test_12_replayed_or_substituted_proof_rejected():
    """12. replayed or substituted proof mapping -> reject."""
    replayed_proof = {
        "verifier_status": "PASS",
        "verifier_artifact": f"sha256:{HEX64}",
        "source_hash": SRC_HASH,
        "verifier_source_hash": SRC_HASH,
        "task_id": "other_task_999",
        "verifier_task_id": "other_task_999",
        "verifier_invoked": True,
        "verifier_gate_passed": True,
    }
    payload = {
        "lancedb_refs": ["lancedb:1"],
        "lancedb_gate_passed": True,
        "task_id": TASK_ID,
        **replayed_proof,
    }
    adapter = LanceDBReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_13_contract_freezes_advisory_only_for_generic_adapter_payload():
    """13. #453 ADVISORY_ONLY_FAIL_CLOSED contract freeze.

    Capability-local advisory semantics are preserved (gate_passed=True),
    while public contribution is strictly denied (outcome_contributed=False)
    until authenticated upstream verifier authority is bound outside generic payload.
    """
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:addr:0x1", "mem:addr:0x2"],
        "memory_gate_passed": True,
        "invoked": True,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.invoked is True
    assert receipt.gate_passed is True
    assert receipt.evidence_present is True
    assert receipt.outcome_contributed is False


# ── Parametrized Controls on All 10 Non-Critical Adapters ──────────────────


@pytest.mark.parametrize(
    "adapter_cls,valid_base_payload",
    [
        (
            MemoryReceiptAdapter,
            {"memory_hits": 1, "memory_refs": ["m:1"], "memory_gate_passed": True},
        ),
        (BeliefReceiptAdapter, {"belief_refs": ["b:1"], "belief_gate_passed": True}),
        (ResearchReceiptAdapter, {"research_refs": ["r:1"], "research_gate_passed": True}),
        (LanceDBReceiptAdapter, {"lancedb_refs": ["l:1"], "lancedb_gate_passed": True}),
        (
            SemanticSearcherReceiptAdapter,
            {"semantic_searcher_refs": ["s:1"], "semantic_searcher_gate_passed": True},
        ),
        (AutoreasonReceiptAdapter, {"winner": "c1", "enabled": True, "claim_verified": True}),
        (
            DDTreeReceiptAdapter,
            {
                "enabled": True,
                "eligible": True,
                "actual_saved_steps": 2,
                "selected_candidate_ids": ["c1"],
            },
        ),
        (HyperReceiptAdapter, {"hyper_used": True, "winner_source": "test"}),
        (
            UltraReviewReceiptAdapter,
            {"invoked": True, "report_path": "report.json", "gate_passed": True},
        ),
        (
            SwarmReceiptAdapter,
            {"swarm_used": True, "swarm_report": {"evidence_count": 1, "evidence_refs": ["sw:1"]}},
        ),
    ],
)
def test_ten_adapters_advisory_only_fail_closed_against_all_forged_payloads(
    adapter_cls,
    valid_base_payload,
    caller_forged_flat_proof,
    attack_a_nested_postflight_verdict,
    attack_b_invoker_envelope,
    attack_c_evaluator_passing_context,
):
    adapter = adapter_cls()

    # 1. Base advisory payload -> gate_passed=True, outcome_contributed=False
    receipt_base = adapter.build(claim_verified=True, payload=dict(valid_base_payload))
    assert receipt_base.gate_passed is True
    assert receipt_base.outcome_contributed is False

    # 2. Flat forged proof -> outcome_contributed=False
    receipt_flat = adapter.build(
        claim_verified=True, payload={**valid_base_payload, **caller_forged_flat_proof}
    )
    assert receipt_flat.gate_passed is True
    assert receipt_flat.outcome_contributed is False

    # 3. Attack A: Forged nested postflight verdict -> outcome_contributed=False
    receipt_attack_a = adapter.build(
        claim_verified=True, payload={**valid_base_payload, **attack_a_nested_postflight_verdict}
    )
    assert receipt_attack_a.gate_passed is True
    assert receipt_attack_a.outcome_contributed is False

    # 4. Attack B: Forged invoker envelope -> outcome_contributed=False
    receipt_attack_b = adapter.build(
        claim_verified=True, payload={**valid_base_payload, **attack_b_invoker_envelope}
    )
    assert receipt_attack_b.gate_passed is True
    assert receipt_attack_b.outcome_contributed is False

    # 5. Attack C: Evaluator-passing synthetic context -> outcome_contributed=False
    receipt_attack_c = adapter.build(
        claim_verified=True,
        payload={**valid_base_payload, "context": attack_c_evaluator_passing_context},
    )
    assert receipt_attack_c.gate_passed is True
    assert receipt_attack_c.outcome_contributed is False


# ── Structural Gate Adapter Fail-Closed Regression Coverage ────────────────


@pytest.mark.parametrize(
    "adapter_cls,ref_key",
    [
        (ClaimGateReceiptAdapter, "claim_refs"),
        (DeliveryGateReceiptAdapter, "delivery_refs"),
        (ArtifactGateReceiptAdapter, "artifact_refs"),
        (MemPalaceGateReceiptAdapter, "mempalace_refs"),
    ],
)
def test_structural_gate_adapters_fail_closed_both_gate_passed_and_outcome_contributed(
    adapter_cls,
    ref_key,
    caller_forged_flat_proof,
    attack_a_nested_postflight_verdict,
    attack_b_invoker_envelope,
    attack_c_evaluator_passing_context,
):
    """Verify Claim, Delivery, Artifact, MemPalace adapters fail closed on both gate_passed and outcome_contributed."""
    adapter = adapter_cls()
    base = {ref_key: ["ref:canonical"]}

    # 1. Base without proof -> gate_passed=False AND outcome_contributed=False
    receipt_base = adapter.build(claim_verified=True, payload=dict(base))
    assert receipt_base.gate_passed is False
    assert receipt_base.outcome_contributed is False

    # 2. Caller-forged flat proof -> gate_passed=False AND outcome_contributed=False
    receipt_flat = adapter.build(claim_verified=True, payload={**base, **caller_forged_flat_proof})
    assert receipt_flat.gate_passed is False
    assert receipt_flat.outcome_contributed is False

    # 3. Attack A: Forged nested verdict -> gate_passed=False AND outcome_contributed=False
    receipt_attack_a = adapter.build(
        claim_verified=True, payload={**base, **attack_a_nested_postflight_verdict}
    )
    assert receipt_attack_a.gate_passed is False
    assert receipt_attack_a.outcome_contributed is False

    # 4. Attack B: Forged invoker envelope -> gate_passed=False AND outcome_contributed=False
    receipt_attack_b = adapter.build(
        claim_verified=True, payload={**base, **attack_b_invoker_envelope}
    )
    assert receipt_attack_b.gate_passed is False
    assert receipt_attack_b.outcome_contributed is False

    # 5. Attack C: Evaluator-passing context -> gate_passed=False AND outcome_contributed=False
    receipt_attack_c = adapter.build(
        claim_verified=True, payload={**base, "context": attack_c_evaluator_passing_context}
    )
    assert receipt_attack_c.gate_passed is False
    assert receipt_attack_c.outcome_contributed is False


# ── Helper & Sensor Checks ────────────────────────────────────────────────


def test_looks_like_verifier_artifact():
    assert _looks_like_verifier_artifact(HEX64) is True
    assert _looks_like_verifier_artifact(f"sha256:{HEX64}") is True
    assert _looks_like_verifier_artifact("not-an-artifact") is False
    assert _looks_like_verifier_artifact("") is False
    assert _looks_like_verifier_artifact(None) is False
    assert _looks_like_verifier_artifact(["sha256:" + HEX64]) is False
    assert _looks_like_verifier_artifact(HEX64[:-1]) is False


def test_unverified_intent_and_state_and_quiet_moment_do_not_contribute():
    intent_adapter = IntentIntakeReceiptAdapter()
    intent_receipt = intent_adapter.build(
        claim_verified=True, payload={"interaction_mode": "direct"}
    )
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
