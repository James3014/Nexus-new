"""Nightly quarantine entry: tests/unit/test_fast_matcher_drift.py (#1927). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/test_fast_matcher_drift.py",
    "disposition": "quarantine",
    "issue": "#1927",
    "cause": "needs the Rust nexus_core extension (target/release), which the nightly runner does not build; decide build-in-CI or delete",
    "tests": ("test_fast_matcher_drift_zero",),
}
