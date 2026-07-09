from __future__ import annotations

import pytest
from unittest.mock import patch

from nexus.services.local_heal.p3_local_cheap_verifier_runtime import (
    P3CheapVerifierRuntimeReceipt,
    compute_p3_cheap_verifier_runtime,
)


def test_compute_p3_cheap_verifier_runtime_invoked_true() -> None:
    metadata = {"p3_cloud_stub_candidate_generated": True}
    receipt = compute_p3_cheap_verifier_runtime(metadata)
    assert receipt.cheap_verifier_invoked is True
    assert receipt.authority == "runtime_enabled"


def test_compute_p3_cheap_verifier_runtime_behavior_changed_true() -> None:
    metadata = {"p3_cloud_stub_candidate_generated": True}
    receipt = compute_p3_cheap_verifier_runtime(metadata)
    assert receipt.runtime_behavior_changed is True


def test_compute_p3_cheap_verifier_runtime_no_real_call() -> None:
    metadata = {"p3_cloud_stub_candidate_generated": True}
    with patch(
        "nexus.services.local_heal.p3_local_cheap_verifier_runtime.compute_p3_cheap_verifier"
    ) as mock_verifier:
        mock_verifier.return_value = type("FakeVerifier", (), {
            "enabled": True, "authority": "shadow_only",
            "candidate_available": True, "canonical_candidate_hash": "",
            "cheap_verifier_planned": True, "cheap_verifier_invoked": False,
            "cheap_verifier_result": "not_run_shadow_only",
            "cheap_verifier_confidence": 0.0, "full_verifier_required": True,
            "claim_gate_required": True, "solved_claim_allowed": False,
            "public_claim_allowed": False, "runtime_behavior_changed": False,
            "blocked_reason": "", "reason": "test",
        })()
        receipt = compute_p3_cheap_verifier_runtime(metadata)
        mock_verifier.assert_called_once()
        assert receipt.cheap_verifier_invoked is True
