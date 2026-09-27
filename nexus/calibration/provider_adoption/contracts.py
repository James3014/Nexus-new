"""G0 Experiment Contract for Provider Adoption Experiments.

Schema: nexus.provider_experiment.contract.v1
This contract defines the immutable parameters, authority boundaries, dataset references,
pass thresholds, stop conditions, and claim ceilings for evaluating a model provider candidate.

Strict Invariants:
1. An experiment contract SHALL NEVER grant routing authority or acceptance authority.
2. An experiment contract SHALL NEVER grant file mutation, process spawning, or network permissions to candidate models.
3. Every contract has a deterministic SHA-256 hash. Any change to thresholds, datasets, or boundaries requires a new revision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nexus.calibration.provider_adoption.canonical_json import canonical_json_hash

EXPERIMENT_CONTRACT_SCHEMA = "nexus.provider_experiment.contract.v1"


class CohortType(str, Enum):
    FIXTURE_COHORT = "FIXTURE_COHORT"
    BENCHMARK_COHORT = "BENCHMARK_COHORT"
    PHYSICAL_HISTORICAL_COHORT = "PHYSICAL_HISTORICAL_COHORT"


@dataclass(frozen=True)
class CandidateIdentity:
    provider_id: str
    model_id: str
    transport: str
    runtime: str
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "transport": self.transport,
            "runtime": self.runtime,
            "options": dict(self.options),
        }


@dataclass(frozen=True)
class BaselineIdentity:
    provider_id: str
    model_id: str
    transport: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "transport": self.transport,
        }


@dataclass(frozen=True)
class DatasetRef:
    cohort_id: str
    cohort_revision: int
    cohort_sha256: str
    ground_truth_revision: int
    ground_truth_sha256: str
    leakage_policy_revision: int
    cohort_type: str = CohortType.BENCHMARK_COHORT.value
    ground_truth_ready: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "cohort_revision": self.cohort_revision,
            "cohort_sha256": self.cohort_sha256,
            "ground_truth_revision": self.ground_truth_revision,
            "ground_truth_sha256": self.ground_truth_sha256,
            "leakage_policy_revision": self.leakage_policy_revision,
            "cohort_type": self.cohort_type,
            "ground_truth_ready": self.ground_truth_ready,
        }


@dataclass(frozen=True)
class MetricsConfig:
    latency_p50_max_ms: int
    latency_p95_max_ms: int
    max_error_rate: float
    min_throughput_rps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency_p50_max_ms": self.latency_p50_max_ms,
            "latency_p95_max_ms": self.latency_p95_max_ms,
            "max_error_rate": self.max_error_rate,
            "min_throughput_rps": self.min_throughput_rps,
        }


@dataclass(frozen=True)
class PassThresholds:
    accuracy_min: float
    format_compliance_min: float
    semantic_correctness_min: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "accuracy_min": self.accuracy_min,
            "format_compliance_min": self.format_compliance_min,
            "semantic_correctness_min": self.semantic_correctness_min,
        }


@dataclass(frozen=True)
class StopConditions:
    max_consecutive_failures: int
    max_error_rate: float
    safety_abort_on_timeout: bool
    max_total_failures: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_consecutive_failures": self.max_consecutive_failures,
            "max_error_rate": self.max_error_rate,
            "safety_abort_on_timeout": self.safety_abort_on_timeout,
            "max_total_failures": self.max_total_failures,
        }


@dataclass(frozen=True)
class EnvironmentConstraints:
    required_os: str
    required_arch: str
    min_memory_gb: int
    allow_network: bool = False
    require_offline: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_os": self.required_os,
            "required_arch": self.required_arch,
            "min_memory_gb": self.min_memory_gb,
            "allow_network": self.allow_network,
            "require_offline": self.require_offline,
        }


@dataclass(frozen=True)
class AuthorityBoundary:
    write_permission: bool = False
    process_permission: bool = False
    network_permission: bool = False
    tool_permission: bool = False
    routing_authority: bool = False
    acceptance_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "write_permission": self.write_permission,
            "process_permission": self.process_permission,
            "network_permission": self.network_permission,
            "tool_permission": self.tool_permission,
            "routing_authority": self.routing_authority,
            "acceptance_authority": self.acceptance_authority,
        }


@dataclass(frozen=True)
class ExperimentContract:
    schema: str
    experiment_id: str
    experiment_revision: int
    candidate: CandidateIdentity
    baseline: BaselineIdentity | None
    job_to_be_done: str
    allowed_capabilities: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]
    dataset: DatasetRef
    metrics_config: MetricsConfig
    pass_thresholds: PassThresholds
    stop_conditions: StopConditions
    environment_constraints: EnvironmentConstraints
    authority_boundary: AuthorityBoundary
    claim_ceiling: str
    created_at: str
    contract_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "experiment_id": self.experiment_id,
            "experiment_revision": self.experiment_revision,
            "candidate": self.candidate.to_dict(),
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "job_to_be_done": self.job_to_be_done,
            "allowed_capabilities": list(self.allowed_capabilities),
            "forbidden_capabilities": list(self.forbidden_capabilities),
            "dataset": self.dataset.to_dict(),
            "metrics_config": self.metrics_config.to_dict(),
            "pass_thresholds": self.pass_thresholds.to_dict(),
            "stop_conditions": self.stop_conditions.to_dict(),
            "environment_constraints": self.environment_constraints.to_dict(),
            "authority_boundary": self.authority_boundary.to_dict(),
            "claim_ceiling": self.claim_ceiling,
            "created_at": self.created_at,
            "contract_hash": self.contract_hash,
        }

    def compute_content_hash(self) -> str:
        data = self.to_dict()
        data.pop("contract_hash", None)
        return canonical_json_hash(data)


def validate_contract_authority(boundary: AuthorityBoundary) -> None:
    """Fail-closed validation that no prohibited authorities are granted."""
    if boundary.routing_authority:
        raise ValueError(
            "FORBIDDEN_AUTHORITY_ESCALATION: Experiment contract must never grant routing_authority. "
            "Routing authority is exclusively owned by CapabilityPlanner."
        )
    if boundary.acceptance_authority:
        raise ValueError(
            "FORBIDDEN_AUTHORITY_ESCALATION: Experiment contract must never grant acceptance_authority. "
            "Acceptance is exclusively owned by Nexus/Owner authority."
        )
    if boundary.write_permission:
        raise ValueError(
            "FORBIDDEN_AUTHORITY_ESCALATION: Experiment contract must never grant write_permission to candidate."
        )
    if boundary.process_permission:
        raise ValueError(
            "FORBIDDEN_AUTHORITY_ESCALATION: Experiment contract must never grant process_permission to candidate."
        )
    if boundary.network_permission:
        raise ValueError(
            "FORBIDDEN_AUTHORITY_ESCALATION: Experiment contract must never grant network_permission to candidate."
        )


def validate_contract_capabilities(
    allowed_capabilities: tuple[str, ...],
    forbidden_capabilities: tuple[str, ...],
) -> None:
    """Validate consistency of allowed and forbidden capabilities.

    Vocabulary Note:
    - Allowed capabilities typically specify capability probe IDs (e.g. CAP-001 through CAP-011
      defined in capability.py) to be evaluated during G2 probing.
    - Forbidden capabilities specify capabilities or side-effect classes forbidden to the
      candidate (e.g. CAP-008, or effect names such as "file_mutation", "process_execution").
    - Overlap between allowed_capabilities and forbidden_capabilities represents an inconsistent
      or contradictory contract and fails closed.
    - This consistency check does NOT invent a generic runtime permission authority; runtime
      authority boundaries remain strictly governed by AuthorityBoundary.
    """
    allowed_set = set(allowed_capabilities)
    forbidden_set = set(forbidden_capabilities)
    overlap = allowed_set & forbidden_set
    if overlap:
        raise ValueError(
            f"CAPABILITY_CONSISTENCY_ERROR: Overlap detected between allowed_capabilities "
            f"and forbidden_capabilities: {sorted(overlap)}."
        )


def validate_experiment_contract(contract: ExperimentContract) -> None:
    if contract.schema != EXPERIMENT_CONTRACT_SCHEMA:
        raise ValueError(
            f"Invalid schema: expected {EXPERIMENT_CONTRACT_SCHEMA}, got {contract.schema}"
        )
    validate_contract_authority(contract.authority_boundary)
    validate_contract_capabilities(contract.allowed_capabilities, contract.forbidden_capabilities)
    expected_hash = contract.compute_content_hash()
    if contract.contract_hash != expected_hash:
        raise ValueError(
            f"CONTRACT_HASH_MISMATCH: Declared hash {contract.contract_hash} does not match computed {expected_hash}"
        )


def verify_contract_immutability(contract: ExperimentContract, expected_hash: str) -> bool:
    if not contract.contract_hash or contract.contract_hash != expected_hash:
        return False
    return contract.compute_content_hash() == expected_hash


def build_experiment_contract(
    *,
    experiment_id: str,
    experiment_revision: int,
    candidate: CandidateIdentity,
    baseline: BaselineIdentity | None,
    job_to_be_done: str,
    allowed_capabilities: tuple[str, ...],
    forbidden_capabilities: tuple[str, ...],
    dataset: DatasetRef,
    metrics_config: MetricsConfig,
    pass_thresholds: PassThresholds,
    stop_conditions: StopConditions,
    environment_constraints: EnvironmentConstraints,
    authority_boundary: AuthorityBoundary,
    claim_ceiling: str,
    created_at: str,
) -> ExperimentContract:
    validate_contract_authority(authority_boundary)
    validate_contract_capabilities(allowed_capabilities, forbidden_capabilities)
    raw_dict = {
        "schema": EXPERIMENT_CONTRACT_SCHEMA,
        "experiment_id": experiment_id,
        "experiment_revision": experiment_revision,
        "candidate": candidate.to_dict(),
        "baseline": baseline.to_dict() if baseline else None,
        "job_to_be_done": job_to_be_done,
        "allowed_capabilities": list(allowed_capabilities),
        "forbidden_capabilities": list(forbidden_capabilities),
        "dataset": dataset.to_dict(),
        "metrics_config": metrics_config.to_dict(),
        "pass_thresholds": pass_thresholds.to_dict(),
        "stop_conditions": stop_conditions.to_dict(),
        "environment_constraints": environment_constraints.to_dict(),
        "authority_boundary": authority_boundary.to_dict(),
        "claim_ceiling": claim_ceiling,
        "created_at": created_at,
    }
    contract_hash = canonical_json_hash(raw_dict)
    return ExperimentContract(
        schema=EXPERIMENT_CONTRACT_SCHEMA,
        experiment_id=experiment_id,
        experiment_revision=experiment_revision,
        candidate=candidate,
        baseline=baseline,
        job_to_be_done=job_to_be_done,
        allowed_capabilities=allowed_capabilities,
        forbidden_capabilities=forbidden_capabilities,
        dataset=dataset,
        metrics_config=metrics_config,
        pass_thresholds=pass_thresholds,
        stop_conditions=stop_conditions,
        environment_constraints=environment_constraints,
        authority_boundary=authority_boundary,
        claim_ceiling=claim_ceiling,
        created_at=created_at,
        contract_hash=contract_hash,
    )
