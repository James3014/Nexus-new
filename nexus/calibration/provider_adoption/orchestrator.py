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

from nexus.calibration.provider_adoption.adapter import (
    CandidateAdapter,
    get_adapter_evidence_ceiling,
)
from nexus.calibration.provider_adoption.canonical_json import canonical_json_hash
from nexus.calibration.provider_adoption.capability import (
    ALL_CAPABILITY_IDS,
    CapabilityMatrix,
    CapabilityProbeResult,
    CapabilityStatus,
    create_initial_capability_matrix,
)
from nexus.calibration.provider_adoption.cohort import (
    SUPPORTED_LEAKAGE_POLICY_REVISIONS,
    EvaluationResult,
    EvidenceLevel,
    FrozenCohort,
    QualityVerdict,
    audit_cohort_leakage,
    resolve_effective_evidence_level,
    validate_contract_cohort_binding,
)
from nexus.calibration.provider_adoption.contracts import (
    BaselineIdentity,
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
BASELINE_EVALUATION_SCHEMA = "nexus.provider_experiment.baseline_evaluation.v1"
COMPARATIVE_METRICS_SCHEMA = "nexus.provider_experiment.comparative_metrics.v1"

BASELINE_STATUS_NOT_REQUESTED = "NOT_REQUESTED"
BASELINE_STATUS_NOT_EVALUATED = "NOT_EVALUATED"
BASELINE_STATUS_UNAVAILABLE = "UNAVAILABLE"
BASELINE_STATUS_IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
BASELINE_STATUS_STOPPED_BY_CONDITION = "STOPPED_BY_CONDITION"
BASELINE_STATUS_EVALUATED = "EVALUATED"

COMPARISON_STATUS_AVAILABLE = "AVAILABLE"
COMPARISON_STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True)
class ComparativeMetrics:
    status: str
    reason: str = ""
    accuracy_delta: float | None = None
    error_rate_delta: float | None = None
    p50_latency_delta_ms: int | None = None
    p95_latency_delta_ms: int | None = None
    throughput_delta_rps: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "accuracy_delta": self.accuracy_delta,
            "error_rate_delta": self.error_rate_delta,
            "p50_latency_delta_ms": self.p50_latency_delta_ms,
            "p95_latency_delta_ms": self.p95_latency_delta_ms,
            "throughput_delta_rps": self.throughput_delta_rps,
        }


@dataclass(frozen=True)
class BaselineEvaluation:
    schema: str
    status: str
    reason: str
    requested: bool
    expected_identity: BaselineIdentity | None
    physical_identity: PhysicalIdentity | None
    baseline_identity_digest: str | None
    baseline_run_id: str | None
    cohort_id: str
    cohort_revision: int
    cohort_sha256: str
    ground_truth_revision: int
    ground_truth_sha256: str
    cohort_evaluations: tuple[EvaluationResult, ...]
    operational_metrics: OperationalMetrics | None
    comparison: ComparativeMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "requested": self.requested,
            "expected_identity": self.expected_identity.to_dict()
            if self.expected_identity
            else None,
            "physical_identity": self.physical_identity.to_dict()
            if self.physical_identity
            else None,
            "baseline_identity_digest": self.baseline_identity_digest,
            "baseline_run_id": self.baseline_run_id,
            "cohort_id": self.cohort_id,
            "cohort_revision": self.cohort_revision,
            "cohort_sha256": self.cohort_sha256,
            "ground_truth_revision": self.ground_truth_revision,
            "ground_truth_sha256": self.ground_truth_sha256,
            "cohort_evaluations": [e.to_dict() for e in self.cohort_evaluations],
            "operational_metrics": self.operational_metrics.to_dict()
            if self.operational_metrics
            else None,
            "comparison": self.comparison.to_dict(),
        }


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
    leakage_audit_status: str = "NOT_EVALUATED"
    stop_reason: str = ""
    receipt_hash: str = ""
    baseline_evaluation: BaselineEvaluation | None = None

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
            "leakage_audit_status": self.leakage_audit_status,
            "stop_reason": self.stop_reason,
            "receipt_hash": self.receipt_hash,
            "baseline_evaluation": self.baseline_evaluation.to_dict()
            if self.baseline_evaluation
            else None,
        }

    def compute_hash(self) -> str:
        data = self.to_dict()
        data.pop("receipt_hash", None)
        return canonical_json_hash(data)


