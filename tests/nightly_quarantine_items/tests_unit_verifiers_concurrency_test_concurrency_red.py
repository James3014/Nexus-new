"""Nightly quarantine entry: tests/unit/verifiers/concurrency/test_concurrency_red.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/verifiers/concurrency/test_concurrency_red.py",
    "disposition": "delete-candidate",
    "issue": "#1928",
    "cause": "target fixed in ac87243dc; deadlock no longer reproducible; fixed behaviour pinned by test_deadlock.py",
    "tests": ("TestConcurrencyTargetsRed::test_target3_deadlock_happens",),
}
