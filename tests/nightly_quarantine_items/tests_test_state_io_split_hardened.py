"""Nightly quarantine entry: tests/test_state_io_split_hardened.py (#1929). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/test_state_io_split_hardened.py",
    "disposition": "quarantine",
    "issue": "#1929",
    "cause": "behavior removed: StateRepository.save is now an atomic overwrite (v26.2), no append history; owner decision",
    "tests": ("test_state_repository_append_mode",),
}
