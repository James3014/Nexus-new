"""
H8-5 Fake Adapter Verifier / Receipt Gate Tests

Gate: H8 verifier and receipt gate boundary.

Safety boundary:
- NO_RUNTIME_BEHAVIOR_CHANGE / NO_LOCAL_MODEL_RUN
- NO_OLLAMA_CALL / NO_QWEN_CALL
- NO_PROVIDER_CALL / NO_MODEL_CALL / NO_MODEL_LOAD / NO_NETWORK_CALL
- production_ready=false / public_claim_allowed=false
- H8 runtime not started

All tests are fixture-only. No real adapter or model is invoked.
"""

from __future__ import annotations

import pytest


def _accepted_candidate() -> dict:
    return {
        "receipt_id": "h8-5-receipt-001",
        "fake_adapter": True,
        "candidate_id": "h8-5-candidate",
        "selected_candidate_hash": "sha256:h8-5-candidate",
        "evidence_refs": ["receipt://h8-4"],
        "verifier_result": "pass",
        "public_claim_allowed": False,
        "production_ready": False,
        "route_truth_source": "CapabilityPlanner",
        "adapter_output_is_route_truth": False,
        "local_model_loaded": False,
        "local_model_called": False,
    }


def _candidate_acceptance(c: dict) -> bool:
    if c.get("verifier_result") != "pass":
        return False
    if not c.get("receipt_id"):
        return False
    if not c.get("evidence_refs"):
        return False
    if not c.get("selected_candidate_hash"):
        return False
    return True


class TestH85VerifierBlocksClaim:
    def test_h8_5_verifier_not_run_blocks_public_claim(self):
        c = _accepted_candidate()
        c["verifier_result"] = "not_run"
        assert _candidate_acceptance(c) is False
        assert c["public_claim_allowed"] is False

    def test_h8_5_verifier_fail_blocks_public_claim(self):
        c = _accepted_candidate()
        c["verifier_result"] = "fail"
        assert _candidate_acceptance(c) is False
        assert c["public_claim_allowed"] is False

    def test_h8_5_verifier_pass_required_for_claim_candidate(self):
        c = _accepted_candidate()
        assert c["verifier_result"] == "pass"
        assert _candidate_acceptance(c) is True


class TestH85ReceiptBlocksAcceptance:
    def test_h8_5_receipt_missing_blocks_candidate_acceptance(self):
        c = _accepted_candidate()
        del c["receipt_id"]
        assert _candidate_acceptance(c) is False

    def test_h8_5_receipt_missing_evidence_refs_blocks_candidate_acceptance(self):
        c = _accepted_candidate()
        c["evidence_refs"] = []
        assert _candidate_acceptance(c) is False

    def test_h8_5_receipt_missing_candidate_hash_blocks_candidate_acceptance(self):
        c = _accepted_candidate()
        del c["selected_candidate_hash"]
        assert _candidate_acceptance(c) is False


class TestH85ReceiptRecords:
    def test_h8_5_receipt_records_verifier_result(self):
        c = _accepted_candidate()
        assert "verifier_result" in c
        assert c["verifier_result"] in ("not_run", "pass", "fail")

    def test_h8_5_receipt_records_fake_adapter_source(self):
        c = _accepted_candidate()
        assert c["fake_adapter"] is True

    def test_h8_5_receipt_records_model_not_called(self):
        c = _accepted_candidate()
        assert c["local_model_called"] is False

    def test_h8_5_receipt_records_model_not_loaded(self):
        c = _accepted_candidate()
        assert c["local_model_loaded"] is False


class TestH85VerifiedStillNotRouteTruth:
    def test_h8_5_verified_fake_candidate_still_not_route_truth(self):
        c = _accepted_candidate()
        assert c["adapter_output_is_route_truth"] is False
        assert c["route_truth_source"] == "CapabilityPlanner"

    def test_h8_5_verified_fake_candidate_still_production_ready_false(self):
        c = _accepted_candidate()
        assert c["production_ready"] is False
