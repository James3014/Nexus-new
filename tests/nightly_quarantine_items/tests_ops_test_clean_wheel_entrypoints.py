"""Nightly quarantine entry: tests/ops/test_clean_wheel_entrypoints.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/ops/test_clean_wheel_entrypoints.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "console script nexus-cueline-worker dropped in #770; restore needs a trusted dependency snapshot transition (pyproject change) — separate PR",
    "tests": ("test_clean_wheel_contains_and_runs_registered_cli_entrypoints",),
}
