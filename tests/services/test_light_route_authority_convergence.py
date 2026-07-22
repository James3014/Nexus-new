"""Task R2: Light Route Authority Convergence Test Suite.

Proves that parallel light route implementation (`nexus.services.nexus_light_core`)
is removed and that light route classification and execution rely solely on existing
authorities (`LiteRouteOracle`, `CapabilityPlanner`, `CapabilityRegistry`, `UnifiedRuntime`).
"""

from __future__ import annotations

import importlib.util

from nexus.core.lite_route_oracle import should_use_lite_route
from nexus.services.online_nexus_context import evaluate_postflight_gate


def test_nexus_light_core_not_importable() -> None:
    """Check 1: nexus.services.nexus_light_core must not exist or be importable."""
    spec = importlib.util.find_spec("nexus.services.nexus_light_core")
    assert spec is None, "nexus.services.nexus_light_core must not exist in codebase"


def test_legacy_light_route_flags_do_not_bypass_postflight_gates() -> None:
    """Check 2 & 4: Postflight claim and delivery gates must fail closed without real invocation.

    Legacy route flags ('nexus_light', 'deterministic_core') must not satisfy claim or delivery gates.
    """
    context_without_invocation = {
        "task_id": "r2-test-task-001",
        "verifier": {
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_task_id": "r2-test-task-001",
            "source_hash": "a" * 64,
            "verifier_source_hash": "a" * 64,
            "verifier_artifact": "sha256:" + ("b" * 64),
        },
        "capability_evidence_bundle": {
            "source_hash": "a" * 64,
        },
        "artifact_hash": "a" * 64,
        "online": {"invoked": False},
        "local": {"invoked": False},
        "route": {"nexus_light": True, "deterministic_core": True},
    }

    claim_gate_res = evaluate_postflight_gate("claim_gate", context_without_invocation)
    assert claim_gate_res["gate_passed"] is False
    assert "online_not_invoked" in claim_gate_res.get("blockers", [])

    delivery_gate_res = evaluate_postflight_gate("delivery_gate", context_without_invocation)
    assert delivery_gate_res["gate_passed"] is False
    assert "online_not_invoked" in delivery_gate_res.get("blockers", [])


def test_lite_route_oracle_authority() -> None:
    """Check 5: Existing LiteRouteOracle correctly classifies low-risk vs high-risk tasks."""
    low_risk = should_use_lite_route(
        risk_level="LOW",
        impact_complexity=1.0,
        belief_confidence=0.9,
    )
    assert low_risk.is_lite is True
    assert low_risk.reason == "auto_lite_low_risk_low_complexity"

    high_risk = should_use_lite_route(
        risk_level="HIGH",
        impact_complexity=4.0,
        belief_confidence=0.9,
    )
    assert high_risk.is_lite is False
    assert high_risk.reason == "standard_heavy_route_blocked_lite"


def test_capability_registry_authority() -> None:
    """Check 6: Mainchain capability handlers are fetched from CapabilityRegistry authority."""
    from nexus.services.capability_registry import build_default_mainchain_invokers

    invokers = build_default_mainchain_invokers(include_postflight_gates=True)
    assert "codeintel" in invokers
    assert "artifact_gate" in invokers
    assert "claim_gate" in invokers
    assert "delivery_gate" in invokers
