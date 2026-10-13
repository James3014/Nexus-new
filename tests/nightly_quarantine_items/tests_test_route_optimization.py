"""Nightly quarantine entry: tests/test_route_optimization.py (#1929). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/test_route_optimization.py",
    "disposition": "quarantine",
    "issue": "#1929",
    "cause": "behavior removed: CapabilityAssembler no longer does risk/rule-driven lazy activation (assemble_chains(flow) only); owner decision",
    "tests": (
        "TestRouteOptimization::test_risk_driven_lazy_activation",
        "TestRouteOptimization::test_rule_driven_lazy_activation",
    ),
}
