"""Unit tests for Requalification Policy in Provider Adoption Framework."""

from dataclasses import replace

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


def _requalification_base_identity():
    return inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        model_generation="model-gen-1",
        timestamp="2026-09-27T00:00:00Z",
    )


def test_requalification_transport_and_source_drift_are_stale():
    base = _requalification_base_identity()
    current = replace(
        base,
        transport="other_cli",
        source_commit_identity="f" * 40,
    )
    res = evaluate_requalification(
        experiment_id="EXP-TRANSPORT-SOURCE",
        baseline_identity=base,
        current_identity=current,
    )
    assert res.overall_verdict == RequalificationVerdict.STALE
    assert {d.dimension_name for d in res.dimensions} == {
        "transport",
        "source_commit_identity",
    }


def test_requalification_model_generation_drift_requires_full_requalification():
    base = _requalification_base_identity()
    res = evaluate_requalification(
        experiment_id="EXP-MODEL-GEN",
        baseline_identity=base,
        current_identity=replace(base, model_generation="model-gen-2"),
    )
    assert res.overall_verdict == RequalificationVerdict.REQUALIFICATION_REQUIRED
    assert res.requires_full_requalification is True


def test_requalification_kernel_and_architecture_drift_are_stale():
    base = _requalification_base_identity()
    res = evaluate_requalification(
        experiment_id="EXP-HOST-DRIFT",
        baseline_identity=base,
        current_identity=replace(base, kernel_version="new-kernel", architecture="other-arch"),
    )
    assert res.overall_verdict == RequalificationVerdict.STALE
    assert {d.dimension_name for d in res.dimensions} == {"kernel_version", "architecture"}
