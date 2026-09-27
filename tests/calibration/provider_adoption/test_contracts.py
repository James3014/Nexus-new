"""Unit tests for G0 Experiment Contract in Provider Adoption Framework."""

import pytest

from nexus.calibration.provider_adoption.contracts import (
    EXPERIMENT_CONTRACT_SCHEMA,
    AuthorityBoundary,
    BaselineIdentity,
    CandidateIdentity,
    CohortType,
    DatasetRef,
    EnvironmentConstraints,
    ExperimentContract,
    MetricsConfig,
    PassThresholds,
    StopConditions,
    build_experiment_contract,
    validate_experiment_contract,
    verify_contract_immutability,
)


def _make_valid_contract(**kwargs) -> ExperimentContract:
    base_kwargs = {
        "experiment_id": "EXP-TEST-001",
        "experiment_revision": 1,
        "candidate": CandidateIdentity("test-provider", "model-v1", "cli", "test_runtime"),
        "baseline": BaselineIdentity("base-provider", "base-model", "cli"),
        "job_to_be_done": "Testing provider qualification",
        "allowed_capabilities": ("CAP-001", "CAP-002"),
        "forbidden_capabilities": ("file_mutation", "process_execution"),
        "dataset": DatasetRef(
            "COHORT-01", 1, "cohort_hash", 1, "gt_hash", 1, CohortType.BENCHMARK_COHORT.value, True
        ),
        "metrics_config": MetricsConfig(500, 2000, 0.05, 1.0),
        "pass_thresholds": PassThresholds(0.8, 0.9, 0.85),
        "stop_conditions": StopConditions(3, 0.2, True, 5),
        "environment_constraints": EnvironmentConstraints("Darwin", "arm64", 8),
        "authority_boundary": AuthorityBoundary(),
        "claim_ceiling": "L0.5",
        "created_at": "2026-09-27T00:00:00Z",
    }
    base_kwargs.update(kwargs)
    return build_experiment_contract(**base_kwargs)


def test_contract_creation_and_hash_binding():
    contract = _make_valid_contract()
    assert contract.schema == EXPERIMENT_CONTRACT_SCHEMA
    assert contract.contract_hash != ""
    assert len(contract.contract_hash) == 64
    validate_experiment_contract(contract)
    assert verify_contract_immutability(contract, contract.contract_hash)


def test_contract_immutability_detects_tampering():
    contract = _make_valid_contract()
    original_hash = contract.contract_hash

    # Tampered with different claim ceiling
    tampered = ExperimentContract(**{**contract.__dict__, "claim_ceiling": "L3"})
    assert not verify_contract_immutability(tampered, original_hash)
    with pytest.raises(ValueError, match="CONTRACT_HASH_MISMATCH"):
        validate_experiment_contract(tampered)


def test_contract_authority_escalation_rejection():
    # Attempting to grant routing authority MUST fail closed
    with pytest.raises(ValueError, match="FORBIDDEN_AUTHORITY_ESCALATION.*routing_authority"):
        _make_valid_contract(authority_boundary=AuthorityBoundary(routing_authority=True))

    # Attempting to grant acceptance authority MUST fail closed
    with pytest.raises(ValueError, match="FORBIDDEN_AUTHORITY_ESCALATION.*acceptance_authority"):
        _make_valid_contract(authority_boundary=AuthorityBoundary(acceptance_authority=True))

    # Attempting to grant write permission MUST fail closed
    with pytest.raises(ValueError, match="FORBIDDEN_AUTHORITY_ESCALATION.*write_permission"):
        _make_valid_contract(authority_boundary=AuthorityBoundary(write_permission=True))

    # Attempting to grant process permission MUST fail closed
    with pytest.raises(ValueError, match="FORBIDDEN_AUTHORITY_ESCALATION.*process_permission"):
        _make_valid_contract(authority_boundary=AuthorityBoundary(process_permission=True))

    # Attempting to grant network permission MUST fail closed
    with pytest.raises(ValueError, match="FORBIDDEN_AUTHORITY_ESCALATION.*network_permission"):
        _make_valid_contract(authority_boundary=AuthorityBoundary(network_permission=True))


def test_contract_capabilities_overlap_rejected():
    """Verify D6: overlap between allowed_capabilities and forbidden_capabilities fails closed."""
    from nexus.calibration.provider_adoption.contracts import validate_contract_capabilities

    # 1. Direct validator check with CAP-* ID overlap
    with pytest.raises(ValueError, match="CAPABILITY_CONSISTENCY_ERROR.*CAP-001"):
        validate_contract_capabilities(
            allowed_capabilities=("CAP-001", "CAP-002"),
            forbidden_capabilities=("CAP-001", "file_mutation"),
        )

    # 2. Direct validator check with effect name overlap
    with pytest.raises(ValueError, match="CAPABILITY_CONSISTENCY_ERROR.*tool_calling"):
        validate_contract_capabilities(
            allowed_capabilities=("CAP-001", "tool_calling"),
            forbidden_capabilities=("tool_calling", "process_execution"),
        )

    # 3. Contract builder check with CAP-* ID overlap
    with pytest.raises(ValueError, match="CAPABILITY_CONSISTENCY_ERROR.*CAP-002"):
        _make_valid_contract(
            allowed_capabilities=("CAP-001", "CAP-002"),
            forbidden_capabilities=("CAP-002", "process_execution"),
        )

    # 4. Valid disjoint sets succeed
    validate_contract_capabilities(
        allowed_capabilities=("CAP-001", "CAP-002"),
        forbidden_capabilities=("CAP-008", "file_mutation", "process_execution"),
    )
