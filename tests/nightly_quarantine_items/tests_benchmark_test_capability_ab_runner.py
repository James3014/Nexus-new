"""Nightly quarantine entry: tests/benchmark/test_capability_ab_runner.py (#1926). See package docstring."""

from __future__ import annotations

# Tombstone (#1926): the two learn-metadata hook tests now create their runner under /private/tmp only when it exists, else the platform temp dir, and re-point the hook's sanctioned-root glob at that parent; verified passing in a python:3.12 Linux container.
ENTRY = None
