"""Nightly quarantine entry: tests/integration/test_pipeline_e2e.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_pipeline_e2e.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy NexusEngine (archived 2026-10-13, scheduled for deletion): after fixing the phase mocks the R stage routes to the swarm proxy / local repair and the audit loop never approves; no production caller, so not worth re-mocking",
    "tests": ("test_full_chain_cli_to_engine",),
}
