"""Nightly quarantine entry: tests/nexus/orchestrator/test_target_integration_git_canary.py (#1923). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/nexus/orchestrator/test_target_integration_git_canary.py",
    "disposition": "quarantine-product-bug?",
    "issue": "#1923",
    "cause": "assertion encodes a safety/boundary invariant that the product currently violates; possible real product bug, file a new Issue before fixing",
    "tests": ("test_real_git_staging_failure_and_success_do_not_fake_ancestry",),
}
