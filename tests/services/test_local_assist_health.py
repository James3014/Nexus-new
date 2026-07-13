from __future__ import annotations

from nexus.services.local_assist_health import run_local_assist_health_checks


def test_all_operational_health_checks_pass_when_dependencies_are_present(tmp_path) -> None:
    report = run_local_assist_health_checks(
        workspace_root=tmp_path,
        ollama_available=True,
        model_available=True,
        provider_adapter_available=True,
        candidate_isolation_available=True,
        verifier_environment_available=True,
        receipt_storage_available=True,
        workspace_revision_integrity=True,
    )
    assert report["status"] == "HEALTHY"
    assert all(item["status"] == "PASS" for item in report["checks"].values())


def test_missing_dependency_is_degraded_and_not_ready(tmp_path) -> None:
    report = run_local_assist_health_checks(
        workspace_root=tmp_path,
        ollama_available=False,
        model_available=False,
        provider_adapter_available=True,
        candidate_isolation_available=True,
        verifier_environment_available=True,
        receipt_storage_available=True,
        workspace_revision_integrity=False,
    )
    assert report["status"] == "DEGRADED"
    assert report["production_ready"] is False
    assert report["public_claim_allowed"] is False
    assert report["checks"]["ollama_availability"]["status"] == "FAIL"
    assert report["checks"]["workspace_revision_integrity"]["status"] == "FAIL"
