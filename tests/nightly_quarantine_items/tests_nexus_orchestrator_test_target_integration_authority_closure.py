"""Nightly quarantine entry: tests/nexus/orchestrator/test_target_integration_authority_closure.py (#1923). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/nexus/orchestrator/test_target_integration_authority_closure.py",
    "disposition": "quarantine-product-bug?",
    "issue": "#1923",
    "cause": "assertion encodes a safety/boundary invariant that the product currently violates; possible real product bug, file a new Issue before fixing",
    "tests": ("test_owner_finish_delegates_full_authorized_integration_then_cleanup",),
}
