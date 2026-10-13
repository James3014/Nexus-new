"""Nightly quarantine entry: tests/unit/local_heal/test_rrl3c_evidence_harness_proof.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_rrl3c_evidence_harness_proof.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: audits generated, gitignored artifacts/runtime evidence (real model call receipts, selected candidates, evidence bundles) that a clean runner lacks; faking them would defeat the audit",
    "tests": (
        "TestOrchestratorHookBehavior::test_committed_bundle_has_task_id",
        "TestOrchestratorHookBehavior::test_runtime_artifact_exists_at_committed_path",
    ),
}
