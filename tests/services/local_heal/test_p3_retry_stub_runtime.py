from __future__ import annotations

import os

import pytest
from unittest.mock import patch

from nexus.services.local_heal.p3_local_retry_stub_runtime import (
    P3RetryStubRuntimeReceipt,
    RealLocalRetry,
    compute_p3_retry_stub_runtime,
    DEFAULT_CASCADE_MODELS,
)


def test_compute_p3_retry_stub_runtime_invoked_true() -> None:
    metadata = {"p3_cheap_verifier_result": "not_run_shadow_only"}
    receipt = compute_p3_retry_stub_runtime(metadata)
    assert receipt.retry_invoked is True
    assert receipt.authority == "runtime_enabled"


def test_compute_p3_retry_stub_runtime_cascade_3_models() -> None:
    metadata = {"p3_cheap_verifier_result": "not_run_shadow_only"}
    receipt = compute_p3_retry_stub_runtime(metadata)
    assert len(receipt.cascade_models_invoked) == 3
    assert receipt.cascade_models_invoked == list(DEFAULT_CASCADE_MODELS)


def test_compute_p3_retry_stub_runtime_no_real_call() -> None:
    metadata = {"p3_cheap_verifier_result": "not_run_shadow_only"}
    with patch(
        "nexus.services.local_heal.p3_local_retry_stub_runtime.compute_p3_local_retry"
    ) as mock_retry:
        mock_retry.return_value = type("FakeRetry", (), {
            "enabled": True, "authority": "shadow_only",
            "retry_trigger": "not_run_shadow_only", "retry_planned": True,
            "retry_invoked": False, "cascade_models_planned": [],
            "cascade_models_invoked": [], "retry_candidate_generated": False,
            "retry_candidate_hash": "", "full_verifier_required": True,
            "claim_gate_required": True, "solved_claim_allowed": False,
            "public_claim_allowed": False, "runtime_behavior_changed": False,
            "blocked_reason": "", "reason": "test",
        })()
        receipt = compute_p3_retry_stub_runtime(metadata)
        mock_retry.assert_called_once()
        assert receipt.retry_invoked is True


class TestRealLocalRetry:
    def test_ollama_disabled_returns_stub(self) -> None:
        if "NEXUS_OLLAMA_ENABLED" in os.environ:
            del os.environ["NEXUS_OLLAMA_ENABLED"]
        retry = RealLocalRetry()
        metadata = {"p3_cheap_verifier_result": "not_run_shadow_only"}
        receipt = retry.compute_p3_retry_stub_runtime(metadata)
        assert isinstance(receipt, P3RetryStubRuntimeReceipt)

    def test_ollama_enabled_cascade_3_models(self) -> None:
        os.environ["NEXUS_OLLAMA_ENABLED"] = "1"
        retry = RealLocalRetry()
        assert retry.ollama_enabled is True
        assert len(retry.CASCADE_MODELS) == 3
        metadata = {"p3_cheap_verifier_result": "not_run_shadow_only"}
        receipt = retry.compute_p3_retry_stub_runtime(metadata)
        assert receipt.retry_invoked is True
        assert receipt.cascade_models_invoked == list(DEFAULT_CASCADE_MODELS)
        del os.environ["NEXUS_OLLAMA_ENABLED"]

    def test_existing_p1c_still_works(self) -> None:
        metadata = {"p3_cheap_verifier_result": "not_run_shadow_only"}
        receipt = compute_p3_retry_stub_runtime(metadata)
        assert receipt.retry_invoked is True
