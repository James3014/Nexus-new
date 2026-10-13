"""Nightly quarantine entry: tests/engine/test_self_hosted_cli.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_self_hosted_cli.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "fails in isolation too: approve now requires a lifecycle-authorized contract kind (bare CLI submit records NONE) and a one-shot approval grant; needs a grant-issuing fixture in the lifecycle_guards area (#1884)",
    "tests": ("test_self_hosted_approve_exact_binding_and_mismatch",),
}
