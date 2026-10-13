"""Nightly quarantine entry: tests/unit/test_fast_matcher_exist.py (#1927). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/test_fast_matcher_exist.py",
    "disposition": "quarantine",
    "issue": "#1927",
    "cause": "needs the Rust nexus_core extension (target/release), which the nightly runner does not build; decide build-in-CI or delete",
    "tests": (
        "test_fast_matcher_metadata_exists",
        "test_fast_matcher_module_exists",
        "test_fast_scan_callable",
    ),
}
