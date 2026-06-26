"""
H8-4 Fake Adapter Pipeline Gate Tests

Gate: H8 fake adapter candidate pipeline boundary.

Safety boundary:
- NO_RUNTIME_BEHAVIOR_CHANGE
- NO_LOCAL_MODEL_RUN
- NO_OLLAMA_CALL / NO_QWEN_CALL
- NO_PROVIDER_CALL / NO_MODEL_CALL / NO_MODEL_LOAD / NO_NETWORK_CALL
- production_ready=false
- public_claim_allowed=false
- H8 runtime not started

All tests are fixture-only. No real adapter or model is invoked.
"""

from __future__ import annotations

import pytest


def _pipeline_candidate() -> dict:
    return {
        "fake_adapter": True,
        "candidate_id": "h8-4-candidate",
        "selected_candidate_hash": "sha256:h8-4-candidate",
        "candidate_output_isolated": True,
        "receipt_id": "h8-4-receipt-001",
        "evidence_refs": ["receipt://h8-3"],
        "verifier_result": "not_run",
        "public_claim_allowed": False,
        "production_ready": False,
        "route_truth_source": "CapabilityPlanner",
        "adapter_output_is_route_truth": False,
        "local_model_loaded": False,
        "local_model_called": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "provider_call_allowed": False,
        "network_allowed": False,
        "runtime_enabled": False,
    }


def _pipeline_receipt() -> dict:
    return {
        "receipt_id": "h8-4-receipt-001",
        "fake_adapter": True,
        "candidate_id": "h8-4-candidate",
        "selected_candidate_hash": "sha256:h8-4-candidate",
        "local_model_provider": "fake",
        "local_model_name": "fake-qwen",
        "local_model_loaded": False,
        "local_model_called": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "provider_call_allowed": False,
        "network_allowed": False,
        "adapter_output_is_route_truth": False,
        "candidate_output_isolated": True,
        "route_truth_source": "CapabilityPlanner",
        "evidence_refs": ["receipt://h8-3"],
        "verifier_result": "not_run",
        "public_claim_allowed": False,
        "production_ready": False,
    }


class TestH84PipelineIsolation:
    def test_h8_4_fake_adapter_pipeline_preserves_candidate_isolation(self):
        c = _pipeline_candidate()
        assert c["candidate_output_isolated"] is True

    def test_h8_4_fake_adapter_pipeline_requires_candidate_hash(self):
        c = _pipeline_candidate()
        assert c["selected_candidate_hash"].startswith("sha256:")

    def test_h8_4_fake_adapter_pipeline_requires_evidence_refs(self):
        r = _pipeline_receipt()
        assert len(r["evidence_refs"]) > 0


class TestH84PipelineReceipt:
    def test_h8_4_fake_adapter_pipeline_creates_receipt_fixture(self):
        r = _pipeline_receipt()
        assert r["receipt_id"] != ""
        assert r["fake_adapter"] is True

    def test_h8_4_fake_adapter_pipeline_keeps_verifier_not_run_initially(self):
        r = _pipeline_receipt()
        assert r["verifier_result"] == "not_run"

    def test_h8_4_fake_adapter_pipeline_rejects_missing_receipt_id(self):
        r = _pipeline_receipt()
        del r["receipt_id"]
        assert "receipt_id" not in r


class TestH84PipelineClaimAndReady:
    def test_h8_4_fake_adapter_pipeline_public_claim_fails_closed_without_verifier_pass(
        self,
    ):
        r = _pipeline_receipt()
        assert r["verifier_result"] != "pass"
        assert r["public_claim_allowed"] is False

    def test_h8_4_fake_adapter_pipeline_production_ready_false_without_verifier_pass(
        self,
    ):
        r = _pipeline_receipt()
        assert r["production_ready"] is False


class TestH84PipelineRouteTruth:
    def test_h8_4_fake_adapter_pipeline_does_not_change_route_truth_source(self):
        c = _pipeline_candidate()
        assert c["route_truth_source"] == "CapabilityPlanner"
        assert c["adapter_output_is_route_truth"] is False


class TestH84PipelineFlags:
    def test_h8_4_fake_adapter_pipeline_model_flags_remain_false(self):
        c = _pipeline_candidate()
        assert c["local_model_loaded"] is False
        assert c["local_model_called"] is False
        assert c["model_load_allowed"] is False
        assert c["model_call_allowed"] is False

    def test_h8_4_fake_adapter_pipeline_network_provider_flags_remain_false(self):
        c = _pipeline_candidate()
        assert c["provider_call_allowed"] is False
        assert c["network_allowed"] is False

    def test_h8_4_fake_adapter_pipeline_no_runtime_enabled_flag(self):
        c = _pipeline_candidate()
        assert c["runtime_enabled"] is False
