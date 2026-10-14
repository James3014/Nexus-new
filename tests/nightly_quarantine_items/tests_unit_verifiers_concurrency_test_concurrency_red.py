"""Nightly quarantine entry: tests/unit/verifiers/concurrency/test_concurrency_red.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/verifiers/concurrency/test_concurrency_red.py",
    "disposition": "delete-candidate",
    "issue": "#1928",
    "cause": (
        "red-phase test that asserts the AB/BA deadlock still happens; the target was fixed in "
        "ac87243dc and test_deadlock.py pins the fixed behaviour, so the assertion can never pass "
        "again. Removing a test id needs an Owner-approved deletion (Core deletion_policy=FORBID)"
    ),
    "tests": ("TestConcurrencyTargetsRed::test_target3_deadlock_happens",),
}
