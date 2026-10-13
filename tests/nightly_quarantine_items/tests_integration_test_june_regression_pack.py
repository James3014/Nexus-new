"""Nightly quarantine entry: tests/integration/test_june_regression_pack.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_june_regression_pack.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: run_pack replays real astropy/sympy workspaces (hard-coded /Users/jameschen/.../.nexus/workspaces/astropy venvs and external_sources checkouts) that a clean runner lacks; faking them would defeat the governance-integrity check",
    "tests": ("test_june_regression_pack_governance_integrity",),
}
