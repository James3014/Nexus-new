"""Serve GB019 advisory-path witnesses a policy where the 3B advisor is admitted.

The planner emits the non-mutating ``compact_diagnosis`` role, whose only
admitted worker was ``local_advisor_3b``. The live policy marks that worker
``INSTALLED_NOT_CONNECTED`` (not present on M5 Ollama, 2026-10-12), so the
advisory-delivery behaviour these witnesses verify is exercised against a
temporary copy of the live policy with only that worker's state and reason
reverted. The live policy file is never modified.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

LIVE_POLICY = Path(__file__).resolve().parents[1] / "nexus" / "config" / "model_workforce.yaml"

_ADVISORY_TESTS = frozenset({
    "test_gateway_unified_hybrid_uses_real_local_assist_and_shared_planner",
    "test_gb019_advisory_verifier_failure_keeps_public_delivery",
    "test_gb019_fail_closed_override_blocks_public_online",
    "test_gb019_public_guard_negative_controls",
    "test_advisory_guard_cannot_block_delivery_yet",
    "test_gb019_advisory_failure_does_not_block_delivery_or_claim",
    "test_gb019_blocking_override_fails_closed",
})


@pytest.fixture(autouse=True)
def pre_m5_advisor_policy(request: pytest.FixtureRequest, monkeypatch, tmp_path: Path) -> None:
    if request.node.originalname not in _ADVISORY_TESTS:
        return
    from nexus_runtime.planning.services import model_workforce_policy as mwp

    data = yaml.safe_load(LIVE_POLICY.read_text(encoding="utf-8"))
    advisor = data["workers"]["local_advisor_3b"]
    advisor["state"] = "LOCAL_CONDITIONAL"
    advisor.pop("reason", None)
    patched = tmp_path / "model_workforce_pre_m5_advisor.yaml"
    patched.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    original_init = mwp.WorkforcePolicyLoader.__init__

    def init(self, policy_path=None):
        if policy_path is not None and Path(policy_path).resolve() == LIVE_POLICY.resolve():
            policy_path = patched
        original_init(self, policy_path)

    monkeypatch.setattr(mwp.WorkforcePolicyLoader, "__init__", init)
