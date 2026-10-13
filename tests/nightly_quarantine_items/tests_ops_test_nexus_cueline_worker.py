"""Nightly quarantine entry: tests/ops/test_nexus_cueline_worker.py (#1926). See package docstring."""

from __future__ import annotations

# Fixed in #1928: submit payload supplies the now-mandatory verifier_commands.
# Re-quarantined (#1926): host dependence, not order pollution.
ENTRY: dict[str, object] = {
    "file": "tests/ops/test_nexus_cueline_worker.py",
    "disposition": "quarantine",
    "issue": "#1926",
    "cause": "host-only: the submitted task uses worker=codex and the owned worker starts at once; with no codex CLI on PATH (ubuntu-latest) the attempt fails at worker_execution and status is FINAL_BLOCK, which the test does not accept; with codex installed (Mac host) status is SUBMITTED. Reproduced on the Mac by running the worker with PATH=/usr/bin:/bin. Fails in isolation on Linux; needs a hermetic fake provider binary",
    "tests": ("test_nexus_cueline_worker_full_pipeline_subprocess",),
}
