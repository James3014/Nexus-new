"""Lifecycle Orchestrator for Provider Adoption Experiments.

Executes the sequential G0 to G6 lifecycle:
G0: Contract Validation & Immutability Binding
G1: Physical Host & Runtime Identity Inspection
G2: Capability Probing
G3: Frozen Cohort Evaluation with Single Run Identity & Stop-Condition Enforcement
G4: Operational Metrics Aggregation
G5: Failure Behavior Contract & Observation Matrix
G6: Advisory Admission Recommendation

False-Green Defenses:
- Single Run Identity (6.6): run_id is generated once per experiment run and bound to all cases.
- Stop Conditions (6.4): Active evaluation after each case; halts immediately on limit breach.
- Cohort Provenance (6.5): Rejects unready ground truth with GROUND_TRUTH_NOT_READY.
- Honest Evidence (6.1, 6.2, 6.3): Preserves UNKNOWN and NOT_EVALUATED when not physically tested.
"""

from __future__ import annotations

import datetime
import time
import uuid
from dataclasses import dataclass
from typing import Any

from nexus.calibration.provider_adoption.adapter import CandidateAdapter
from nexus.calibration.provider_adoption.canonical_json import canonical_json_hash
from nexus.calibration.provider_adoption.capability import (
    ALL_CAPABILITY_IDS,
    CapabilityMatrix,
    CapabilityProbeResult,
    CapabilityStatus,
    create_initial_capability_matrix,
)
from nexus.calibration.provider_adoption.cohort import (
    EvaluationResult,
    EvidenceLevel,
    FrozenCohort,
    QualityVerdict,
)
from nexus.calibration.provider_adoption.contracts import (
    ExperimentContract,
    validate_experiment_contract,
)
from nexus.calibration.provider_adoption.failure import (
    FailureClass,
    FailureMatrix,
    build_failure_matrix,
)
from nexus.calibration.provider_adoption.identity import PhysicalIdentity
from nexus.calibration.provider_adoption.metrics import (
    OperationalMetrics,
    aggregate_operational_metrics,
)
from nexus.calibration.provider_adoption.recommendation import (
    AdmissionRecommendation,
    build_admission_recommendation,
)
from nexus.calibration.provider_adoption.state_machine import (
    LifecycleState,
    LifecycleStateMachine,
)

EXPERIMENT_RECEIPT_SCHEMA = "nexus.provider_experiment.execution_receipt.v1"


@dataclass(frozen=True)
class ExperimentExecutionReceipt:
    schema: str
    experiment_id: str
    run_id: str
    contract_hash: str
    final_state: LifecycleState
    state_history: tuple[tuple[str, str], ...]
    physical_identity: PhysicalIdentity
    capability_matrix: CapabilityMatrix
    cohort_evaluations: tuple[EvaluationResult, ...]
    operational_metrics: OperationalMetrics
    failure_matrix: FailureMatrix
    recommendation: AdmissionRecommendation
    stop_reason: str = ""
    receipt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "contract_hash": self.contract_hash,
            "final_state": self.final_state.value,
            "state_history": [(s, r) for s, r in self.state_history],
            "physical_identity": self.physical_identity.to_dict(),
            "capability_matrix": self.capability_matrix.to_dict(),
            "cohort_evaluations": [e.to_dict() for e in self.cohort_evaluations],
            "operational_metrics": self.operational_metrics.to_dict(),
            "failure_matrix": self.failure_matrix.to_dict(),
            "recommendation": self.recommendation.to_dict(),
            "stop_reason": self.stop_reason,
            "receipt_hash": self.receipt_hash,
        }

    def compute_hash(self) -> str:
        data = self.to_dict()
        data.pop("receipt_hash", None)
        return canonical_json_hash(data)


