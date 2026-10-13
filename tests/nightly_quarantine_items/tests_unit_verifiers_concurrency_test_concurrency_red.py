"""Nightly quarantine entry: tests/unit/verifiers/concurrency/test_concurrency_red.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/verifiers/concurrency/test_concurrency_red.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "timing-dependent RED demonstration (expects a deadlock within a fixed sleep); flaky on shared runners",
    "tests": ("TestConcurrencyTargetsRed::test_target3_deadlock_happens",),
}
