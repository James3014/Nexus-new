"""Nightly quarantine entry: tests/ops/test_audit_cli_contracts.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/ops/test_audit_cli_contracts.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "passes in isolation on macOS at current main but fails in the Linux full-suite run (order-dependent state pollution or Linux-only environment difference); needs bisect",
    "tests": (
        "test_brain_hub_audit_accepts_output_json_flag",
        "test_render_brain_hub_coverage_accepts_output_json_flag",
    ),
}
