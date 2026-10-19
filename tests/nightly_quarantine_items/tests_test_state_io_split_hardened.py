"""Nightly quarantine entry: tests/test_state_io_split_hardened.py (#1929). See package docstring."""

from __future__ import annotations

# Tombstone (#1929): test_state_repository_append_mode now asserts the retirement (id kept for the impact gate): StateRepository.save is an atomic overwrite since v26.2 (9f1e9afac); Owner decision on #1929 (2026-10-19, workspace-32).
ENTRY = None
