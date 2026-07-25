"""Tests for the fail-closed live proof validator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.local_assist_live_proof import (
    LIVE_PROOF_FAIL,
    LIVE_PROOF_NOT_RUN,
    LIVE_PROOF_PASS,
    LiveProofResult,
    validate_live_proof,
    write_live_proof_result,
)


def _base_receipt(**overrides: object) -> dict:
    receipt = {
        "task_id": "test-task",
        "workspace_revision": "rev-1",
        "receipt_complete": True,
        "terminal_status": "SUCCEEDED",
        "evidence_mode": "live_runtime",
        "local": {
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "response": {
                "provider": "ollama",
                "local_model_invoked": True,
                "output_delivered": True,
                "provider_call_count": 1,
            },
        },
        "online": {
            "invoked": True,
            "gate_passed": True,
            "status": "SUCCEEDED",
            "response": {
                "provider": "grok",
                "invoked": True,
                "output_delivered": True,
                "provider_call_count": 1,
                "transport": "registered_cli",
                "evidence_refs": ["online:test:local_context_forwarded"],
            },
        },
        "verifier": {
            "invoked": True,
            "gate_passed": True,
        },
    }
    receipt.update(overrides)
    return receipt


def _base_report(**overrides: object) -> dict:
    report = {
        "task_name": "test-task",
        "unified_runtime_task_id": "test-task",
        "unified_runtime_receipt_path": "",
        "local_assist_mode": "advisor",
        "local_assist_success": True,
        "online_success": True,
        "runtime_receipt_complete": True,
        "local_context_forwarded": True,
        "online_provider": "grok",
        "workspace_revision": "rev-1",
        "formal_workspace_mutated": False,
    }
    report.update(overrides)
    return report


def test_missing_receipts_returns_not_run() -> None:
    result = validate_live_proof(
        pipeline_report=None,
        unified_runtime_receipt=None,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_NOT_RUN
    assert result.claim_boundary["public_claim_allowed"] is False
    assert result.claim_boundary["production_ready"] is False


def test_canary_evidence_cannot_receive_live_pass() -> None:
    receipt = _base_receipt()
    receipt["evidence_mode"] = "canary"
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
        evidence_mode="canary",
    )
    assert result.status != LIVE_PROOF_PASS
    assert any("non_live_evidence_mode:canary" in f for f in result.failures)
    assert result.claim_boundary["public_claim_allowed"] is False
    assert result.claim_boundary["production_ready"] is False


def test_fixture_evidence_cannot_receive_live_pass() -> None:
    receipt = _base_receipt()
    receipt["evidence_mode"] = "fixture"
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
        evidence_mode="fixture",
    )
    assert result.status != LIVE_PROOF_PASS
    assert any("non_live_evidence_mode:fixture" in f for f in result.failures)
    assert result.claim_boundary["public_claim_allowed"] is False


def test_simulation_evidence_cannot_receive_live_pass() -> None:
    receipt = _base_receipt()
    receipt["evidence_mode"] = "simulation"
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
        evidence_mode="simulation",
    )
    assert result.status != LIVE_PROOF_PASS
    assert any("non_live_evidence_mode:simulation" in f for f in result.failures)


def test_missing_provider_call_count_fails_closed() -> None:
    receipt = _base_receipt()
    receipt["local"]["response"]["provider_call_count"] = 0
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_FAIL
    assert any("local_provider_call_count_lt_1" in f for f in result.failures)


def test_incomplete_receipt_fails_closed() -> None:
    receipt = _base_receipt()
    receipt["receipt_complete"] = False
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_FAIL
    assert any("receipt_incomplete" in f for f in result.failures)


def test_formal_workspace_mutation_fails_closed() -> None:
    receipt = _base_receipt()
    report = _base_report(formal_workspace_mutated=True)
    result = validate_live_proof(
        pipeline_report=report,
        unified_runtime_receipt=receipt,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_FAIL
    assert any("formal_workspace_mutated" in f for f in result.failures)


def test_public_and_production_claims_remain_false() -> None:
    receipt = _base_receipt()
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_PASS
    assert result.claim_boundary["public_claim_allowed"] is False
    assert result.claim_boundary["production_ready"] is False
    assert result.claim_boundary["value_measured"] is False
    assert result.claim_boundary["real_local_online_continuation_observed"] is True


def test_live_pass_requires_all_components() -> None:
    receipt = _base_receipt()
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_PASS
    assert result.evidence["local_invoked"] is True
    assert result.evidence["online_invoked"] is True
    assert result.evidence["local_provider_call_count"] == 1
    assert result.evidence["online_provider_call_count"] == 1
    assert result.evidence["local_context_forwarded"] is True
    assert result.evidence["formal_workspace_mutated"] is False


def test_write_live_proof_result_creates_file(tmp_path: Path) -> None:
    result = LiveProofResult(
        status=LIVE_PROOF_PASS,
        reason="test",
        evidence={"test": True},
    )
    path = tmp_path / "proof.json"
    write_live_proof_result(path, result)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "nexus.local_assist.live_proof.v1"
    assert data["status"] == LIVE_PROOF_PASS
    assert data["evidence"]["test"] is True


def test_verifier_not_invoked_fails_closed() -> None:
    receipt = _base_receipt()
    receipt["verifier"]["invoked"] = False
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_FAIL
    assert any("verifier_not_invoked" in f for f in result.failures)


def test_verifier_gate_not_passed_fails_closed() -> None:
    receipt = _base_receipt()
    receipt["verifier"]["gate_passed"] = False
    result = validate_live_proof(
        unified_runtime_receipt=receipt,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_FAIL
    assert any("verifier_gate_not_passed" in f for f in result.failures)


def test_task_id_mismatch_fails_closed() -> None:
    receipt = _base_receipt()
    report = _base_report(unified_runtime_task_id="different-task")
    result = validate_live_proof(
        pipeline_report=report,
        unified_runtime_receipt=receipt,
        external_authorized=True,
    )
    assert result.status == LIVE_PROOF_FAIL
    assert any("task_id_mismatch" in f for f in result.failures)
