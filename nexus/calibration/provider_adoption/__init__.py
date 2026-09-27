"""Provider Adoption Experiment Framework for Nexus (V1).

A generic, reusable, multi-gate qualification and calibration framework:
G0: Immutable Experiment Contract
G1: Physical Identity Inspection & Drift Tracking
G2: Capability Probing
G3: Frozen Cohort Evaluation & Leakage Defense
G4: Operational Latency, Throughput & Offline Metrics
G5: Failure Taxonomy, Contract & Observation Matrix
G6: Advisory Admission Recommendation
"""

from nexus.calibration.provider_adoption.adapter import (
    CandidateAdapter,
    SimulatedCandidateAdapter,
)
from nexus.calibration.provider_adoption.apple_fm_adapter import (
    AppleFMCandidateAdapter,
)
from nexus.calibration.provider_adoption.canonical_json import (
    canonical_json_dumps,
    canonical_json_hash,
)
from nexus.calibration.provider_adoption.capability import (
    ALL_CAPABILITY_IDS,
    CapabilityMatrix,
    CapabilityProbeResult,
    CapabilityStatus,
    evaluate_capability_probe,
)
from nexus.calibration.provider_adoption.cohort import (
    CohortCase,
    CohortType,
    EvaluationResult,
    EvidenceLevel,
    FrozenCohort,
    QualityVerdict,
    audit_cohort_leakage,
    create_frozen_cohort,
)
from nexus.calibration.provider_adoption.contracts import (
    AuthorityBoundary,
    BaselineIdentity,
    CandidateIdentity,
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
from nexus.calibration.provider_adoption.evidence_bundle import (
    EvidenceBundle,
    build_evidence_bundle,
    generate_13_question_report,
)
from nexus.calibration.provider_adoption.failure import (
    FailureClass,
    FailureContractItem,
    FailureMatrix,
    FailureObservationItem,
    build_failure_matrix,
    get_default_failure_contracts,
)
from nexus.calibration.provider_adoption.identity import (
    PhysicalIdentity,
    evaluate_identity_drift,
    inspect_physical_host_identity,
)
from nexus.calibration.provider_adoption.metrics import (
    OperationalMetrics,
    aggregate_operational_metrics,
)
from nexus.calibration.provider_adoption.orchestrator import (
    BASELINE_EVALUATION_SCHEMA,
    BASELINE_STATUS_EVALUATED,
    BASELINE_STATUS_IDENTITY_MISMATCH,
    BASELINE_STATUS_NOT_EVALUATED,
    BASELINE_STATUS_NOT_REQUESTED,
    BASELINE_STATUS_STOPPED_BY_CONDITION,
    BASELINE_STATUS_UNAVAILABLE,
    COMPARATIVE_METRICS_SCHEMA,
    COMPARISON_STATUS_AVAILABLE,
    COMPARISON_STATUS_NOT_AVAILABLE,
    BaselineEvaluation,
    ComparativeMetrics,
    ExperimentExecutionReceipt,
    run_provider_adoption_experiment,
)
from nexus.calibration.provider_adoption.recommendation import (
    AdmissionRecommendation,
    build_admission_recommendation,
)
from nexus.calibration.provider_adoption.requalification import (
    DriftDimension,
    RequalificationEvaluation,
    RequalificationVerdict,
    evaluate_requalification,
)
from nexus.calibration.provider_adoption.state_machine import (
    LifecycleState,
    LifecycleStateMachine,
)

__all__ = [
    "ALL_CAPABILITY_IDS",
    "AdmissionRecommendation",
    "AppleFMCandidateAdapter",
    "AuthorityBoundary",
    "BASELINE_EVALUATION_SCHEMA",
    "BASELINE_STATUS_EVALUATED",
    "BASELINE_STATUS_IDENTITY_MISMATCH",
    "BASELINE_STATUS_NOT_EVALUATED",
    "BASELINE_STATUS_NOT_REQUESTED",
    "BASELINE_STATUS_STOPPED_BY_CONDITION",
    "BASELINE_STATUS_UNAVAILABLE",
    "BaselineEvaluation",
    "BaselineIdentity",
    "COMPARATIVE_METRICS_SCHEMA",
    "COMPARISON_STATUS_AVAILABLE",
    "COMPARISON_STATUS_NOT_AVAILABLE",
    "CandidateAdapter",
    "CandidateIdentity",
    "CapabilityMatrix",
    "CapabilityProbeResult",
    "CapabilityStatus",
    "CohortCase",
    "CohortType",
    "ComparativeMetrics",
    "DatasetRef",
    "DriftDimension",
    "EnvironmentConstraints",
    "EvaluationResult",
    "EvidenceBundle",
    "EvidenceLevel",
    "ExperimentContract",
    "ExperimentExecutionReceipt",
    "FailureClass",
    "FailureContractItem",
    "FailureMatrix",
    "FailureObservationItem",
    "FrozenCohort",
    "LifecycleState",
    "LifecycleStateMachine",
    "MetricsConfig",
    "OperationalMetrics",
    "PassThresholds",
    "PhysicalIdentity",
    "QualityVerdict",
    "RequalificationEvaluation",
    "RequalificationVerdict",
    "SimulatedCandidateAdapter",
    "StopConditions",
    "aggregate_operational_metrics",
    "audit_cohort_leakage",
    "build_admission_recommendation",
    "build_evidence_bundle",
    "build_experiment_contract",
    "build_failure_matrix",
    "canonical_json_dumps",
    "canonical_json_hash",
    "create_frozen_cohort",
    "evaluate_capability_probe",
    "evaluate_identity_drift",
    "evaluate_requalification",
    "generate_13_question_report",
    "get_default_failure_contracts",
    "inspect_physical_host_identity",
    "run_provider_adoption_experiment",
    "validate_experiment_contract",
    "verify_contract_immutability",
]
