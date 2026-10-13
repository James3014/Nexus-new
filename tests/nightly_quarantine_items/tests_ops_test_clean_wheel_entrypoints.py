"""Nightly quarantine entry: tests/ops/test_clean_wheel_entrypoints.py (#1928). See package docstring."""

from __future__ import annotations

# Tombstone (#1928): the test now runs the cueline worker as a module from the clean wheel; the console script stays retired (#770, no CueLine consumer).
ENTRY = None
