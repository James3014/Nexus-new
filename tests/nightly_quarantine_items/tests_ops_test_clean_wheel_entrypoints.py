"""Nightly quarantine entry: tests/ops/test_clean_wheel_entrypoints.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/ops/test_clean_wheel_entrypoints.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "passes in isolation on macOS at current main but fails in the Linux full-suite run (order-dependent state pollution or Linux-only environment difference); needs bisect",
    "tests": ("test_clean_wheel_contains_and_runs_registered_cli_entrypoints",),
}
