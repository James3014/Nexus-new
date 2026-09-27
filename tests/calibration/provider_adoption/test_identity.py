"""Unit tests for G1 Physical Identity module in Provider Adoption Framework."""

from nexus.calibration.provider_adoption.identity import (
    PHYSICAL_IDENTITY_SCHEMA,
    UNKNOWN,
    evaluate_identity_drift,
    inspect_physical_host_identity,
)


def test_physical_identity_inspection_and_digest():
    ident = inspect_physical_host_identity(
        provider_id="test-provider",
        model_id="test-model",
        transport="test_transport",
        runtime_executable=UNKNOWN,
        runtime_version="1.0.0",
        timestamp="2026-09-27T00:00:00Z",
    )
    assert ident.schema == PHYSICAL_IDENTITY_SCHEMA
    assert ident.provider_id == "test-provider"
    assert ident.model_id == "test-model"
    assert ident.identity_digest != ""
    assert len(ident.identity_digest) == 64
    assert ident.compute_digest() == ident.identity_digest


def test_identity_digest_ignores_observation_timestamp():
    first = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        timestamp="2026-09-27T00:00:00Z",
    )
    later = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        timestamp="2026-09-27T01:00:00Z",
    )
    assert first.timestamp != later.timestamp
    assert first.identity_digest == later.identity_digest


def test_identity_digest_ignores_later_offline_network_observation():
    unknown = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        timestamp="2026-09-27T00:00:00Z",
        offline_verified=None,
        network_dependency_observed="UNKNOWN",
    )
    verified = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        timestamp="2026-09-27T01:00:00Z",
        offline_verified=True,
        network_dependency_observed="NONE",
    )
    assert unknown.identity_digest == verified.identity_digest
    assert unknown.offline_availability != verified.offline_availability
    assert unknown.network_dependency != verified.network_dependency


def test_offline_status_honest_preservation_fix_6_1():
    """Verify Invariant 6.1: offline_availability defaults to UNKNOWN, never guessed."""
    ident = inspect_physical_host_identity(
        provider_id="apple-fm",
        model_id="default",
        transport="cli",
        timestamp="2026-09-27T00:00:00Z",
    )
    # Must NOT be VERIFIED_OFFLINE merely because provider is apple-fm
    assert ident.offline_availability == UNKNOWN
    assert ident.network_dependency == UNKNOWN

    # Only when explicitly verified physically:
    verified_ident = inspect_physical_host_identity(
        provider_id="apple-fm",
        model_id="default",
        transport="cli",
        timestamp="2026-09-27T00:00:00Z",
        offline_verified=True,
        network_dependency_observed="NONE",
    )
    assert verified_ident.offline_availability == "VERIFIED_OFFLINE"
    assert verified_ident.network_dependency == "NONE"


def test_identity_drift_evaluation():
    base = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        timestamp="2026-09-27T00:00:00Z",
    )

    # Identical baseline
    curr_same = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        timestamp="2026-09-27T00:00:00Z",
    )
    assert evaluate_identity_drift(base, curr_same) == "CURRENT"

    # Model ID changed -> REQUALIFICATION_REQUIRED
    curr_model_drift = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-2",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v1",
        timestamp="2026-09-27T00:00:00Z",
    )
    assert evaluate_identity_drift(base, curr_model_drift) == "REQUALIFICATION_REQUIRED"

    # Adapter generation updated -> STALE
    curr_adapter_drift = inspect_physical_host_identity(
        provider_id="provider-a",
        model_id="model-1",
        transport="cli",
        runtime_executable="/bin/echo",
        runtime_version="1.0.0",
        adapter_generation="v2",
        timestamp="2026-09-27T00:00:00Z",
    )
    assert evaluate_identity_drift(base, curr_adapter_drift) == "STALE"
