"""Nightly quarantine entry: tests/unit/local_heal/test_memory_eval_identity_and_path.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_memory_eval_identity_and_path.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: audits generated, gitignored artifacts/runtime evidence (real model call receipts, selected candidates, evidence bundles) that a clean runner lacks; faking them would defeat the audit",
    "tests": (
        "TestArtifactExistence::test_memory_path_matrix_exists",
        "TestArtifactExistence::test_rrl3c_artifacts_exist",
        "TestArtifactExistence::test_rrl3c_bundle_has_required_fields",
    ),
}
