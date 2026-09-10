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
def genuine_postflight_context() -> dict[str, Any]:
    """Canonical postflight execution context with isolated verifier stage and sealed source."""
    return {
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


# ── Hostile Matrix: Controls 1 to 12 ───────────────────────────────────────


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


def test_02_caller_forged_pass_payload_rejected(caller_forged_flat_proof):
    """2. 完整但 caller-forged PASS payload -> no contribution."""
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


def test_03_syntactically_valid_fake_artifact_rejected():
    """3. syntactically valid fake 64hex artifact in flat payload -> no contribution."""
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "verifier_artifact": f"sha256:{HEX64}",
        "source_hash": SRC_HASH,
        "invoked": True,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_04_correct_looking_task_and_source_without_verifier_execution_rejected():
    """4. correct-looking task/source strings but no real verifier execution -> no contribution."""
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "task_id": TASK_ID,
        "verifier_task_id": TASK_ID,
        "source_hash": SRC_HASH,
        "verifier_source_hash": SRC_HASH,
        "invoked": True,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_05_missing_verifier_invocation_rejected(genuine_postflight_context):
    """5. missing verifier invocation -> reject."""
    ctx = dict(genuine_postflight_context)
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


def test_06_missing_verifier_gate_result_rejected(genuine_postflight_context):
    """6. missing verifier gate result -> reject."""
    ctx = dict(genuine_postflight_context)
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


def test_07_verifier_fail_or_blocked_rejected(genuine_postflight_context):
    """7. verifier FAIL/BLOCKED -> reject."""
    for bad_status in ("fail", "failed", "blocked"):
        ctx = dict(genuine_postflight_context)
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


def test_08_foreign_task_rejected(genuine_postflight_context):
    """8. foreign task -> reject."""
    ctx = dict(genuine_postflight_context)
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


def test_09_stale_mismatched_source_rejected(genuine_postflight_context):
    """9. stale/mismatched source -> reject."""
    ctx = dict(genuine_postflight_context)
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


def test_10_substituted_malformed_artifact_rejected(genuine_postflight_context):
    """10. substituted artifact (not valid sha256 64hex) -> reject."""
    ctx = dict(genuine_postflight_context)
    ctx["verifier"] = dict(ctx["verifier"])
    ctx["verifier"]["verifier_artifact"] = "not-an-artifact"
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


def test_11_bundle_refs_substitution_rejected(genuine_postflight_context):
    """11. bundle/evidence refs substitution in delivery gate -> reject."""
    ctx = dict(genuine_postflight_context)
    ctx["verifier"] = dict(ctx["verifier"])
    ctx["verifier"]["verifier_artifact"] = ""
    ctx["online"] = {"invoked": True}
    payload = {
        "delivery_refs": ["d:1"],
        "delivery_gate_passed": True,
        "context": ctx,
    }
    adapter = DeliveryGateReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.outcome_contributed is False


def test_12_local_advisory_gate_preserved_without_contribution():
    """12. local advisory gate may remain true without public contribution."""
    payload = {
        "memory_hits": 10,
        "memory_refs": ["mem:addr:0x1", "mem:addr:0x2"],
        "memory_gate_passed": True,
        "invoked": True,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=False, payload=payload)
    assert receipt.invoked is True
    assert receipt.gate_passed is True
    assert receipt.evidence_present is True
    assert receipt.outcome_contributed is False


# ── Hostile Matrix: Control 13 — Genuine Verifier Positive Path ───────────


def test_13_genuine_verifier_backed_positive_path(genuine_postflight_context):
    """13. genuine existing verifier-backed positive path -> contribution allowed.

    Must use production-equivalent verifier/postflight path via canonical
    online_nexus_context.evaluate_postflight_gate.
    """
    # 1. Evaluate genuine context through production postflight gate
    verdict = evaluate_postflight_gate("claim_gate", genuine_postflight_context)
    assert verdict["gate_passed"] is True
    assert verdict["blockers"] == []

    # 2. Bridge validated postflight verdict to capability adapter
    payload = {
        "memory_hits": 5,
        "memory_refs": ["mem:1"],
        "memory_gate_passed": True,
        "postflight_verdict": verdict,
    }
    adapter = MemoryReceiptAdapter()
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is True


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
def test_ten_adapters_require_genuine_verifier_for_outcome_contributed(
    adapter_cls, valid_base_payload, genuine_postflight_context, caller_forged_flat_proof
):
    adapter = adapter_cls()

    # 1. Negative control: without verifier proof -> outcome_contributed=False
    receipt_no_proof = adapter.build(claim_verified=True, payload=dict(valid_base_payload))
    assert receipt_no_proof.gate_passed is True
    assert receipt_no_proof.outcome_contributed is False

    # 2. Negative control: caller-forged flat payload -> outcome_contributed=False
    forged_payload = {**valid_base_payload, **caller_forged_flat_proof}
    receipt_forged = adapter.build(claim_verified=True, payload=forged_payload)
    assert receipt_forged.gate_passed is True
    assert receipt_forged.outcome_contributed is False

    # 3. Positive control: genuine postflight context -> outcome_contributed=True
    verdict = evaluate_postflight_gate("claim_gate", genuine_postflight_context)
    positive_payload = {**valid_base_payload, "postflight_verdict": verdict}
    receipt_with_proof = adapter.build(claim_verified=True, payload=positive_payload)
    assert receipt_with_proof.gate_passed is True
    assert receipt_with_proof.outcome_contributed is True


# ── Structural Gate Adapter Regression Coverage (Review Requirement) ───────


@pytest.mark.parametrize(
    "adapter_cls,ref_key",
    [
        (ClaimGateReceiptAdapter, "claim_refs"),
        (DeliveryGateReceiptAdapter, "delivery_refs"),
        (ArtifactGateReceiptAdapter, "artifact_refs"),
        (MemPalaceGateReceiptAdapter, "mempalace_refs"),
    ],
)
def test_structural_gate_adapters_fail_closed_on_forged_and_pass_on_genuine(
    adapter_cls, ref_key, genuine_postflight_context, caller_forged_flat_proof
):
    """Verify Claim, Delivery, Artifact, MemPalace adapters fail closed on forged and pass on genuine."""
    adapter = adapter_cls()
    base = {ref_key: ["ref:canonical"]}

    # 1. Caller-forged flat payload -> rejected
    forged = {**base, **caller_forged_flat_proof}
    receipt_forged = adapter.build(claim_verified=True, payload=forged)
    assert receipt_forged.outcome_contributed is False

    # 2. Genuine postflight verdict -> accepted
    verdict = evaluate_postflight_gate(adapter.name, genuine_postflight_context)
    genuine = {**base, "postflight_verdict": verdict}
    receipt_genuine = adapter.build(claim_verified=True, payload=genuine)
    assert receipt_genuine.gate_passed is True
    assert receipt_genuine.outcome_contributed is True


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
