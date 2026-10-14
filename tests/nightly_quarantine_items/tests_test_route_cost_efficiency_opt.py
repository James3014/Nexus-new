"""Nightly quarantine entry: tests/test_route_cost_efficiency_opt.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/test_route_cost_efficiency_opt.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "stale, not host state: even with a tmp project_root (the hard-coded /Users/jameschen/Workspace/nexus fails first with PermissionError on any other host), BattlesuitGateway.ask_structured now fails closed with {'status': 'FAILED', 'error': 'online_execution_not_authorized'} (not FAIL/REJECTED) and returns no shadow_compaction_ratio telemetry, so the observation-only compaction expectation drifted from the gateway authority gate; needs owner fix-or-delete decision",
    "tests": ("test_context_compaction_is_observation_only",),
}
