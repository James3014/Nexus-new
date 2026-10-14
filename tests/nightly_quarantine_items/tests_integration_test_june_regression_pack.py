"""Nightly quarantine entry: tests/integration/test_june_regression_pack.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_june_regression_pack.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: scripts/local_heal/run_june_regression_pack.run_pack(replay_mode='mock_oracle') replays real workspaces under the repo root: .nexus/workspaces/astropy with its .venv_12907/bin/python (astropy C extensions built for python3.11) and artifacts/external_sources/sympy_13852; a clean checkout has none, so every case fails with 'Environment sync failed ... ensurepip failed' (re-checked 2026-10-14); faking them would defeat the governance-integrity check",
    "tests": ("test_june_regression_pack_governance_integrity",),
}
