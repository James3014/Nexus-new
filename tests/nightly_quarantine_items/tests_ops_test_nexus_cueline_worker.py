"""Nightly quarantine entry: tests/ops/test_nexus_cueline_worker.py (#1926). See package docstring."""

from __future__ import annotations

# Tombstone (#1926): the full-pipeline test now puts a fake codex CLI first on PATH (and in NEXUS_CODEX_BIN) that holds the worker in WORKER_RUNNING until released, so it no longer needs, or launches, a real codex; verified passing in a python:3.12 Linux container with no codex.
ENTRY = None
