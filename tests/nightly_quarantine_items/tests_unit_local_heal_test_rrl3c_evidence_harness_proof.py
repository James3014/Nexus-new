"""Nightly quarantine entry: tests/unit/local_heal/test_rrl3c_evidence_harness_proof.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_rrl3c_evidence_harness_proof.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: the two ids read cwd-relative, gitignored artifacts/runtime/rrl3_runtime_evidence_harness_integration_v0/runs/unknown/{evidence_bundle,bottleneck_classification}.json from a real harness run; a clean runner lacks them and faking them would defeat the audit (the other ids in the file are hermetic and pass)",
    "tests": (
        "TestOrchestratorHookBehavior::test_committed_bundle_has_task_id",
        "TestOrchestratorHookBehavior::test_runtime_artifact_exists_at_committed_path",
    ),
}
