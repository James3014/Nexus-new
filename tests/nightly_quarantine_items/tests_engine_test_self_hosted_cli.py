"""Nightly quarantine entry: tests/engine/test_self_hosted_cli.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_self_hosted_cli.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "fails in isolation too: approve now requires a lifecycle-authorized contract kind (bare CLI submit records NONE) and a one-shot approval grant; needs a grant-issuing fixture in the lifecycle_guards area (#1884). list_actionable (host-only, #1926): the submitted task uses worker=codex and the owned worker starts at once; without a codex CLI (ubuntu-latest) it ends FINAL_BLOCK/WORKER_EXECUTION_FAILED before list-actionable runs, so actionable_count is 0 (reproduced in a python:3.12 Linux container; same error_sha256 e59255bf as the cueline worker test)",
    "tests": (
        "test_self_hosted_approve_exact_binding_and_mismatch",
        "test_self_hosted_list_actionable_empty_and_populated",
    ),
}
