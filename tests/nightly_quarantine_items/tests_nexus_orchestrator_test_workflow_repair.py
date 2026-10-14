"""Nightly quarantine entry: tests/nexus/orchestrator/test_workflow_repair.py (#1928). See package docstring."""

from __future__ import annotations

# Tombstone (#1928): the integrate_approved tests now persist a fully authorized state (a1b77a658, GB-042 fixture) and expect INTEGRATION_FAILED_PRE_APPLY for a pre-apply failure (c956f8f7e).
ENTRY = None