def _grade_case_execution(
    *,
    out_text: str,
    schema_valid: bool,
    failure_class: str | None,
    ground_truth: str,
    acceptable_variants: tuple[str, ...],
    forbidden_outputs: tuple[str, ...],
) -> tuple[QualityVerdict, str | None, bool]:
    """Grade case execution against ground truth, acceptable variants, and forbidden outputs.

    Returns: (verdict, effective_failure_class, is_failure)
    """
    if failure_class:
        return QualityVerdict.FAIL, failure_class, True
    if not schema_valid:
        return QualityVerdict.FAIL, FailureClass.SCHEMA_VIOLATION.value, True

    norm_out = out_text.strip().lower()
    norm_gt = ground_truth.strip().lower()
    norm_variants = [v.strip().lower() for v in acceptable_variants]
    norm_forbidden = [f.strip().lower() for f in forbidden_outputs]

    if norm_out in norm_forbidden:
        return QualityVerdict.FAIL, FailureClass.INVALID_RESPONSE.value, True
    if norm_out == norm_gt or norm_out in norm_variants:
        return QualityVerdict.PASS, None, False
    return QualityVerdict.FAIL, FailureClass.INVALID_RESPONSE.value, True


def _evaluate_baseline(
    *,
    contract: ExperimentContract,
    cohort: FrozenCohort,
    baseline_adapter: CandidateAdapter | None,
    candidate_cohort_reached: bool,
    lifecycle_halt_reason: str,
    candidate_operational_metrics: OperationalMetrics | None,
    candidate_evaluated: bool,
    evaluator_identity: str,
    evidence_level: EvidenceLevel,
) -> BaselineEvaluation:
    """Evaluate optional baseline evidence without hiding framework defects."""
    return _evaluate_baseline_impl(
        contract=contract,
        cohort=cohort,
        baseline_adapter=baseline_adapter,
        candidate_cohort_reached=candidate_cohort_reached,
        lifecycle_halt_reason=lifecycle_halt_reason,
        candidate_operational_metrics=candidate_operational_metrics,
        candidate_evaluated=candidate_evaluated,
        evaluator_identity=evaluator_identity,
        evidence_level=evidence_level,
    )


