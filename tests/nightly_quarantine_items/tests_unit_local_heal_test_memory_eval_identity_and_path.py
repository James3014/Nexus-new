"""Nightly quarantine entry: tests/unit/local_heal/test_memory_eval_identity_and_path.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_memory_eval_identity_and_path.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: the three TestArtifactExistence ids read cwd-relative, gitignored artifacts/runtime/rrl3_runtime_evidence_harness_integration_v0/runs/unknown/{evidence_bundle,bottleneck_classification,missing_fields,runtime_invariance}.json and artifacts/runtime/memory_eval_0_path_audit_v0/memory_path_matrix.json from real harness runs; a clean runner lacks them and faking them would defeat the audit (the other ids in the file are hermetic and pass)",
    "tests": (
        "TestArtifactExistence::test_memory_path_matrix_exists",
        "TestArtifactExistence::test_rrl3c_artifacts_exist",
        "TestArtifactExistence::test_rrl3c_bundle_has_required_fields",
    ),
}
