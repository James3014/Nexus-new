"""Nightly quarantine entry: tests/test_route_cost_efficiency_opt.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/test_route_cost_efficiency_opt.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "stale, not host state: BattlesuitGateway.ask_structured now fails closed with online_execution_not_authorized and returns no shadow_compaction_ratio telemetry, so the observation-only compaction expectation drifted from the gateway authority gate; needs owner fix-or-delete decision (project_root path was also host-specific)",
    "tests": ("test_context_compaction_is_observation_only",),
}
