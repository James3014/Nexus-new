"""Unit tests for BE-Track targeted 14B fallback gate."""
from __future__ import annotations

import os
from pathlib import Path
from nexus.services.local_heal.targeted_fallback import TargetedFallbackGate


def test_targeted_14b_fallback_policy():
    gate = TargetedFallbackGate(Path("/tmp"))

    # 1. Reject if not model-relevant
    eligible, reason = gate.should_fallback("C_15000", "MODEL_SEMANTIC_LIMIT", model_relevant=False)
    assert not eligible
    assert "not model-relevant" in reason

    # 2. Reject if not MODEL_SEMANTIC_LIMIT (e.g. ACTION_PROTOCOL_LIMIT)
    eligible, reason = gate.should_fallback("C_15000", "ACTION_PROTOCOL_LIMIT")
    assert not eligible
    assert "not eligible" in reason

    # 3. Reject if verifier not available
    eligible, reason = gate.should_fallback("C_15000", "MODEL_SEMANTIC_LIMIT", verifier_available=False)
    assert not eligible
    assert "Verifier is not available" in reason

    # 4. Resource blocked when env is True
    os.environ["NEXUS_14B_RESOURCE_BLOCKED"] = "true"
    eligible, reason = gate.should_fallback("C_15000", "MODEL_SEMANTIC_LIMIT")
    assert not eligible
    assert reason == "RESOURCE_BLOCKED"

    status, info = gate.execute_fallback("C_15000", "some_prompt")
    assert status == "RESOURCE_BLOCKED"
    assert not info["success"]

    # 5. Eligible when env is False
    os.environ["NEXUS_14B_RESOURCE_BLOCKED"] = "false"
    eligible, reason = gate.should_fallback("C_15000", "MODEL_SEMANTIC_LIMIT")
    assert eligible
    assert reason == "ELIGIBLE"

    status, info = gate.execute_fallback("C_15000", "some_prompt", run_fallback_simulation=True)
    assert status == "SUCCESS"
    assert info["success"]
    assert "Qwen-14B" in info["model_name"]
    assert "SEARCH" in info["model_output"]
