"""Nightly quarantine entry: tests/ops/test_nexus_p30_acceptance_gate.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/ops/test_nexus_p30_acceptance_gate.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "passes in isolation on macOS at current main but fails in the Linux full-suite run (order-dependent state pollution or Linux-only environment difference); needs bisect",
    "tests": ("test_p30_acceptance_gate_can_block_only_on_required_flash",),
}
