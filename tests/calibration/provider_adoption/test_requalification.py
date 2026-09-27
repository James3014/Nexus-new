"""Unit tests for Requalification Policy in Provider Adoption Framework."""

from nexus.calibration.provider_adoption.identity import inspect_physical_host_identity
from nexus.calibration.provider_adoption.requalification import (
    RequalificationVerdict,
    evaluate_requalification,
)


def test_requalification_current_when_identical():
    ident1 = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        timestamp="2026-09-27T00:00:00Z",
    )
    ident2 = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        timestamp="2026-09-27T00:00:00Z",
    )
    res = evaluate_requalification(
        experiment_id="EXP-1",
        baseline_identity=ident1,
        current_identity=ident2,
    )
    assert res.overall_verdict == RequalificationVerdict.CURRENT
    assert not res.requires_full_requalification


def test_requalification_model_drift_requires_requalification():
    base = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        timestamp="2026-09-27T00:00:00Z",
    )
    current = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-2",  # changed
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        timestamp="2026-09-27T00:00:00Z",
    )
    res = evaluate_requalification(
        experiment_id="EXP-1",
        baseline_identity=base,
        current_identity=current,
    )
    assert res.overall_verdict == RequalificationVerdict.REQUALIFICATION_REQUIRED
    assert res.requires_full_requalification is True


def test_requalification_adapter_generation_drift_is_stale():
    base = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        timestamp="2026-09-27T00:00:00Z",
    )
    current = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v2",  # changed
        timestamp="2026-09-27T00:00:00Z",
    )
    res = evaluate_requalification(
        experiment_id="EXP-1",
        baseline_identity=base,
        current_identity=current,
    )
    assert res.overall_verdict == RequalificationVerdict.STALE
    assert res.requires_full_requalification is False
