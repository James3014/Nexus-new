"""Nightly quarantine entry: tests/integration/test_june_regression_pack.py (#1926). See package docstring."""

from __future__ import annotations

# Tombstone (#1926): the governance-integrity test now runs run_pack against empty git workspaces in tmp_path with results_dir in tmp_path; all nine governance gates still apply.
ENTRY = None
