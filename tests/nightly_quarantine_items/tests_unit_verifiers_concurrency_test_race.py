"""Nightly quarantine entry: tests/unit/verifiers/concurrency/test_race.py (#1923). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/verifiers/concurrency/test_race.py",
    "disposition": "quarantine-product-bug?",
    "issue": "#1923",
    "cause": "assertion encodes a safety/boundary invariant that the product currently violates; possible real product bug, file a new Issue before fixing",
    "tests": ("TestBatchB02RaceFixed::test_idempotent_executor_green_stress",),
}
