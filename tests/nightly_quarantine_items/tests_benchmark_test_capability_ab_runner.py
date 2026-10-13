"""Nightly quarantine entry: tests/benchmark/test_capability_ab_runner.py (#1926). See package docstring."""

from __future__ import annotations

# Re-quarantined under #1926: host-only (#1928 had fixed stale expectations (#453 fail-closed gates, d9a3bb0e3 signal_snapshot, h6_13 report quote) and a PEP 765 fallback for Python < 3.14, but the test still depends on the host).
ENTRY: dict[str, object] = {
    "file": "tests/benchmark/test_capability_ab_runner.py",
    "disposition": "quarantine",
    "issue": "#1926",
    "cause": "host-only (macOS): the sanitized-runner metadata hook (scripts/bench/build_sanitized_runner.py) only acts on runner roots matching /private/tmp/nexus-live-clean-runner-*, so the tests create their runner under /private/tmp, which does not exist on Linux (FileNotFoundError on ubuntu-latest); pass on the Mac host",
    "tests": (
        "test_sanitized_runner_learn_metadata_hook_commits_only_allowed_files",
        "test_sanitized_runner_learn_metadata_hook_does_not_hide_other_dirty_entries",
    ),
}