def run_provider_adoption_experiment(
    *,
    contract: ExperimentContract,
    cohort: FrozenCohort,
    adapter: CandidateAdapter,
    evidence_level: EvidenceLevel = EvidenceLevel.SIMULATED,
    evaluator_identity: str = "nexus_provider_adoption_evaluator_v1",
) -> ExperimentExecutionReceipt:
    """Execute complete provider adoption experiment."""
    # Invariant 6.6: Single stable run_id for the entire execution
    run_id = str(uuid.uuid4())
    sm = LifecycleStateMachine(experiment_id=contract.experiment_id)

    # G0: Contract Validation
    validate_experiment_contract(contract)
    sm.transition_to(LifecycleState.CONTRACT_FROZEN, "Contract validated and frozen.")

    # Check adapter environment blockers
    is_blocked, blocker_reason = adapter.is_environment_blocked()

    # G1: Physical Identity
    physical_id = adapter.inspect_identity()

    # Invariant 2: Contract environment constraints runtime enforcement
    env_c = contract.environment_constraints
    if not is_blocked and env_c.required_os and physical_id.platform != env_c.required_os:
        is_blocked = True
        blocker_reason = (
            f"ENVIRONMENT_CONSTRAINT_VIOLATION: Required OS '{env_c.required_os}' "
            f"does not match host platform '{physical_id.platform}'."
        )

    if not is_blocked and env_c.required_arch and physical_id.architecture != env_c.required_arch:
        is_blocked = True
        blocker_reason = (
            f"ENVIRONMENT_CONSTRAINT_VIOLATION: Required architecture '{env_c.required_arch}' "
            f"does not match host architecture '{physical_id.architecture}'."
        )

    if not is_blocked and env_c.min_memory_gb > 0:
        if physical_id.memory_gb is not None and physical_id.memory_gb < env_c.min_memory_gb:
            is_blocked = True
            blocker_reason = (
                f"ENVIRONMENT_CONSTRAINT_VIOLATION: Host memory {physical_id.memory_gb} GB "
                f"is below required min_memory_gb ({env_c.min_memory_gb} GB)."
            )
        elif physical_id.memory_gb is None:
            is_blocked = True
            blocker_reason = (
                f"ENVIRONMENT_CONSTRAINT_VIOLATION: min_memory_gb={env_c.min_memory_gb} required "
                f"but host memory is UNKNOWN."
            )

    if not is_blocked and env_c.require_offline:
        if physical_id.offline_availability != "VERIFIED_OFFLINE":
            is_blocked = True
            blocker_reason = (
                f"ENVIRONMENT_CONSTRAINT_VIOLATION: require_offline=True requires verified physical offline evidence, "
                f"but observed status is '{physical_id.offline_availability}'."
            )

    if not is_blocked and not env_c.allow_network:
        if physical_id.network_dependency == "ONLINE_REQUIRED":
            is_blocked = True
            blocker_reason = "ENVIRONMENT_CONSTRAINT_VIOLATION: allow_network=False but candidate requires online network."

    if is_blocked:
        sm.transition_to(
            LifecycleState.BLOCKED_BY_ENVIRONMENT,
            f"Candidate environment blocked: {blocker_reason}",
        )
        empty_caps = create_initial_capability_matrix()
        empty_metrics = aggregate_operational_metrics([])
        failure_matrix = build_failure_matrix()
        recommendation = build_admission_recommendation(
            experiment_id=contract.experiment_id,
            candidate_provider_id=contract.candidate.provider_id,
            candidate_model_id=contract.candidate.model_id,
            claim_ceiling=contract.claim_ceiling,
            accuracy=0.0,
            format_compliance=0.0,
            error_rate=1.0,
            offline_verified=False,
            latency_p95_ms=0,
            pass_thresholds=contract.pass_thresholds,
            metrics_config=contract.metrics_config,
            environment_blocked=True,
            blocker_reason=blocker_reason,
        )
        receipt = ExperimentExecutionReceipt(
            schema=EXPERIMENT_RECEIPT_SCHEMA,
            experiment_id=contract.experiment_id,
            run_id=run_id,
            contract_hash=contract.contract_hash,
            final_state=sm.current_state,
            state_history=tuple((s.value, r) for s, r in sm.history),
            physical_identity=physical_id,
            capability_matrix=empty_caps,
            cohort_evaluations=(),
            operational_metrics=empty_metrics,
            failure_matrix=failure_matrix,
            recommendation=recommendation,
            stop_reason=sm.stop_reason,
        )
        h = receipt.compute_hash()
        return ExperimentExecutionReceipt(**{**receipt.__dict__, "receipt_hash": h})

    sm.transition_to(LifecycleState.IDENTITY_INSPECTED, "Physical host identity inspected.")

    # G2: Capability Probes
    probe_results: dict[str, CapabilityProbeResult] = {}
    for cap_id in contract.allowed_capabilities:
        res = adapter.probe_capability(cap_id)
        probe_results[cap_id] = res
    # For capabilities not in allowed, leave as NOT_EVALUATED
    for cap_id in ALL_CAPABILITY_IDS:
        if cap_id not in probe_results:
            probe_results[cap_id] = CapabilityProbeResult(
                capability_id=cap_id,
                status=CapabilityStatus.NOT_EVALUATED,
                physical_evidence="Capability not included in contract probe list.",
                exit_code=None,
                latency_ms=0,
            )

    cap_matrix = CapabilityMatrix(
        schema="nexus.provider_experiment.capability_matrix.v1", probes=probe_results
    )
    sm.transition_to(LifecycleState.CAPABILITY_PROBED, "Capability probes evaluated.")

    # Invariant 6.5: Provenance & Ground truth readiness
    if not cohort.ground_truth_ready:
        sm.transition_to(
            LifecycleState.FAILED,
            "GROUND_TRUTH_NOT_READY: Benchmark cohort ground truth is incomplete or unverified.",
        )
        empty_metrics = aggregate_operational_metrics([])
        failure_matrix = build_failure_matrix()
        recommendation = build_admission_recommendation(
            experiment_id=contract.experiment_id,
            candidate_provider_id=contract.candidate.provider_id,
            candidate_model_id=contract.candidate.model_id,
            claim_ceiling=contract.claim_ceiling,
            accuracy=0.0,
            format_compliance=0.0,
            error_rate=1.0,
            offline_verified=False,
            latency_p95_ms=0,
            environment_blocked=True,
            blocker_reason="GROUND_TRUTH_NOT_READY",
        )
        receipt = ExperimentExecutionReceipt(
            schema=EXPERIMENT_RECEIPT_SCHEMA,
            experiment_id=contract.experiment_id,
            run_id=run_id,
            contract_hash=contract.contract_hash,
            final_state=sm.current_state,
            state_history=tuple((s.value, r) for s, r in sm.history),
            physical_identity=physical_id,
            capability_matrix=cap_matrix,
            cohort_evaluations=(),
            operational_metrics=empty_metrics,
            failure_matrix=failure_matrix,
            recommendation=recommendation,
            stop_reason=sm.stop_reason,
        )
        h = receipt.compute_hash()
        return ExperimentExecutionReceipt(**{**receipt.__dict__, "receipt_hash": h})

    # G3: Cohort Evaluation with active Stop Condition enforcement (Invariant 6.4)
    evaluations: list[EvaluationResult] = []
    consecutive_failures = 0
    total_failures = 0
    total_executed = 0
    t0_cohort = time.monotonic()
    stopped = False

    for case in cohort.cases:
        t_case_start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        out_text, schema_valid, failure_class, lat_ms = adapter.execute_case(case)
        t_case_end = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Grade quality
        if failure_class:
            verdict = QualityVerdict.FAIL
            consecutive_failures += 1
            total_failures += 1
        elif not schema_valid:
            verdict = QualityVerdict.FAIL
            failure_class = FailureClass.SCHEMA_VIOLATION.value
            consecutive_failures += 1
            total_failures += 1
        else:
            norm_out = out_text.strip().lower()
            norm_gt = case.ground_truth.strip().lower()
            norm_variants = [v.strip().lower() for v in case.acceptable_variants]
            if norm_out == norm_gt or norm_out in norm_variants:
                verdict = QualityVerdict.PASS
                consecutive_failures = 0
            else:
                verdict = QualityVerdict.FAIL
                failure_class = FailureClass.INVALID_RESPONSE.value
                consecutive_failures += 1
                total_failures += 1

        total_executed += 1

        evaluations.append(
            EvaluationResult(
                schema="nexus.provider_experiment.evaluation_result.v1",
                experiment_id=contract.experiment_id,
                run_id=run_id,  # Invariant 6.6: exact same run_id
                case_id=case.case_id,
                candidate_identity_digest=physical_id.identity_digest,
                input_digest=canonical_json_hash(case.input_prompt),
                output_text=out_text,
                output_digest=canonical_json_hash(out_text),
                schema_valid=schema_valid,
                quality_result=verdict,
                failure_class=failure_class,
                latency_ms=lat_ms,
                retry_count=0,
                started_at=t_case_start,
                completed_at=t_case_end,
                evaluator_identity=evaluator_identity,
                evidence_level=evidence_level,
            )
        )

        # Check stop conditions actively (Invariant 6.4)
        should_stop, stop_reason = sm.check_stop_conditions(
            contract.stop_conditions,
            consecutive_failures=consecutive_failures,
            total_failures=total_failures,
            total_executed=total_executed,
            timed_out=(failure_class == FailureClass.PROVIDER_TIMEOUT.value),
        )
        if should_stop:
            sm.transition_to(LifecycleState.STOPPED_BY_CONDITION, stop_reason)
            stopped = True
            break

    if not stopped:
        sm.transition_to(LifecycleState.COHORT_EVALUATED, "Frozen cohort evaluation completed.")

    # G4: Operational Metrics
    t_cohort_duration = max(0.001, time.monotonic() - t0_cohort)
    offline_bool = (
        True
        if physical_id.offline_availability == "VERIFIED_OFFLINE"
        else (False if physical_id.offline_availability == "ONLINE_REQUIRED" else None)
    )
    operational_metrics = aggregate_operational_metrics(
        evaluations,
        total_duration_sec=t_cohort_duration,
        offline_verified=offline_bool,
        network_dependency_observed=physical_id.network_dependency,
    )
    if not stopped:
        sm.transition_to(LifecycleState.OPERATIONAL_EVALUATED, "Operational metrics aggregated.")

    # G5: Failure Evaluation (Contract vs Observation)
    observations: dict[str, Any] = {}
    for fc in FailureClass:
        obs = adapter.inject_fault(fc)
        observations[fc.value] = obs

    failure_matrix = build_failure_matrix(observations=observations)
    if not stopped:
        sm.transition_to(LifecycleState.FAILURE_EVALUATED, "Failure behavior matrix compiled.")

    # G6: Admission Recommendation (Advisory Only)
    recommendation = build_admission_recommendation(
        experiment_id=contract.experiment_id,
        candidate_provider_id=contract.candidate.provider_id,
        candidate_model_id=contract.candidate.model_id,
        claim_ceiling=contract.claim_ceiling,
        accuracy=operational_metrics.accuracy,
        format_compliance=operational_metrics.format_compliance_rate,
        error_rate=operational_metrics.error_rate,
        offline_verified=(operational_metrics.offline_status == "VERIFIED_OFFLINE"),
        latency_p95_ms=operational_metrics.p95_latency_ms,
        semantic_correctness=operational_metrics.semantic_correctness_rate,
        latency_p50_ms=operational_metrics.p50_latency_ms,
        pass_thresholds=contract.pass_thresholds,
        metrics_config=contract.metrics_config,
        environment_blocked=stopped,
        blocker_reason=sm.stop_reason if stopped else "",
    )
    if not stopped:
        sm.transition_to(LifecycleState.RECOMMENDATION_READY, "Advisory recommendation ready.")

    receipt = ExperimentExecutionReceipt(
        schema=EXPERIMENT_RECEIPT_SCHEMA,
        experiment_id=contract.experiment_id,
        run_id=run_id,
        contract_hash=contract.contract_hash,
        final_state=sm.current_state,
        state_history=tuple((s.value, r) for s, r in sm.history),
        physical_identity=physical_id,
        capability_matrix=cap_matrix,
        cohort_evaluations=tuple(evaluations),
        operational_metrics=operational_metrics,
        failure_matrix=failure_matrix,
        recommendation=recommendation,
        stop_reason=sm.stop_reason,
    )
    h = receipt.compute_hash()
    return ExperimentExecutionReceipt(**{**receipt.__dict__, "receipt_hash": h})