def _evaluate_baseline_impl(
    *,
    contract: ExperimentContract,
    cohort: FrozenCohort,
    baseline_adapter: CandidateAdapter | None,
    candidate_cohort_reached: bool,
    lifecycle_halt_reason: str,
    candidate_operational_metrics: OperationalMetrics | None,
    candidate_evaluated: bool,
    evaluator_identity: str,
    evidence_level: EvidenceLevel,
) -> BaselineEvaluation:
    # 1. Baseline is optional: contract.baseline is None => NOT_REQUESTED
    if contract.baseline is None:
        return BaselineEvaluation(
            schema=BASELINE_EVALUATION_SCHEMA,
            status=BASELINE_STATUS_NOT_REQUESTED,
            reason="Baseline evaluation not requested in contract.",
            requested=False,
            expected_identity=None,
            physical_identity=None,
            baseline_identity_digest=None,
            baseline_run_id=None,
            cohort_id=cohort.cohort_id,
            cohort_revision=cohort.cohort_revision,
            cohort_sha256=cohort.cohort_sha256,
            ground_truth_revision=cohort.ground_truth_revision,
            ground_truth_sha256=cohort.ground_truth_sha256,
            cohort_evaluations=(),
            operational_metrics=None,
            comparison=ComparativeMetrics(
                status=COMPARISON_STATUS_NOT_AVAILABLE,
                reason="Baseline not requested.",
            ),
        )

    expected = contract.baseline

    # 2. Baseline requested but no adapter supplied => NOT_EVALUATED
    if baseline_adapter is None:
        return BaselineEvaluation(
            schema=BASELINE_EVALUATION_SCHEMA,
            status=BASELINE_STATUS_NOT_EVALUATED,
            reason="Baseline requested in contract but no baseline_adapter provided.",
            requested=True,
            expected_identity=expected,
            physical_identity=None,
            baseline_identity_digest=None,
            baseline_run_id=None,
            cohort_id=cohort.cohort_id,
            cohort_revision=cohort.cohort_revision,
            cohort_sha256=cohort.cohort_sha256,
            ground_truth_revision=cohort.ground_truth_revision,
            ground_truth_sha256=cohort.ground_truth_sha256,
            cohort_evaluations=(),
            operational_metrics=None,
            comparison=ComparativeMetrics(
                status=COMPARISON_STATUS_NOT_AVAILABLE,
                reason="Baseline adapter not provided.",
            ),
        )

    # 3. If candidate cohort evaluation was not reached, do not touch baseline transport.
    if not candidate_cohort_reached:
        return BaselineEvaluation(
            schema=BASELINE_EVALUATION_SCHEMA,
            status=BASELINE_STATUS_NOT_EVALUATED,
            reason=f"Cohort execution not reached due to candidate lifecycle halt: {lifecycle_halt_reason}",
            requested=True,
            expected_identity=expected,
            physical_identity=None,
            baseline_identity_digest=None,
            baseline_run_id=None,
            cohort_id=cohort.cohort_id,
            cohort_revision=cohort.cohort_revision,
            cohort_sha256=cohort.cohort_sha256,
            ground_truth_revision=cohort.ground_truth_revision,
            ground_truth_sha256=cohort.ground_truth_sha256,
            cohort_evaluations=(),
            operational_metrics=None,
            comparison=ComparativeMetrics(
                status=COMPARISON_STATUS_NOT_AVAILABLE,
                reason="Candidate cohort execution not reached.",
            ),
        )

    # 4. Inspect exact baseline physical identity
    try:
        baseline_physical_id = baseline_adapter.inspect_identity()
    except Exception as exc:
        err_msg = str(exc).strip().replace("\n", " ")[:120]
        reason = f"Baseline identity probe raised exception: {type(exc).__name__}: {err_msg}"
        return BaselineEvaluation(
            schema=BASELINE_EVALUATION_SCHEMA,
            status=BASELINE_STATUS_UNAVAILABLE,
            reason=reason,
            requested=True,
            expected_identity=expected,
            physical_identity=None,
            baseline_identity_digest=None,
            baseline_run_id=None,
            cohort_id=cohort.cohort_id,
            cohort_revision=cohort.cohort_revision,
            cohort_sha256=cohort.cohort_sha256,
            ground_truth_revision=cohort.ground_truth_revision,
            ground_truth_sha256=cohort.ground_truth_sha256,
            cohort_evaluations=(),
            operational_metrics=None,
            comparison=ComparativeMetrics(
                status=COMPARISON_STATUS_NOT_AVAILABLE,
                reason=reason,
            ),
        )

    if (
        baseline_physical_id.provider_id != expected.provider_id
        or baseline_physical_id.model_id != expected.model_id
        or baseline_physical_id.transport != expected.transport
    ):
        return BaselineEvaluation(
            schema=BASELINE_EVALUATION_SCHEMA,
            status=BASELINE_STATUS_IDENTITY_MISMATCH,
            reason=(
                f"Baseline physical identity mismatch: expected provider='{expected.provider_id}', "
                f"model='{expected.model_id}', transport='{expected.transport}'; "
                f"observed provider='{baseline_physical_id.provider_id}', "
                f"model='{baseline_physical_id.model_id}', transport='{baseline_physical_id.transport}'."
            ),
            requested=True,
            expected_identity=expected,
            physical_identity=baseline_physical_id,
            baseline_identity_digest=baseline_physical_id.identity_digest,
            baseline_run_id=None,
            cohort_id=cohort.cohort_id,
            cohort_revision=cohort.cohort_revision,
            cohort_sha256=cohort.cohort_sha256,
            ground_truth_revision=cohort.ground_truth_revision,
            ground_truth_sha256=cohort.ground_truth_sha256,
            cohort_evaluations=(),
            operational_metrics=None,
            comparison=ComparativeMetrics(
                status=COMPARISON_STATUS_NOT_AVAILABLE,
                reason="Baseline physical identity mismatch.",
            ),
        )

    # 5. Check if baseline adapter environment is blocked
    try:
        is_base_blocked, base_blocker_reason = baseline_adapter.is_environment_blocked()
    except Exception as exc:
        err_msg = str(exc).strip().replace("\n", " ")[:120]
        reason = f"Baseline environment check raised exception: {type(exc).__name__}: {err_msg}"
        return BaselineEvaluation(
            schema=BASELINE_EVALUATION_SCHEMA,
            status=BASELINE_STATUS_UNAVAILABLE,
            reason=reason,
            requested=True,
            expected_identity=expected,
            physical_identity=baseline_physical_id,
            baseline_identity_digest=baseline_physical_id.identity_digest,
            baseline_run_id=None,
            cohort_id=cohort.cohort_id,
            cohort_revision=cohort.cohort_revision,
            cohort_sha256=cohort.cohort_sha256,
            ground_truth_revision=cohort.ground_truth_revision,
            ground_truth_sha256=cohort.ground_truth_sha256,
            cohort_evaluations=(),
            operational_metrics=None,
            comparison=ComparativeMetrics(
                status=COMPARISON_STATUS_NOT_AVAILABLE,
                reason=reason,
            ),
        )

    if is_base_blocked:
        return BaselineEvaluation(
            schema=BASELINE_EVALUATION_SCHEMA,
            status=BASELINE_STATUS_UNAVAILABLE,
            reason=f"Baseline environment blocked: {base_blocker_reason}",
            requested=True,
            expected_identity=expected,
            physical_identity=baseline_physical_id,
            baseline_identity_digest=baseline_physical_id.identity_digest,
            baseline_run_id=None,
            cohort_id=cohort.cohort_id,
            cohort_revision=cohort.cohort_revision,
            cohort_sha256=cohort.cohort_sha256,
            ground_truth_revision=cohort.ground_truth_revision,
            ground_truth_sha256=cohort.ground_truth_sha256,
            cohort_evaluations=(),
            operational_metrics=None,
            comparison=ComparativeMetrics(
                status=COMPARISON_STATUS_NOT_AVAILABLE,
                reason=f"Baseline environment blocked: {base_blocker_reason}",
            ),
        )

    # 6. Execute SAME exact cohort cases with same grading semantics under stable baseline_run_id
    baseline_ceiling = get_adapter_evidence_ceiling(baseline_adapter)
    baseline_effective_level = resolve_effective_evidence_level(evidence_level, baseline_ceiling)
    baseline_run_id = str(uuid.uuid4())
    base_evaluations: list[EvaluationResult] = []
    base_consecutive_failures = 0
    base_total_failures = 0
    base_total_executed = 0
    base_t0 = time.monotonic()
    base_stopped = False
    base_stop_reason = ""
    base_crashed = False
    base_crash_reason = ""

    # Isolated state machine for stop condition evaluation only; does NOT mutate candidate sm
    base_sm = LifecycleStateMachine(experiment_id=contract.experiment_id)

    for case in cohort.cases:
        t_start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            out_text, schema_valid, failure_class, lat_ms = baseline_adapter.execute_case(case)
        except Exception as exc:
            base_crashed = True
            err_msg = str(exc).strip().replace("\n", " ")[:120]
            base_crash_reason = (
                f"Baseline case execution failed on case '{case.case_id}': "
                f"{type(exc).__name__}: {err_msg}"
            )
            break
        t_end = datetime.datetime.now(datetime.timezone.utc).isoformat()

        verdict, effective_fc, is_fail = _grade_case_execution(
            out_text=out_text,
            schema_valid=schema_valid,
            failure_class=failure_class,
            ground_truth=case.ground_truth,
            acceptable_variants=case.acceptable_variants,
            forbidden_outputs=case.forbidden_outputs,
        )

        if is_fail:
            base_consecutive_failures += 1
            base_total_failures += 1
        else:
            base_consecutive_failures = 0

        base_total_executed += 1

        base_evaluations.append(
            EvaluationResult(
                schema="nexus.provider_experiment.evaluation_result.v1",
                experiment_id=contract.experiment_id,
                run_id=baseline_run_id,
                case_id=case.case_id,
                candidate_identity_digest=baseline_physical_id.identity_digest,
                input_digest=canonical_json_hash(case.input_prompt),
                output_text=out_text,
                output_digest=canonical_json_hash(out_text),
                schema_valid=schema_valid,
                quality_result=verdict,
                failure_class=effective_fc,
                latency_ms=lat_ms,
                retry_count=0,
                started_at=t_start,
                completed_at=t_end,
                evaluator_identity=evaluator_identity,
                evidence_level=baseline_effective_level,
            )
        )

        should_stop, s_reason = base_sm.check_stop_conditions(
            contract.stop_conditions,
            consecutive_failures=base_consecutive_failures,
            total_failures=base_total_failures,
            total_executed=base_total_executed,
            timed_out=(effective_fc == FailureClass.PROVIDER_TIMEOUT.value),
        )
        if should_stop:
            base_stopped = True
            base_stop_reason = s_reason
            break

    # 7. Aggregate operational metrics
    base_t_duration = max(0.001, time.monotonic() - base_t0)
    base_offline_bool = (
        True
        if baseline_physical_id.offline_availability == "VERIFIED_OFFLINE"
        else (False if baseline_physical_id.offline_availability == "ONLINE_REQUIRED" else None)
    )
    base_metrics = (
        aggregate_operational_metrics(
            base_evaluations,
            total_duration_sec=base_t_duration,
            offline_verified=base_offline_bool,
            network_dependency_observed=baseline_physical_id.network_dependency,
        )
        if base_evaluations
        else None
    )

    # 8. Determine final status and comparison
    if base_crashed:
        base_status = BASELINE_STATUS_UNAVAILABLE
        base_reason = base_crash_reason
        comparison = ComparativeMetrics(
            status=COMPARISON_STATUS_NOT_AVAILABLE,
            reason=base_crash_reason,
        )
    elif base_stopped:
        base_status = BASELINE_STATUS_STOPPED_BY_CONDITION
        base_reason = base_stop_reason
        comparison = ComparativeMetrics(
            status=COMPARISON_STATUS_NOT_AVAILABLE,
            reason=f"Baseline evaluation stopped early by stop condition: {base_stop_reason}",
        )
    else:
        base_status = BASELINE_STATUS_EVALUATED
        base_reason = "Baseline cohort evaluation completed successfully."

        if (
            candidate_operational_metrics is not None
            and candidate_evaluated
            and base_metrics is not None
        ):
            accuracy_delta = round(
                candidate_operational_metrics.accuracy - base_metrics.accuracy, 4
            )
            error_rate_delta = round(
                candidate_operational_metrics.error_rate - base_metrics.error_rate, 4
            )
            p50_latency_delta_ms = (
                candidate_operational_metrics.p50_latency_ms - base_metrics.p50_latency_ms
            )
            p95_latency_delta_ms = (
                candidate_operational_metrics.p95_latency_ms - base_metrics.p95_latency_ms
            )
            throughput_delta_rps = round(
                candidate_operational_metrics.throughput_rps - base_metrics.throughput_rps, 4
            )
            comparison = ComparativeMetrics(
                status=COMPARISON_STATUS_AVAILABLE,
                reason="Candidate and baseline cohorts fully evaluated under identical conditions.",
                accuracy_delta=accuracy_delta,
                error_rate_delta=error_rate_delta,
                p50_latency_delta_ms=p50_latency_delta_ms,
                p95_latency_delta_ms=p95_latency_delta_ms,
                throughput_delta_rps=throughput_delta_rps,
            )
        else:
            comparison = ComparativeMetrics(
                status=COMPARISON_STATUS_NOT_AVAILABLE,
                reason="Candidate cohort was not fully evaluated.",
            )

    return BaselineEvaluation(
        schema=BASELINE_EVALUATION_SCHEMA,
        status=base_status,
        reason=base_reason,
        requested=True,
        expected_identity=expected,
        physical_identity=baseline_physical_id,
        baseline_identity_digest=baseline_physical_id.identity_digest,
        baseline_run_id=baseline_run_id if base_evaluations else None,
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        cohort_evaluations=tuple(base_evaluations),
        operational_metrics=base_metrics,
        comparison=comparison,
    )


