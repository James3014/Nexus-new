"""Nightly quarantine entry: tests/engine/test_self_hosted_cli.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_self_hosted_cli.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": (
        "approve: 6fa83c25c (#1758) requires an approval grant on every approve surface, but "
        "run_self_hosted_approve (scripts/engine/commands/self_hosted_actions.py) has no grant input "
        "and never passes approval_context, so the CLI always fails (APPROVAL_GRANT_REQUIRED); with "
        "the autouse set_test_runner fixture CUSTOM_RUNNER_PRODUCTION_CLAIM_FORBIDDEN (5e47e0820) "
        "fires first. Owner decision: add a grant-bearing CLI approve option or retire CLI approve"
    ),
    # list_actionable fixed (#1928): it now waits for the worker thread before listing.
    "tests": ("test_self_hosted_approve_exact_binding_and_mismatch",),
}
