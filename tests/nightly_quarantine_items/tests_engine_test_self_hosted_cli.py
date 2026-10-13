"""Nightly quarantine entry: tests/engine/test_self_hosted_cli.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_self_hosted_cli.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "passes in isolation on macOS at current main but fails in the Linux full-suite run (order-dependent state pollution or Linux-only environment difference); needs bisect",
    "tests": ("test_self_hosted_approve_exact_binding_and_mismatch",),
}
