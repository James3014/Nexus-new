"""Nightly quarantine entry: tests/ops/test_nexus_cueline_worker.py (#1926). See package docstring."""

from __future__ import annotations

# Tombstone (#1926): the full-pipeline test now puts a fake codex CLI first on PATH (on the worker's env allowlist); the fake holds the worker in WORKER_RUNNING until the test writes a release file next to its directory, the test waits for the fake to exit, and NEXUS_TARGET_ROOT_OVERRIDE pins the target worktree inside tmp_path (the service ignores roots containing "/tmp" and would otherwise write to <cwd>/../nexus-runtime-targets), so no real codex is needed or launched and no process outlives the test; verified on Linux (python:3.12, no codex) and macOS.
ENTRY = None