def run_provider_adoption_experiment(
    *,
    contract: ExperimentContract,
    cohort: FrozenCohort,
    adapter: CandidateAdapter,
    baseline_adapter: CandidateAdapter | None = None,
    evidence_level: EvidenceLevel = EvidenceLevel.SIMULATED,
    evaluator_identity: str = "nexus_provider_adoption_evaluator_v1",
) -> ExperimentExecutionReceipt:
    """Execute complete provider adoption experiment."""
    # Invariant 6.6: Single stable run_id for the entire execution
    run_id = str(uuid.uuid4())
    sm = LifecycleStateMachine(experiment_id=contract.experiment_id)

    # G0: Contract Validation
    validate_experiment_contract(contract)
    validate_contract_cohort_binding(contract, cohort)
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
            blocker_category="ENVIRONMENT",
            blocker_reason=blocker_reason,
        )
        base_eval = _evaluate_baseline(
            contract=contract,
            cohort=cohort,
            baseline_adapter=baseline_adapter,
            candidate_cohort_reached=False,
            lifecycle_halt_reason=f"Candidate environment blocked: {blocker_reason}",
            candidate_operational_metrics=None,
            candidate_evaluated=False,
            evaluator_identity=evaluator_identity,
            evidence_level=evidence_level,
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
            leakage_audit_status="NOT_EVALUATED",
            stop_reason=sm.stop_reason,
            baseline_evaluation=base_eval,
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
            pass_thresholds=contract.pass_thresholds,
            metrics_config=contract.metrics_config,
            blocker_category="DATA/COHORT",
            blocker_reason="GROUND_TRUTH_NOT_READY: Benchmark cohort ground truth is incomplete or unverified.",
        )
        base_eval = _evaluate_baseline(
            contract=contract,
            cohort=cohort,
            baseline_adapter=baseline_adapter,
            candidate_cohort_reached=False,
            lifecycle_halt_reason="GROUND_TRUTH_NOT_READY: Benchmark cohort ground truth is incomplete or unverified.",
            candidate_operational_metrics=None,
            candidate_evaluated=False,
            evaluator_identity=evaluator_identity,
            evidence_level=evidence_level,
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
            leakage_audit_status="NOT_EVALUATED",
            stop_reason=sm.stop_reason,
            baseline_evaluation=base_eval,
        )
        h = receipt.compute_hash()
        return ExperimentExecutionReceipt(**{**receipt.__dict__, "receipt_hash": h})

    # Invariant 6.5 / Leakage Defense: Audit cohort for leakage before executing cases
    if contract.dataset.leakage_policy_revision not in SUPPORTED_LEAKAGE_POLICY_REVISIONS:
        policy_msg = (
            f"UNSUPPORTED_LEAKAGE_POLICY_REVISION: Revision "
            f"{contract.dataset.leakage_policy_revision} is not supported "
            f"(supported: {list(SUPPORTED_LEAKAGE_POLICY_REVISIONS)})."
        )
        sm.transition_to(LifecycleState.FAILED, policy_msg)
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
            blocker_category="DATA/COHORT",
            blocker_reason=policy_msg,
            capability_matrix=cap_matrix,
            allowed_capabilities=contract.allowed_capabilities,
        )
        base_eval = _evaluate_baseline(
            contract=contract,
            cohort=cohort,
            baseline_adapter=baseline_adapter,
            candidate_cohort_reached=False,
            lifecycle_halt_reason=policy_msg,
            candidate_operational_metrics=None,
            candidate_evaluated=False,
            evaluator_identity=evaluator_identity,
            evidence_level=evidence_level,
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
            leakage_audit_status="FAILED",
            stop_reason=sm.stop_reason,
            baseline_evaluation=base_eval,
        )
        h = receipt.compute_hash()
        return ExperimentExecutionReceipt(**{**receipt.__dict__, "receipt_hash": h})

    is_clean, leak_issues = audit_cohort_leakage(
        cohort,
        policy_revision=contract.dataset.leakage_policy_revision,
    )
    if not is_clean:
        leak_msg = f"COHORT_LEAKAGE_DETECTED: {'; '.join(leak_issues)}"
        sm.transition_to(LifecycleState.FAILED, leak_msg)
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
            blocker_category="DATA/COHORT",
            blocker_reason=leak_msg,
            capability_matrix=cap_matrix,
            allowed_capabilities=contract.allowed_capabilities,
        )
        base_eval = _evaluate_baseline(
            contract=contract,
            cohort=cohort,
            baseline_adapter=baseline_adapter,
            candidate_cohort_reached=False,
            lifecycle_halt_reason=leak_msg,
            candidate_operational_metrics=None,
            candidate_evaluated=False,
            evaluator_identity=evaluator_identity,
            evidence_level=evidence_level,
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
            leakage_audit_status="FAILED",
            stop_reason=sm.stop_reason,
            baseline_evaluation=base_eval,
        )
        h = receipt.compute_hash()
        return ExperimentExecutionReceipt(**{**receipt.__dict__, "receipt_hash": h})

    leakage_audit_status = "PASSED"

    # G3: Cohort Evaluation with active Stop Condition enforcement (Invariant 6.4)
    candidate_ceiling = get_adapter_evidence_ceiling(adapter)
    candidate_effective_level = resolve_effective_evidence_level(evidence_level, candidate_ceiling)
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

        verdict, effective_fc, is_fail = _grade_case_execution(
            out_text=out_text,
            schema_valid=schema_valid,
            failure_class=failure_class,
            ground_truth=case.ground_truth,
            acceptable_variants=case.acceptable_variants,
            forbidden_outputs=case.forbidden_outputs,
        )

        if is_fail:
            consecutive_failures += 1
            total_failures += 1
        else:
            consecutive_failures = 0

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
                failure_class=effective_fc,
                latency_ms=lat_ms,
                retry_count=0,
                started_at=t_case_start,
                completed_at=t_case_end,
                evaluator_identity=evaluator_identity,
                evidence_level=candidate_effective_level,
            )
        )

        # Check stop conditions actively (Invariant 6.4)
        should_stop, stop_reason = sm.check_stop_conditions(
            contract.stop_conditions,
            consecutive_failures=consecutive_failures,
            total_failures=total_failures,
            total_executed=total_executed,
            timed_out=(effective_fc == FailureClass.PROVIDER_TIMEOUT.value),
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

    # Baseline Calibration Evaluation (Settled Semantics)
    base_eval = _evaluate_baseline(
        contract=contract,
        cohort=cohort,
        baseline_adapter=baseline_adapter,
        candidate_cohort_reached=(not stopped),
        lifecycle_halt_reason=sm.stop_reason if stopped else "",
        candidate_operational_metrics=operational_metrics,
        candidate_evaluated=(not stopped),
        evaluator_identity=evaluator_identity,
        evidence_level=evidence_level,
    )

    # G5: Failure Evaluation (Contract vs Observation)
    if stopped:
        failure_matrix = build_failure_matrix()
    else:
        observations: dict[str, Any] = {}
        for fc in FailureClass:
            obs = adapter.inject_fault(fc)
            observations[fc.value] = obs

        failure_matrix = build_failure_matrix(observations=observations)
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
        throughput_rps=operational_metrics.throughput_rps,
        pass_thresholds=contract.pass_thresholds,
        metrics_config=contract.metrics_config,
        blocker_category="EVALUATION_STOP" if stopped else None,
        blocker_reason=sm.stop_reason if stopped else "",
        capability_matrix=cap_matrix,
        allowed_capabilities=contract.allowed_capabilities,
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
        leakage_audit_status=leakage_audit_status,
        stop_reason=sm.stop_reason,
        baseline_evaluation=base_eval,
    )
    h = receipt.compute_hash()
    return ExperimentExecutionReceipt(**{**receipt.__dict__, "receipt_hash": h})
