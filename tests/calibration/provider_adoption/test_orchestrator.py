"""Integration tests for Provider Adoption Lifecycle Orchestrator.

Verifies:
- G0 to G6 full pipeline execution.
- Invariant 6.6: Single stable run_id across all evaluations.
- Invariant 6.4: Active stop condition enforcement halts remaining case execution immediately.
- Invariant 6.5: Unready ground truth triggers GROUND_TRUTH_NOT_READY halt.
- Environment blocked candidate handling.
- Evidence bundle generation and 13-question report rendering.
"""

from typing import Any

from nexus.calibration.provider_adoption.adapter import (
    SimulatedCandidateAdapter,
)
from nexus.calibration.provider_adoption.cohort import (
    CohortCase,
    CohortType,
    EvidenceLevel,
    QualityVerdict,
    create_frozen_cohort,
)
from nexus.calibration.provider_adoption.contracts import (
    AuthorityBoundary,
    BaselineIdentity,
    CandidateIdentity,
    DatasetRef,
    EnvironmentConstraints,
    MetricsConfig,
    PassThresholds,
    StopConditions,
    build_experiment_contract,
)
from nexus.calibration.provider_adoption.evidence_bundle import (
    build_evidence_bundle,
    generate_13_question_report,
)
from nexus.calibration.provider_adoption.failure import FailureClass
from nexus.calibration.provider_adoption.identity import PhysicalIdentity
from nexus.calibration.provider_adoption.orchestrator import (
    BASELINE_STATUS_EVALUATED,
    BASELINE_STATUS_IDENTITY_MISMATCH,
    BASELINE_STATUS_NOT_EVALUATED,
    BASELINE_STATUS_NOT_REQUESTED,
    BASELINE_STATUS_STOPPED_BY_CONDITION,
    BASELINE_STATUS_UNAVAILABLE,
    COMPARISON_STATUS_AVAILABLE,
    COMPARISON_STATUS_NOT_AVAILABLE,
    run_provider_adoption_experiment,
)
from nexus.calibration.provider_adoption.state_machine import LifecycleState


def _make_test_contract(
    experiment_id: str = "EXP-TEST-001",
    claim_ceiling: str = "L0.5",
    max_consecutive_failures: int = 3,
) -> tuple[Any, Any]:
    cohort = create_frozen_cohort(
        cohort_id="COHORT-ORCH-TEST",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[
            CohortCase("C1", "classification", "Input 1", "PASS"),
            CohortCase("C2", "classification", "Input 2", "PASS"),
            CohortCase("C3", "classification", "Input 3", "PASS"),
            CohortCase("C4", "classification", "Input 4", "PASS"),
            CohortCase("C5", "classification", "Input 5", "PASS"),
        ],
    )
    dataset_ref = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id=experiment_id,
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-v1", "in_memory", "sim_runtime"),
        baseline=None,
        job_to_be_done="Testing orchestrator",
        allowed_capabilities=("CAP-001", "CAP-002"),
        forbidden_capabilities=("file_mutation", "process_execution"),
        dataset=dataset_ref,
        metrics_config=MetricsConfig(500, 2000, 0.05, 1.0),
        pass_thresholds=PassThresholds(0.8, 0.9, 0.85),
        stop_conditions=StopConditions(max_consecutive_failures, 0.2, True, 5),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling=claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    return contract, cohort


def test_orchestrator_full_successful_run_and_single_run_id_6_6():
    """Verify complete G0-G6 lifecycle and Invariant 6.6 (single stable run_id)."""
    contract, cohort = _make_test_contract("EXP-SUCCESS")
    adapter = SimulatedCandidateAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert receipt.receipt_hash != ""
    assert len(receipt.cohort_evaluations) == 5

    # Invariant 6.6: every case evaluation MUST bind to the exact same run_id
    stable_run_id = receipt.run_id
    assert stable_run_id != ""
    for ev in receipt.cohort_evaluations:
        assert ev.run_id == stable_run_id

    # Verify claim ceiling clamping
    assert receipt.recommendation.clamped_by_ceiling is True
    assert receipt.recommendation.recommended_autonomy == "L0.5"

    # Verify bundle and report generation
    bundle = build_evidence_bundle(contract, receipt)
    assert bundle.bundle_hash != ""
    report = generate_13_question_report(bundle)
    assert "Q1:" in report
    assert "Q13:" in report
    assert "INDEPENDENT_REVIEW_OF_NEXUS_NEW_PROVIDER_ADOPTION_CANDIDATE" in report


def test_orchestrator_stop_condition_halts_execution_immediately_6_4():
    """Verify Invariant 6.4: stop condition aborts remaining cases."""
    contract, cohort = _make_test_contract(
        experiment_id="EXP-STOP-TEST",
        max_consecutive_failures=2,
    )
    # Fail case C1 and C2
    adapter = SimulatedCandidateAdapter(
        fail_case_ids={"C1", "C2"},
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.STOPPED_BY_CONDITION
    assert "consecutive failures (2) reached limit (2)" in receipt.stop_reason

    # CRUCIAL INVARIANT: remaining cases (C3, C4, C5) must NOT have been executed!
    assert len(receipt.cohort_evaluations) == 2
    assert [e.case_id for e in receipt.cohort_evaluations] == ["C1", "C2"]

    # D4: stop-condition must NOT be labeled as environment blocked
    assert receipt.recommendation.blocker_category == "EVALUATION_STOP"
    assert "blocked by environment" not in receipt.recommendation.reasons[0].lower()
    assert "stopped by evaluation condition" in receipt.recommendation.reasons[0].lower()


def test_orchestrator_unready_ground_truth_blocks_benchmark_6_5():
    """Verify Invariant 6.5: ground truth not ready blocks benchmark."""
    contract_tmpl, cohort = _make_test_contract("EXP-GT-UNREADY")
    # Mark cohort ground truth as unready
    unready_cohort = create_frozen_cohort(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cohort.cases,
        ground_truth_ready=False,
    )
    unready_ds = DatasetRef(
        cohort_id=unready_cohort.cohort_id,
        cohort_revision=unready_cohort.cohort_revision,
        cohort_sha256=unready_cohort.cohort_sha256,
        ground_truth_revision=unready_cohort.ground_truth_revision,
        ground_truth_sha256=unready_cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=unready_cohort.cohort_type,
        ground_truth_ready=False,
    )
    contract = build_experiment_contract(
        experiment_id=contract_tmpl.experiment_id,
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=unready_ds,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    adapter = SimulatedCandidateAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=unready_cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.FAILED
    assert "GROUND_TRUTH_NOT_READY" in receipt.stop_reason
    assert len(receipt.cohort_evaluations) == 0

    # D4: ground-truth failure must NOT be labeled as environment blocked
    assert receipt.recommendation.blocker_category == "DATA/COHORT"
    assert "blocked by environment" not in receipt.recommendation.reasons[0].lower()
    assert "blocked by dataset/cohort" in receipt.recommendation.reasons[0].lower()
    assert receipt.leakage_audit_status == "NOT_EVALUATED"


def test_orchestrator_environment_blocked_candidate():
    contract, cohort = _make_test_contract("EXP-BLOCKED")
    adapter = SimulatedCandidateAdapter(
        environment_blocked=True,
        environment_blocker_reason="APPLE_FM_LICENSE_NOT_AGREED: Run 'sudo fm license' to review and agree.",
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    assert "APPLE_FM_LICENSE_NOT_AGREED" in receipt.stop_reason
    assert receipt.recommendation.recommended_state == "REGISTERED_BLOCKED"
    assert receipt.recommendation.recommended_autonomy == "L0"
    assert len(receipt.cohort_evaluations) == 0


def test_orchestrator_environment_constraints_os_arch_violation():
    """Verify that contract environment constraints (OS/Arch mismatch) fail-close at G1."""
    contract_tmpl, cohort = _make_test_contract("EXP-ENV-OS-MISMATCH")
    # Require an OS that doesn't match host
    wrong_env = EnvironmentConstraints(
        required_os="NonExistentOS",
        required_arch="arm64",
        min_memory_gb=8,
    )
    contract = build_experiment_contract(
        experiment_id=contract_tmpl.experiment_id,
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=wrong_env,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    adapter = SimulatedCandidateAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    assert "Required OS 'NonExistentOS' does not match host platform" in receipt.stop_reason
    assert receipt.recommendation.recommended_state == "REGISTERED_BLOCKED"
    assert receipt.recommendation.recommended_autonomy == "L0"
    assert len(receipt.cohort_evaluations) == 0

    # Also test arch mismatch
    wrong_arch = EnvironmentConstraints(
        required_os=receipt.physical_identity.platform,
        required_arch="non_existent_arch_64",
        min_memory_gb=8,
    )
    contract_arch = build_experiment_contract(
        experiment_id="EXP-ENV-ARCH-MISMATCH",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=wrong_arch,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    receipt_arch = run_provider_adoption_experiment(
        contract=contract_arch,
        cohort=cohort,
        adapter=adapter,
    )
    assert receipt_arch.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    assert (
        "Required architecture 'non_existent_arch_64' does not match host architecture"
        in receipt_arch.stop_reason
    )


def test_orchestrator_environment_constraints_require_offline_unverified():
    """Verify that require_offline=True without physical offline verification fail-closes at G1."""
    contract_tmpl, cohort = _make_test_contract("EXP-ENV-OFFLINE")
    # Require offline, but simulated adapter physical identity defaults to UNKNOWN
    offline_env = EnvironmentConstraints(
        required_os="Darwin",
        required_arch="arm64",
        min_memory_gb=8,
        require_offline=True,
    )
    contract = build_experiment_contract(
        experiment_id=contract_tmpl.experiment_id,
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=offline_env,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    adapter = SimulatedCandidateAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    assert "require_offline=True requires verified physical offline evidence" in receipt.stop_reason
    assert receipt.recommendation.recommended_state == "REGISTERED_BLOCKED"
    assert receipt.recommendation.recommended_autonomy == "L0"
    assert len(receipt.cohort_evaluations) == 0


def test_orchestrator_allow_network_false_cannot_silently_become_verified_offline():
    """Verify negative control: allow_network=False cannot silently become verified network independence."""
    contract_tmpl, cohort = _make_test_contract("EXP-ENV-NETWORK-HONESTY")
    no_net_env = EnvironmentConstraints(
        required_os="Darwin",
        required_arch="arm64",
        min_memory_gb=8,
        allow_network=False,
        require_offline=False,
    )
    contract = build_experiment_contract(
        experiment_id=contract_tmpl.experiment_id,
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=no_net_env,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    # Simulated adapter without offline verification (offline_verified=None -> UNKNOWN)
    adapter = SimulatedCandidateAdapter(offline_verified=None)

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    # Invariant: allow_network=False MUST NOT cause offline_availability to become VERIFIED_OFFLINE
    assert receipt.physical_identity.offline_availability == "UNKNOWN"
    assert receipt.physical_identity.network_dependency == "UNKNOWN"
    assert receipt.operational_metrics.offline_status == "UNKNOWN"
    # And recommendation MUST NOT promote to LOCAL_CONDITIONAL without physical offline verification
    assert receipt.recommendation.recommended_state != "LOCAL_CONDITIONAL"
    assert receipt.recommendation.recommended_state == "REGISTERED_CONDITIONAL"


def test_orchestrator_allow_network_false_blocks_online_required_candidate():
    """Verify negative control: allow_network=False blocks candidate with ONLINE_REQUIRED dependency."""
    contract_tmpl, cohort = _make_test_contract("EXP-ENV-ONLINE-BLOCKED")
    no_net_env = EnvironmentConstraints(
        required_os="Darwin",
        required_arch="arm64",
        min_memory_gb=8,
        allow_network=False,
    )
    contract = build_experiment_contract(
        experiment_id=contract_tmpl.experiment_id,
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=no_net_env,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )

    class OnlineRequiredAdapter(SimulatedCandidateAdapter):
        def inspect_identity(self):
            ident = super().inspect_identity()
            # Candidate explicitly requires online network
            raw = ident.to_dict()
            raw["network_dependency"] = "ONLINE_REQUIRED"
            return PhysicalIdentity(**raw)

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=OnlineRequiredAdapter(),
    )

    assert receipt.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    assert "allow_network=False but candidate requires online network" in receipt.stop_reason
    assert receipt.recommendation.recommended_state == "REGISTERED_BLOCKED"
    assert len(receipt.cohort_evaluations) == 0


def test_orchestrator_environment_constraints_min_memory_violation():
    """Verify min_memory_gb constraint violation fail-closes at G1."""
    contract_tmpl, cohort = _make_test_contract("EXP-ENV-MEM")
    # Require absurdly large memory
    mem_env = EnvironmentConstraints(
        required_os="Darwin",
        required_arch="arm64",
        min_memory_gb=2048,
    )
    contract = build_experiment_contract(
        experiment_id=contract_tmpl.experiment_id,
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=mem_env,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    adapter = SimulatedCandidateAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    assert "min_memory_gb" in receipt.stop_reason
    assert receipt.recommendation.recommended_state == "REGISTERED_BLOCKED"
    assert len(receipt.cohort_evaluations) == 0


def test_orchestrator_contract_threshold_failure_drives_recommendation():
    """Verify that failing contract thresholds actively demotes G6 recommendation to L0 / BLOCKED."""
    contract_tmpl, _ = _make_test_contract("EXP-THRESH-FAIL")
    # Pass thresholds requiring 100% accuracy and 100% format compliance
    strict_thresholds = PassThresholds(
        accuracy_min=0.99,
        format_compliance_min=0.99,
        semantic_correctness_min=0.99,
    )
    # Imperfect cohort where C5 will fail when executed by adapter with fail_case_ids={"C5"}
    imperfect_cohort = create_frozen_cohort(
        cohort_id="COHORT-IMPERFECT",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[
            CohortCase("C1", "classification", "Input 1", "PASS"),
            CohortCase("C2", "classification", "Input 2", "PASS"),
            CohortCase("C3", "classification", "Input 3", "PASS"),
            CohortCase("C4", "classification", "Input 4", "PASS"),
            CohortCase("C5", "classification", "Input 5", "PASS"),
        ],
    )
    imperfect_ds = DatasetRef(
        cohort_id=imperfect_cohort.cohort_id,
        cohort_revision=imperfect_cohort.cohort_revision,
        cohort_sha256=imperfect_cohort.cohort_sha256,
        ground_truth_revision=imperfect_cohort.ground_truth_revision,
        ground_truth_sha256=imperfect_cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=imperfect_cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id=contract_tmpl.experiment_id,
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=imperfect_ds,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=strict_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=imperfect_cohort,
        adapter=SimulatedCandidateAdapter(fail_case_ids={"C5"}),
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert receipt.operational_metrics.accuracy == 0.80
    # Because accuracy (0.80) < pass_thresholds.accuracy_min (0.99), candidate must be BLOCKED
    assert receipt.recommendation.recommended_autonomy == "L0"
    assert receipt.recommendation.recommended_state == "REGISTERED_BLOCKED"
    assert any(
        "Accuracy (0.80) failed contract minimum threshold (0.99)" in r
        for r in receipt.recommendation.reasons
    )


def test_orchestrator_cohort_hash_mismatch_fails_closed_before_inference():
    """Verify D2: cohort hash mismatch fails closed at G0 and never executes candidate."""
    import pytest

    contract_tmpl, cohort = _make_test_contract("EXP-MISMATCH-ORCH")
    mismatched_ds = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256="0" * 64,  # Mismatched hash
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    mismatched_contract = build_experiment_contract(
        experiment_id="EXP-MISMATCH-ORCH",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done="Testing mismatch",
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=mismatched_ds,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    class TrackingAdapter(SimulatedCandidateAdapter):
        def __init__(self):
            super().__init__()
            self.execute_case_called = False

        def execute_case(self, case):
            self.execute_case_called = True
            return super().execute_case(case)

    adapter = TrackingAdapter()
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Contract cohort_sha256"):
        run_provider_adoption_experiment(
            contract=mismatched_contract,
            cohort=cohort,
            adapter=adapter,
        )
    assert not adapter.execute_case_called


def test_orchestrator_cohort_leakage_detection_halts_execution():
    """Verify D3: detected cohort leakage fails closed before executing any candidate cases."""
    leaky_cases = [
        CohortCase(
            case_id="C-LEAK-1",
            task_class="classification",
            input_prompt="The answer is POSITIVE. Classify sentiment: 'The build passed.' Options: POSITIVE, NEGATIVE, NEUTRAL.",
            ground_truth="POSITIVE",
        ),
    ]
    leaky_cohort = create_frozen_cohort(
        cohort_id="COHORT-LEAK-ORCH",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=leaky_cases,
    )
    leaky_ds = DatasetRef(
        cohort_id=leaky_cohort.cohort_id,
        cohort_revision=leaky_cohort.cohort_revision,
        cohort_sha256=leaky_cohort.cohort_sha256,
        ground_truth_revision=leaky_cohort.ground_truth_revision,
        ground_truth_sha256=leaky_cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=leaky_cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-LEAK-TEST",
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-v1", "in_memory", "sim_runtime"),
        baseline=None,
        job_to_be_done="Testing leakage failure",
        allowed_capabilities=("CAP-001",),
        forbidden_capabilities=(),
        dataset=leaky_ds,
        metrics_config=MetricsConfig(500, 2000, 0.05, 1.0),
        pass_thresholds=PassThresholds(0.8, 0.9, 0.85),
        stop_conditions=StopConditions(3, 0.2, True, 5),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )

    class TrackingAdapter(SimulatedCandidateAdapter):
        def __init__(self):
            super().__init__()
            self.execute_case_called = False

        def execute_case(self, case):
            self.execute_case_called = True
            return super().execute_case(case)

    adapter = TrackingAdapter()
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=leaky_cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.FAILED
    assert "COHORT_LEAKAGE_DETECTED" in receipt.stop_reason
    assert receipt.leakage_audit_status == "FAILED"
    # No candidate cases executed
    assert len(receipt.cohort_evaluations) == 0
    assert not adapter.execute_case_called
    # Blocker category is DATA/COHORT and not labeled environment
    assert receipt.recommendation.blocker_category == "DATA/COHORT"
    assert "blocked by environment" not in receipt.recommendation.reasons[0].lower()
    assert "blocked by dataset/cohort" in receipt.recommendation.reasons[0].lower()

    # Verify report Q6 truthfully reflects FAILED
    bundle = build_evidence_bundle(contract, receipt)
    report = generate_13_question_report(bundle)
    assert "- **Leakage Audit Status:** `FAILED`" in report
    assert "Prompt leakage detected during audit; case execution halted." in report


def test_orchestrator_environment_blocked_does_not_claim_leakage_audit():
    """Verify D3: environment blocked runs record leakage_audit_status as NOT_EVALUATED and do not overclaim."""
    contract, cohort = _make_test_contract("EXP-ENV-BLOCKED-LEAK")
    adapter = SimulatedCandidateAdapter(
        environment_blocked=True,
        environment_blocker_reason="LICENSE_NOT_AGREED",
    )
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )
    assert receipt.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    assert receipt.leakage_audit_status == "NOT_EVALUATED"

    bundle = build_evidence_bundle(contract, receipt)
    report = generate_13_question_report(bundle)
    assert "- **Leakage Audit Status:** `NOT_EVALUATED`" in report
    assert "Cohort audit was not evaluated due to prior lifecycle blocker." in report


def test_orchestrator_stop_condition_skips_g5_fault_injection():
    """Verify D5: when stopped by condition, G5 fault injection is skipped and observations are NOT_EVALUATED."""
    from nexus.calibration.provider_adoption.failure import FailureClass

    contract, cohort = _make_test_contract(
        experiment_id="EXP-STOP-G5-SKIP",
        max_consecutive_failures=2,
    )

    class CountingFaultInjectionAdapter(SimulatedCandidateAdapter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.inject_fault_call_count = 0

        def inject_fault(self, failure_class: FailureClass):
            self.inject_fault_call_count += 1
            return super().inject_fault(failure_class)

    adapter = CountingFaultInjectionAdapter(
        fail_case_ids={"C1", "C2"},
    )
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.STOPPED_BY_CONDITION
    # D5: adapter.inject_fault MUST NOT have been called after terminal stop!
    assert adapter.inject_fault_call_count == 0
    # G5 failure matrix returns unexercised observations
    assert receipt.failure_matrix.all_fail_closed_observed is None
    for fc_key, obs in receipt.failure_matrix.observations.items():
        assert obs.exercised is False
        assert obs.observed_fail_closed is None
        assert obs.observed_retry_behavior == "NOT_EVALUATED"

    # D4: recommendation category is EVALUATION_STOP
    assert receipt.recommendation.blocker_category == "EVALUATION_STOP"
    assert "blocked by environment" not in receipt.recommendation.reasons[0].lower()


def test_orchestrator_min_throughput_rps_enforced_in_recommendation():
    """Verify D1: low throughput fails contract recommendation in orchestrator."""
    contract_tmpl, cohort = _make_test_contract("EXP-LOW-THROUGHPUT")
    # Require 100000.0 rps (guaranteed to exceed simulated throughput, capped at 5000 rps for 5 cases)
    target_min_throughput = 100000.0
    strict_throughput_cfg = MetricsConfig(
        latency_p50_max_ms=500,
        latency_p95_max_ms=2000,
        max_error_rate=0.05,
        min_throughput_rps=target_min_throughput,
    )
    contract = build_experiment_contract(
        experiment_id=contract_tmpl.experiment_id,
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=strict_throughput_cfg,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=SimulatedCandidateAdapter(),
    )
    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert receipt.operational_metrics.throughput_rps < target_min_throughput
    # Must be demoted to L0 / REGISTERED_BLOCKED due to throughput breach
    assert receipt.recommendation.recommended_autonomy == "L0"
    assert receipt.recommendation.recommended_state == "REGISTERED_BLOCKED"
    assert any(
        f"failed contract minimum threshold ({target_min_throughput:.2f} rps)" in r
        for r in receipt.recommendation.reasons
    )


def test_orchestrator_cli_equivalent_cohort_reaches_execution_without_leakage_error():
    """Verify that CLI-equivalent cohort with legitimate classification options (CASE-001)
    passes leakage audit and successfully reaches execution instead of COHORT_LEAKAGE_DETECTED.
    """
    cases = [
        CohortCase(
            case_id="CASE-001",
            task_class="classification",
            input_prompt="Classify the sentiment of this text: 'The build passed cleanly without errors.' Options: POSITIVE, NEGATIVE, NEUTRAL.",
            ground_truth="POSITIVE",
            acceptable_variants=("positive", "POSITIVE."),
        ),
        CohortCase(
            case_id="CASE-002",
            task_class="extraction",
            input_prompt="Extract the error code from this message: 'Process exited with code 137 (OOM killed)'",
            ground_truth="137",
            acceptable_variants=("code 137", "137 (OOM killed)"),
        ),
        CohortCase(
            case_id="CASE-003",
            task_class="summarization",
            input_prompt="Summarize this status: 'Database connection failed after 3 retries due to connection timeout.'",
            ground_truth="Database connection timed out after 3 retries.",
            acceptable_variants=(
                "database connection timed out after 3 retries.",
                "database timeout after 3 retries",
            ),
        ),
    ]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-DEVSPACE-FAILURES-FIXTURE-V1",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=cases,
        ground_truth_ready=True,
    )
    dataset_ref = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-CLI-EQUIVALENT-TEST",
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-v1", "in_memory", "sim_runtime"),
        baseline=None,
        job_to_be_done="CLI smoke qualification",
        allowed_capabilities=("CAP-001", "CAP-002", "CAP-004", "CAP-005", "CAP-006"),
        forbidden_capabilities=("file_mutation", "process_execution"),
        dataset=dataset_ref,
        metrics_config=MetricsConfig(500, 2000, 0.05, 1.0),
        pass_thresholds=PassThresholds(0.8, 0.9, 0.85),
        stop_conditions=StopConditions(3, 0.2, True, 5),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    adapter = SimulatedCandidateAdapter()
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.leakage_audit_status == "PASSED"
    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert len(receipt.cohort_evaluations) == 3
    assert [e.case_id for e in receipt.cohort_evaluations] == ["CASE-001", "CASE-002", "CASE-003"]
    assert all(e.quality_result.value == "PASS" for e in receipt.cohort_evaluations)


def test_orchestrator_extraction_source_containing_token_is_clean_under_v1():
    """Verify D10: extraction source containing ground truth token is CLEAN under v1 and executes."""
    clean_ext_cases = [
        CohortCase(
            case_id="C-EXT-1",
            task_class="extraction",
            input_prompt="The target value is SECRET_TOKEN_99. Extract it.",
            ground_truth="SECRET_TOKEN_99",
            acceptable_variants=("secret_token_99",),
        ),
    ]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-EXT-CLEAN-ORCH",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=clean_ext_cases,
    )
    dataset_ref = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-EXT-CLEAN-ORCH",
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-v1", "in_memory", "sim_runtime"),
        baseline=None,
        job_to_be_done="Testing clean extraction",
        allowed_capabilities=("CAP-001", "CAP-005"),
        forbidden_capabilities=(),
        dataset=dataset_ref,
        metrics_config=MetricsConfig(500, 2000, 0.05, 1.0),
        pass_thresholds=PassThresholds(0.8, 0.9, 0.85),
        stop_conditions=StopConditions(3, 0.2, True, 5),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    adapter = SimulatedCandidateAdapter(case_responses={"C-EXT-1": "SECRET_TOKEN_99"})
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )
    assert receipt.leakage_audit_status == "PASSED"
    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert len(receipt.cohort_evaluations) == 1
    assert receipt.cohort_evaluations[0].quality_result == QualityVerdict.PASS


def test_orchestrator_unsupported_leakage_policy_fails_closed_before_execution():
    """Verify D10: unsupported leakage_policy_revision fails closed before execution with DATA/COHORT semantics."""
    contract_tmpl, cohort = _make_test_contract("EXP-UNSUPP-POLICY")
    unsupp_ds = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=99,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-UNSUPP-POLICY",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done="Testing unsupp policy",
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=unsupp_ds,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )

    class TrackingAdapter(SimulatedCandidateAdapter):
        def __init__(self):
            super().__init__()
            self.execute_case_called = False

        def execute_case(self, case):
            self.execute_case_called = True
            return super().execute_case(case)

    adapter = TrackingAdapter()
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )
    assert receipt.final_state == LifecycleState.FAILED
    assert receipt.leakage_audit_status == "FAILED"
    assert receipt.recommendation.blocker_category == "DATA/COHORT"
    assert "UNSUPPORTED_LEAKAGE_POLICY_REVISION" in receipt.stop_reason
    assert len(receipt.cohort_evaluations) == 0
    assert not adapter.execute_case_called


def test_orchestrator_forbidden_outputs_fail_grading():
    """Verify D11: exact normalized full-output match against forbidden_outputs triggers FAIL."""
    from nexus.calibration.provider_adoption.failure import FailureClass

    cases = [
        CohortCase(
            case_id="C-FORBIDDEN-1",
            task_class="classification",
            input_prompt="Classify: 'Build error.' Options: TIMEOUT, CRASH, UNKNOWN.",
            ground_truth="TIMEOUT",
            forbidden_outputs=("TIMEOUT", "CRASH"),
        ),
    ]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-FORBIDDEN-TEST",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=cases,
    )
    dataset_ref = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-FORBIDDEN-TEST",
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-v1", "in_memory", "sim_runtime"),
        baseline=None,
        job_to_be_done="Forbidden output test",
        allowed_capabilities=("CAP-001", "CAP-004"),
        forbidden_capabilities=(),
        dataset=dataset_ref,
        metrics_config=MetricsConfig(500, 2000, 0.05, 1.0),
        pass_thresholds=PassThresholds(0.8, 0.9, 0.85),
        stop_conditions=StopConditions(3, 0.2, True, 5),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    # Adapter outputs "  timeout  " which matches forbidden_outputs after normalization
    adapter = SimulatedCandidateAdapter(case_responses={"C-FORBIDDEN-1": "  timeout  "})
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )
    assert len(receipt.cohort_evaluations) == 1
    ev = receipt.cohort_evaluations[0]
    assert ev.quality_result == QualityVerdict.FAIL
    assert ev.failure_class == FailureClass.INVALID_RESPONSE.value


def test_orchestrator_forbidden_output_fails_even_if_in_acceptable_variants():
    """Verify D11: forbidden output takes precedence over acceptable_variants and ground_truth."""
    from nexus.calibration.provider_adoption.failure import FailureClass

    cases = [
        CohortCase(
            case_id="C-CONFLICT-1",
            task_class="classification",
            input_prompt="Classify: 'Build error.' Options: TIMEOUT, CRASH, UNKNOWN.",
            ground_truth="TIMEOUT",
            acceptable_variants=("timeout", "CRASH"),
            forbidden_outputs=(
                "CRASH",
            ),  # Appears in both acceptable_variants and forbidden_outputs
        ),
    ]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-CONFLICT-TEST",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=cases,
    )
    dataset_ref = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-CONFLICT-TEST",
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-v1", "in_memory", "sim_runtime"),
        baseline=None,
        job_to_be_done="Forbidden precedence test",
        allowed_capabilities=("CAP-001", "CAP-004"),
        forbidden_capabilities=(),
        dataset=dataset_ref,
        metrics_config=MetricsConfig(500, 2000, 0.05, 1.0),
        pass_thresholds=PassThresholds(0.8, 0.9, 0.85),
        stop_conditions=StopConditions(3, 0.2, True, 5),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    adapter = SimulatedCandidateAdapter(case_responses={"C-CONFLICT-1": "CRASH"})
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )
    assert len(receipt.cohort_evaluations) == 1
    ev = receipt.cohort_evaluations[0]
    assert ev.quality_result == QualityVerdict.FAIL
    assert ev.failure_class == FailureClass.INVALID_RESPONSE.value


def test_orchestrator_forbidden_output_exact_normalized_match_not_substring():
    """Verify D11: forbidden output check is exact normalized full-output match, NOT substring."""
    cases = [
        CohortCase(
            case_id="C-SUBSTR-1",
            task_class="classification",
            input_prompt="Classify: 'Build error.' Options: TIMEOUT_LONG, TIMEOUT_SHORT.",
            ground_truth="TIMEOUT_LONG",
            forbidden_outputs=("TIMEOUT",),  # "TIMEOUT" is a substring of "TIMEOUT_LONG"
        ),
    ]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-SUBSTR-TEST",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=cases,
    )
    dataset_ref = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-SUBSTR-TEST",
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-v1", "in_memory", "sim_runtime"),
        baseline=None,
        job_to_be_done="Forbidden substring test",
        allowed_capabilities=("CAP-001", "CAP-004"),
        forbidden_capabilities=(),
        dataset=dataset_ref,
        metrics_config=MetricsConfig(500, 2000, 0.05, 1.0),
        pass_thresholds=PassThresholds(0.8, 0.9, 0.85),
        stop_conditions=StopConditions(3, 0.2, True, 5),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    adapter = SimulatedCandidateAdapter(case_responses={"C-SUBSTR-1": "TIMEOUT_LONG"})
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )
    assert len(receipt.cohort_evaluations) == 1
    ev = receipt.cohort_evaluations[0]
    assert ev.quality_result == QualityVerdict.PASS


def test_orchestrator_negative_control_unsupported_capabilities_caps_at_l025_experiment_only():
    """Verify D12: high quality + only CAP-001 supported + allowed CAP-001/002/004/005/006
    caps recommendation at L0.25 / EXPERIMENT_ONLY and excludes classification/extraction/schema roles.
    """
    contract_tmpl, cohort = _make_test_contract("EXP-CAP-NEG-CTRL")
    contract = build_experiment_contract(
        experiment_id="EXP-CAP-NEG-CTRL",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done="Negative control for capability gating",
        allowed_capabilities=("CAP-001", "CAP-002", "CAP-004", "CAP-005", "CAP-006"),
        forbidden_capabilities=(),
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    # Only CAP-001 is supported; CAP-002, CAP-004, CAP-005, CAP-006 are unsupported
    adapter = SimulatedCandidateAdapter(
        supported_capabilities={"CAP-001"},
    )
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert receipt.operational_metrics.accuracy == 1.0
    rec = receipt.recommendation
    assert rec.recommended_autonomy == "L0.25"
    assert rec.recommended_state == "EXPERIMENT_ONLY"
    for forbidden_role in (
        "classification",
        "extraction",
        "simple_extraction",
        "read_only_schema_candidate",
    ):
        assert forbidden_role not in rec.recommended_roles
    assert "bounded_experiment" in rec.recommended_roles
    assert any("CAP-002" in r and "CAP-004" in r for r in rec.reasons)


def test_orchestrator_positive_control_all_capabilities_supported_retains_l1():
    """Verify D12: positive control with all required capabilities SUPPORTED retains expected L1 recommendation."""
    contract_tmpl, cohort = _make_test_contract("EXP-CAP-POS-CTRL")
    contract = build_experiment_contract(
        experiment_id="EXP-CAP-POS-CTRL",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=None,
        job_to_be_done="Positive control for capability gating",
        allowed_capabilities=("CAP-001", "CAP-002", "CAP-004", "CAP-005", "CAP-006"),
        forbidden_capabilities=(),
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )
    # All allowed capabilities supported
    adapter = SimulatedCandidateAdapter(
        supported_capabilities={"CAP-001", "CAP-002", "CAP-004", "CAP-005", "CAP-006"},
    )
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert receipt.operational_metrics.accuracy == 1.0
    rec = receipt.recommendation
    assert rec.recommended_autonomy == "L1"
    assert "classification" in rec.recommended_roles
    assert "extraction" in rec.recommended_roles
    assert "read_only_schema_candidate" in rec.recommended_roles
    assert "bounded_experiment" in rec.recommended_roles


# ============================================================================
# R3 Baseline Calibration & Comparative Evidence Tests (Settled Semantics)
# ============================================================================


def test_baseline_not_requested_candidate_behavior_unchanged():
    """Negative control 1: contract.baseline=None => NOT_REQUESTED, candidate behavior unchanged."""
    contract, cohort = _make_test_contract("EXP-BASE-NONE")
    assert contract.baseline is None

    adapter = SimulatedCandidateAdapter()
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=None,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert receipt.baseline_evaluation is not None
    assert receipt.baseline_evaluation.requested is False
    assert receipt.baseline_evaluation.status == BASELINE_STATUS_NOT_REQUESTED
    assert "not requested" in receipt.baseline_evaluation.reason.lower()
    assert receipt.baseline_evaluation.expected_identity is None
    assert receipt.baseline_evaluation.physical_identity is None
    assert len(receipt.baseline_evaluation.cohort_evaluations) == 0
    assert receipt.baseline_evaluation.operational_metrics is None
    assert receipt.baseline_evaluation.comparison.status == COMPARISON_STATUS_NOT_AVAILABLE
    assert len(receipt.cohort_evaluations) == 5
    assert receipt.operational_metrics.accuracy == 1.0

    bundle = build_evidence_bundle(contract, receipt)
    report = generate_13_question_report(bundle)
    assert "- **Baseline Evaluation:** `NOT_REQUESTED`" in report


def test_baseline_declared_adapter_none_not_evaluated_standalone_completes():
    """Negative control 2: baseline declared, adapter=None => NOT_EVALUATED, candidate completes standalone."""
    contract_tmpl, cohort = _make_test_contract("EXP-BASE-NO-ADAPTER")
    contract = build_experiment_contract(
        experiment_id="EXP-BASE-NO-ADAPTER",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity(
            provider_id="sim-baseline",
            model_id="sim-base-v1",
            transport="in_memory",
        ),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    adapter = SimulatedCandidateAdapter()
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=None,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    be = receipt.baseline_evaluation
    assert be is not None
    assert be.requested is True
    assert be.status == BASELINE_STATUS_NOT_EVALUATED
    assert "no baseline_adapter provided" in be.reason
    assert be.expected_identity == contract.baseline
    assert be.physical_identity is None
    assert len(be.cohort_evaluations) == 0
    assert be.operational_metrics is None
    assert be.comparison.status == COMPARISON_STATUS_NOT_AVAILABLE
    assert len(receipt.cohort_evaluations) == 5

    bundle = build_evidence_bundle(contract, receipt)
    report = generate_13_question_report(bundle)
    assert "- **Baseline Requested:** YES" in report
    assert "- **Baseline Status:** `NOT_EVALUATED`" in report
    assert "- **Comparison Status:** `NOT_AVAILABLE`" in report


def test_baseline_adapter_identity_mismatch_blocks_case_execution():
    """Negative control 3: baseline adapter identity mismatch => no baseline case execution."""
    contract_tmpl, cohort = _make_test_contract("EXP-BASE-MISMATCH")
    contract = build_experiment_contract(
        experiment_id="EXP-BASE-MISMATCH",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity(
            provider_id="expected-provider",
            model_id="expected-model",
            transport="in_memory",
        ),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    adapter = SimulatedCandidateAdapter()
    baseline_adapter = SimulatedCandidateAdapter(
        provider_id="other-provider",
        model_id="other-model",
        transport="in_memory",
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=baseline_adapter,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    be = receipt.baseline_evaluation
    assert be.status == BASELINE_STATUS_IDENTITY_MISMATCH
    assert "mismatch" in be.reason.lower()
    assert be.physical_identity is not None
    assert be.physical_identity.provider_id == "other-provider"
    assert len(be.cohort_evaluations) == 0  # CRUCIAL: zero baseline cases executed!
    assert be.operational_metrics is None
    assert be.comparison.status == COMPARISON_STATUS_NOT_AVAILABLE
    assert len(receipt.cohort_evaluations) == 5  # Candidate unaffected


def test_baseline_adapter_environment_blocked_status_unavailable_no_cases():
    """Negative control 4: baseline environment blocked => UNAVAILABLE, no case execution."""
    contract_tmpl, cohort = _make_test_contract("EXP-BASE-BLOCKED")
    contract = build_experiment_contract(
        experiment_id="EXP-BASE-BLOCKED",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity(
            provider_id="sim-base",
            model_id="sim-base-v1",
            transport="in_memory",
        ),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    adapter = SimulatedCandidateAdapter()
    baseline_adapter = SimulatedCandidateAdapter(
        provider_id="sim-base",
        model_id="sim-base-v1",
        transport="in_memory",
        environment_blocked=True,
        environment_blocker_reason="SIM_BASE_KEY_MISSING: API key not provided",
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=baseline_adapter,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    be = receipt.baseline_evaluation
    assert be.status == BASELINE_STATUS_UNAVAILABLE
    assert "SIM_BASE_KEY_MISSING" in be.reason
    assert len(be.cohort_evaluations) == 0  # No fake measurement!
    assert be.operational_metrics is None
    assert be.comparison.status == COMPARISON_STATUS_NOT_AVAILABLE
    assert len(receipt.cohort_evaluations) == 5  # Candidate completes standalone


def test_baseline_adapter_valid_same_cohort_evaluated_stable_run_id_comparison_available():
    """Negative control 5: valid baseline => same cohort evaluated, stable baseline_run_id, comparison available."""
    contract_tmpl, cohort = _make_test_contract("EXP-BASE-VALID")
    contract = build_experiment_contract(
        experiment_id="EXP-BASE-VALID",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity(
            provider_id="sim-base",
            model_id="sim-base-v1",
            transport="in_memory",
        ),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    adapter = SimulatedCandidateAdapter(default_latency_ms=10)
    baseline_adapter = SimulatedCandidateAdapter(
        provider_id="sim-base",
        model_id="sim-base-v1",
        transport="in_memory",
        default_latency_ms=25,
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=baseline_adapter,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    be = receipt.baseline_evaluation
    assert be.status == BASELINE_STATUS_EVALUATED
    assert len(be.cohort_evaluations) == 5
    assert be.baseline_run_id is not None
    assert be.baseline_run_id != receipt.run_id  # Independent run identity!

    # Verify single stable baseline_run_id across all baseline case records
    for ev in be.cohort_evaluations:
        assert ev.run_id == be.baseline_run_id
        assert ev.candidate_identity_digest == be.baseline_identity_digest
        assert ev.quality_result == QualityVerdict.PASS

    # Verify binding to same cohort and ground truth hashes
    assert be.cohort_id == cohort.cohort_id
    assert be.cohort_revision == cohort.cohort_revision
    assert be.cohort_sha256 == cohort.cohort_sha256
    assert be.ground_truth_revision == cohort.ground_truth_revision
    assert be.ground_truth_sha256 == cohort.ground_truth_sha256

    # Verify operational metrics
    assert be.operational_metrics is not None
    assert be.operational_metrics.total_cases == 5
    assert be.operational_metrics.accuracy == 1.0
    assert be.operational_metrics.error_rate == 0.0

    # Verify comparative evidence
    cmp = be.comparison
    assert cmp.status == COMPARISON_STATUS_AVAILABLE
    assert cmp.accuracy_delta == 0.0
    assert cmp.error_rate_delta == 0.0
    assert cmp.p50_latency_delta_ms is not None
    assert cmp.p95_latency_delta_ms is not None
    assert cmp.throughput_delta_rps is not None

    # Verify 13-question report
    bundle = build_evidence_bundle(contract, receipt)
    report = generate_13_question_report(bundle)
    assert "- **Baseline Requested:** YES" in report
    assert "- **Baseline Status:** `EVALUATED`" in report
    assert "- **Comparison Status:** `AVAILABLE`" in report
    assert "- **Metric Deltas (Candidate - Baseline):**" in report


def test_baseline_partial_stop_condition_renders_comparison_unavailable():
    """Negative control 6: baseline stop condition => STOPPED_BY_CONDITION, comparison NOT_AVAILABLE."""
    contract_tmpl, cohort = _make_test_contract(
        experiment_id="EXP-BASE-STOP",
        max_consecutive_failures=2,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-BASE-STOP",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity(
            provider_id="sim-base",
            model_id="sim-base-v1",
            transport="in_memory",
        ),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    adapter = SimulatedCandidateAdapter()  # candidate passes all 5
    baseline_adapter = SimulatedCandidateAdapter(
        provider_id="sim-base",
        model_id="sim-base-v1",
        transport="in_memory",
        fail_case_ids={"C1", "C2"},  # triggers max_consecutive_failures=2
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=baseline_adapter,
    )

    # Candidate completed cleanly and has full recommendations
    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert len(receipt.cohort_evaluations) == 5
    assert receipt.operational_metrics.accuracy == 1.0

    # Baseline stopped early and has comparison disabled
    be = receipt.baseline_evaluation
    assert be.status == BASELINE_STATUS_STOPPED_BY_CONDITION
    assert len(be.cohort_evaluations) == 2
    assert be.comparison.status == COMPARISON_STATUS_NOT_AVAILABLE
    assert "stop condition" in be.comparison.reason.lower()


def test_baseline_forbidden_outputs_semantics_identical():
    """Negative control 7: forbidden_outputs semantics identical on baseline path."""
    cohort = create_frozen_cohort(
        cohort_id="COHORT-FORBIDDEN-TEST",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[
            CohortCase(
                case_id="C1",
                task_class="classification",
                input_prompt="Input 1",
                ground_truth="PASS",
                forbidden_outputs=("FORBIDDEN_OUTPUT_VAL",),
            ),
            CohortCase("C2", "classification", "Input 2", "PASS"),
        ],
    )
    dataset_ref = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=True,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-FORBIDDEN-TEST",
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-v1", "in_memory", "sim_runtime"),
        baseline=BaselineIdentity("sim-base", "sim-base-v1", "in_memory"),
        job_to_be_done="Forbidden output test",
        allowed_capabilities=("CAP-001",),
        forbidden_capabilities=(),
        dataset=dataset_ref,
        metrics_config=MetricsConfig(500, 2000, 0.5, 1.0),
        pass_thresholds=PassThresholds(0.5, 0.5, 0.5),
        stop_conditions=StopConditions(5, 0.5, True, 10),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )

    adapter = SimulatedCandidateAdapter()
    baseline_adapter = SimulatedCandidateAdapter(
        provider_id="sim-base",
        model_id="sim-base-v1",
        transport="in_memory",
        case_responses={"C1": "FORBIDDEN_OUTPUT_VAL"},
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=baseline_adapter,
    )

    be = receipt.baseline_evaluation
    assert len(be.cohort_evaluations) == 2
    c1_eval = be.cohort_evaluations[0]
    assert c1_eval.quality_result == QualityVerdict.FAIL
    assert c1_eval.failure_class == FailureClass.INVALID_RESPONSE.value


def test_baseline_result_never_changes_candidate_g6_recommendation_or_authority():
    """Negative control 8: baseline result never changes candidate G6 recommendation/authority."""
    contract_tmpl, cohort = _make_test_contract("EXP-BASE-NO-MUTATE")

    # Run 1: No baseline
    receipt1 = run_provider_adoption_experiment(
        contract=contract_tmpl,
        cohort=cohort,
        adapter=SimulatedCandidateAdapter(),
        baseline_adapter=None,
    )

    # Run 2: Baseline with 100% accuracy, high performance
    contract2 = build_experiment_contract(
        experiment_id="EXP-BASE-PERFECT",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity("sim-base", "sim-base-v1", "in_memory"),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    receipt2 = run_provider_adoption_experiment(
        contract=contract2,
        cohort=cohort,
        adapter=SimulatedCandidateAdapter(),
        baseline_adapter=SimulatedCandidateAdapter(
            provider_id="sim-base", model_id="sim-base-v1", transport="in_memory"
        ),
    )

    # Run 3: Baseline that fails completely and stops early
    contract3 = build_experiment_contract(
        experiment_id="EXP-BASE-FAILING",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity("sim-base", "sim-base-v1", "in_memory"),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    receipt3 = run_provider_adoption_experiment(
        contract=contract3,
        cohort=cohort,
        adapter=SimulatedCandidateAdapter(),
        baseline_adapter=SimulatedCandidateAdapter(
            provider_id="sim-base",
            model_id="sim-base-v1",
            transport="in_memory",
            fail_case_ids={"C1", "C2", "C3", "C4", "C5"},
        ),
    )

    # In all three runs, candidate recommendations and authority must be completely identical!
    for r in (receipt2, receipt3):
        assert r.recommendation.verdict == receipt1.recommendation.verdict
        assert r.recommendation.recommended_autonomy == receipt1.recommendation.recommended_autonomy
        assert r.recommendation.recommended_state == receipt1.recommendation.recommended_state
        assert r.recommendation.recommended_roles == receipt1.recommendation.recommended_roles
        assert r.recommendation.clamped_by_ceiling == receipt1.recommendation.clamped_by_ceiling
        assert r.recommendation.authority_disclaimer == receipt1.recommendation.authority_disclaimer

    # Candidate lifecycle state history must NOT be mutated by baseline
    states1 = [s for s, _ in receipt1.state_history]
    states2 = [s for s, _ in receipt2.state_history]
    states3 = [s for s, _ in receipt3.state_history]
    assert states1 == states2 == states3


def test_candidate_stop_condition_skips_baseline_execution():
    """Verify that terminal candidate stop prevents any subsequent baseline execution."""
    contract_tmpl, cohort = _make_test_contract(
        experiment_id="EXP-CAND-STOP",
        max_consecutive_failures=2,
    )
    contract = build_experiment_contract(
        experiment_id="EXP-CAND-STOP",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity("sim-base", "sim-base-v1", "in_memory"),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    adapter = SimulatedCandidateAdapter(fail_case_ids={"C1", "C2"})  # candidate stops on C2

    class CountingBaselineAdapter(SimulatedCandidateAdapter):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.execute_count = 0

        def execute_case(self, case):
            self.execute_count += 1
            return super().execute_case(case)

    baseline_adapter = CountingBaselineAdapter(
        provider_id="sim-base", model_id="sim-base-v1", transport="in_memory"
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=baseline_adapter,
    )

    assert receipt.final_state == LifecycleState.STOPPED_BY_CONDITION
    assert len(receipt.cohort_evaluations) == 2
    be = receipt.baseline_evaluation
    assert be.status == BASELINE_STATUS_NOT_EVALUATED
    assert len(be.cohort_evaluations) == 0
    assert baseline_adapter.execute_count == 0
    assert be.comparison.status == COMPARISON_STATUS_NOT_AVAILABLE
    assert "Candidate cohort execution not reached" in be.comparison.reason


def test_candidate_environment_blocked_leaves_baseline_not_evaluated():
    """Verify that if candidate is blocked by environment at G1, baseline cohort is not executed."""
    contract_tmpl, cohort = _make_test_contract("EXP-CAND-BLOCKED")
    contract = build_experiment_contract(
        experiment_id="EXP-CAND-BLOCKED",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity("sim-base", "sim-base-v1", "in_memory"),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    adapter = SimulatedCandidateAdapter(
        environment_blocked=True,
        environment_blocker_reason="APPLE_FM_LICENSE_NOT_AGREED",
    )

    class BaselineMustNotBeTouched(SimulatedCandidateAdapter):
        def inspect_identity(self):
            raise AssertionError(
                "baseline identity probe must not run before candidate reaches cohort"
            )

    baseline_adapter = BaselineMustNotBeTouched(
        provider_id="sim-base", model_id="sim-base-v1", transport="in_memory"
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        baseline_adapter=baseline_adapter,
    )

    assert receipt.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    be = receipt.baseline_evaluation
    assert be.status == BASELINE_STATUS_NOT_EVALUATED
    assert len(be.cohort_evaluations) == 0
    assert be.comparison.status == COMPARISON_STATUS_NOT_AVAILABLE


class PhysicalCapableFakeAdapter(SimulatedCandidateAdapter):
    """Fake adapter declaring PHYSICAL support ceiling for negative control tests."""

    max_evidence_level = EvidenceLevel.PHYSICAL


def test_evidence_ceiling_simulated_adapter_with_requested_physical_clamps_to_simulated():
    """Negative Control 1: SimulatedCandidateAdapter + requested PHYSICAL => SIMULATED, never PHYSICAL."""
    contract, cohort = _make_test_contract("EXP-CEIL-01")
    adapter = SimulatedCandidateAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        evidence_level=EvidenceLevel.PHYSICAL,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert len(receipt.cohort_evaluations) == 5
    for ev in receipt.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.SIMULATED
        assert ev.evidence_level != EvidenceLevel.PHYSICAL


def test_evidence_ceiling_simulated_adapter_with_requested_fixture_clamps_to_fixture():
    """Negative Control 2: SimulatedCandidateAdapter + requested FIXTURE => FIXTURE."""
    contract, cohort = _make_test_contract("EXP-CEIL-02")
    adapter = SimulatedCandidateAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        evidence_level=EvidenceLevel.FIXTURE,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert len(receipt.cohort_evaluations) == 5
    for ev in receipt.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.FIXTURE


def test_evidence_ceiling_physical_capable_adapter_with_requested_simulated_underclaims():
    """Negative Control 3: Physical-capable adapter + requested SIMULATED => caller underclaim yields SIMULATED."""
    contract, cohort = _make_test_contract("EXP-CEIL-03")
    adapter = PhysicalCapableFakeAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        evidence_level=EvidenceLevel.SIMULATED,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert len(receipt.cohort_evaluations) == 5
    for ev in receipt.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.SIMULATED


def test_evidence_ceiling_physical_capable_adapter_with_requested_physical_is_physical():
    """Negative Control 4: Physical-capable adapter + requested PHYSICAL => PHYSICAL."""
    contract, cohort = _make_test_contract("EXP-CEIL-04")
    adapter = PhysicalCapableFakeAdapter()

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
        evidence_level=EvidenceLevel.PHYSICAL,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert len(receipt.cohort_evaluations) == 5
    for ev in receipt.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.PHYSICAL


def test_evidence_ceiling_candidate_physical_baseline_simulated_independent_resolution():
    """Negative Control 5: Candidate physical + baseline simulated + requested PHYSICAL
    => candidate PHYSICAL, baseline SIMULATED.
    """
    contract_tmpl, cohort = _make_test_contract("EXP-CEIL-05")
    contract = build_experiment_contract(
        experiment_id="EXP-CEIL-05",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity("sim-base", "sim-base-v1", "in_memory"),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    candidate_adapter = PhysicalCapableFakeAdapter()
    baseline_adapter = SimulatedCandidateAdapter(
        provider_id="sim-base", model_id="sim-base-v1", transport="in_memory"
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=candidate_adapter,
        baseline_adapter=baseline_adapter,
        evidence_level=EvidenceLevel.PHYSICAL,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    # Candidate evaluations are PHYSICAL
    assert len(receipt.cohort_evaluations) == 5
    for ev in receipt.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.PHYSICAL

    # Baseline evaluations MUST remain SIMULATED despite caller requesting PHYSICAL
    be = receipt.baseline_evaluation
    assert be.status == BASELINE_STATUS_EVALUATED
    assert len(be.cohort_evaluations) == 5
    for ev in be.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.SIMULATED
        assert ev.evidence_level != EvidenceLevel.PHYSICAL


def test_evidence_ceiling_baseline_physical_candidate_simulated_independent_resolution():
    """Negative Control 6: Baseline physical + candidate simulated + requested PHYSICAL
    => candidate SIMULATED, baseline PHYSICAL when baseline executes.
    """
    contract_tmpl, cohort = _make_test_contract("EXP-CEIL-06")
    contract = build_experiment_contract(
        experiment_id="EXP-CEIL-06",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity("phys-base", "phys-base-v1", "in_memory"),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    candidate_adapter = SimulatedCandidateAdapter()
    baseline_adapter = PhysicalCapableFakeAdapter(
        provider_id="phys-base", model_id="phys-base-v1", transport="in_memory"
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=candidate_adapter,
        baseline_adapter=baseline_adapter,
        evidence_level=EvidenceLevel.PHYSICAL,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    # Candidate evaluations clamped to SIMULATED
    assert len(receipt.cohort_evaluations) == 5
    for ev in receipt.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.SIMULATED
        assert ev.evidence_level != EvidenceLevel.PHYSICAL

    # Baseline evaluations are PHYSICAL
    be = receipt.baseline_evaluation
    assert be.status == BASELINE_STATUS_EVALUATED
    assert len(be.cohort_evaluations) == 5
    for ev in be.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.PHYSICAL


def test_evidence_ceiling_environment_data_stop_paths_do_not_fabricate_evaluations():
    """Negative Control 7: Blocked environment, unready ground truth, or stopped runs
    must never fabricate case evaluations or physical evidence.
    """
    contract_tmpl, cohort = _make_test_contract("EXP-CEIL-07")
    contract = build_experiment_contract(
        experiment_id="EXP-CEIL-07",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity("sim-base", "sim-base-v1", "in_memory"),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )

    # 1. Environment blocked
    blocked_adapter = PhysicalCapableFakeAdapter(
        environment_blocked=True, environment_blocker_reason="BLOCKED_BY_TEST"
    )
    receipt_env = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=blocked_adapter,
        baseline_adapter=PhysicalCapableFakeAdapter(
            provider_id="sim-base", model_id="sim-base-v1", transport="in_memory"
        ),
        evidence_level=EvidenceLevel.PHYSICAL,
    )
    assert receipt_env.final_state == LifecycleState.BLOCKED_BY_ENVIRONMENT
    assert len(receipt_env.cohort_evaluations) == 0
    assert len(receipt_env.baseline_evaluation.cohort_evaluations) == 0

    # 2. Terminal candidate stop condition
    stop_adapter = SimulatedCandidateAdapter(fail_case_ids={"C1", "C2"})
    contract_stop = build_experiment_contract(
        experiment_id="EXP-CEIL-07-STOP",
        experiment_revision=1,
        candidate=contract_tmpl.candidate,
        baseline=BaselineIdentity("sim-base", "sim-base-v1", "in_memory"),
        job_to_be_done=contract_tmpl.job_to_be_done,
        allowed_capabilities=contract_tmpl.allowed_capabilities,
        forbidden_capabilities=contract_tmpl.forbidden_capabilities,
        dataset=contract_tmpl.dataset,
        metrics_config=contract_tmpl.metrics_config,
        pass_thresholds=contract_tmpl.pass_thresholds,
        stop_conditions=StopConditions(2, 0.2, True, 5),
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling=contract_tmpl.claim_ceiling,
        created_at="2026-09-27T00:00:00Z",
    )
    receipt_stop = run_provider_adoption_experiment(
        contract=contract_stop,
        cohort=cohort,
        adapter=stop_adapter,
        baseline_adapter=PhysicalCapableFakeAdapter(
            provider_id="sim-base", model_id="sim-base-v1", transport="in_memory"
        ),
        evidence_level=EvidenceLevel.PHYSICAL,
    )
    assert receipt_stop.final_state == LifecycleState.STOPPED_BY_CONDITION
    # Candidate ran 2 cases; their level was clamped to SIMULATED, not PHYSICAL
    assert len(receipt_stop.cohort_evaluations) == 2
    for ev in receipt_stop.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.SIMULATED
    # Baseline was not run
    assert len(receipt_stop.baseline_evaluation.cohort_evaluations) == 0


def test_evidence_ceiling_default_call_backwards_compatible_as_simulated():
    """Negative Control 8: Default calls without explicit evidence_level remain SIMULATED."""
    contract, cohort = _make_test_contract("EXP-CEIL-08")
    adapter = SimulatedCandidateAdapter()

    # Call with default evidence_level (no explicit parameter)
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    assert receipt.final_state == LifecycleState.RECOMMENDATION_READY
    assert len(receipt.cohort_evaluations) == 5
    for ev in receipt.cohort_evaluations:
        assert ev.evidence_level == EvidenceLevel.SIMULATED


def test_evidence_ceiling_custom_adapter_defaults_conservatively_to_simulated():
    """Negative Control 9 / Settled Semantics 2, 14: Custom adapter that does not override
    ceiling defaults safely to SIMULATED, never PHYSICAL.
    """
    from nexus.calibration.provider_adoption.adapter import CandidateAdapter

    class BareCustomAdapter(CandidateAdapter):
        def is_environment_blocked(self):
            return False, ""

        def inspect_identity(self):
            from nexus.calibration.provider_adoption.identity import inspect_physical_host_identity

            return inspect_physical_host_identity(
                provider_id="custom",
                model_id="custom-v1",
                transport="custom_pipe",
                runtime_executable="custom_bin",
                runtime_version="1.0.0",
                adapter_generation="v1",
                model_generation="custom-gen-1",
                timestamp="2026-09-27T00:00:00Z",
                offline_verified=True,
                network_dependency_observed="NONE",
            )

        def probe_capability(self, capability_id):
            from nexus.calibration.provider_adoption.capability import (
                CapabilityProbeResult,
                CapabilityStatus,
            )

            return CapabilityProbeResult(
                capability_id=capability_id,
                status=CapabilityStatus.SUPPORTED,
                physical_evidence="ok",
                exit_code=0,
                latency_ms=10,
            )

        def execute_case(self, case):
            return case.ground_truth, True, None, 10

        def inject_fault(self, failure_class):
            from nexus.calibration.provider_adoption.failure import FailureObservationItem

            return FailureObservationItem(
                failure_class=failure_class,
                exercised=False,
                observed_fail_closed=None,
                observed_retry_behavior="NOT_EVALUATED",
                evidence_notes="",
            )

    custom_adapter = BareCustomAdapter()
    assert custom_adapter.max_evidence_level == EvidenceLevel.SIMULATED

    contract, cohort = _make_test_contract("EXP-CEIL-09")
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=custom_adapter,
        evidence_level=EvidenceLevel.PHYSICAL,
    )
    assert len(receipt.cohort_evaluations) == 5
    for ev in receipt.cohort_evaluations:
        # Bare custom adapter ceiling is SIMULATED, cannot escalate to PHYSICAL
        assert ev.evidence_level == EvidenceLevel.SIMULATED
        assert ev.evidence_level != EvidenceLevel.PHYSICAL


def test_evidence_ceiling_simulated_adapter_rejects_physical_ceiling_instantiation():
    """SimulatedCandidateAdapter cannot claim PHYSICAL ceiling at instantiation."""
    import pytest

    with pytest.raises(
        ValueError,
        match="SimulatedCandidateAdapter maximum supportable evidence level is SIMULATED",
    ):
        SimulatedCandidateAdapter(max_evidence_level=EvidenceLevel.PHYSICAL)


def test_resolve_effective_evidence_level_all_matrix_combinations():
    """Unit test for resolve_effective_evidence_level across all permutations."""
    from nexus.calibration.provider_adoption.cohort import resolve_effective_evidence_level

    # Requested PHYSICAL
    assert (
        resolve_effective_evidence_level(EvidenceLevel.PHYSICAL, EvidenceLevel.PHYSICAL)
        == EvidenceLevel.PHYSICAL
    )
    assert (
        resolve_effective_evidence_level(EvidenceLevel.PHYSICAL, EvidenceLevel.SIMULATED)
        == EvidenceLevel.SIMULATED
    )
    assert (
        resolve_effective_evidence_level(EvidenceLevel.PHYSICAL, EvidenceLevel.FIXTURE)
        == EvidenceLevel.FIXTURE
    )

    # Requested SIMULATED
    assert (
        resolve_effective_evidence_level(EvidenceLevel.SIMULATED, EvidenceLevel.PHYSICAL)
        == EvidenceLevel.SIMULATED
    )
    assert (
        resolve_effective_evidence_level(EvidenceLevel.SIMULATED, EvidenceLevel.SIMULATED)
        == EvidenceLevel.SIMULATED
    )
    assert (
        resolve_effective_evidence_level(EvidenceLevel.SIMULATED, EvidenceLevel.FIXTURE)
        == EvidenceLevel.FIXTURE
    )

    # Requested FIXTURE
    assert (
        resolve_effective_evidence_level(EvidenceLevel.FIXTURE, EvidenceLevel.PHYSICAL)
        == EvidenceLevel.FIXTURE
    )
    assert (
        resolve_effective_evidence_level(EvidenceLevel.FIXTURE, EvidenceLevel.SIMULATED)
        == EvidenceLevel.FIXTURE
    )
    assert (
        resolve_effective_evidence_level(EvidenceLevel.FIXTURE, EvidenceLevel.FIXTURE)
        == EvidenceLevel.FIXTURE
    )

    # String input support & fallback
    assert resolve_effective_evidence_level("PHYSICAL", "SIMULATED") == EvidenceLevel.SIMULATED
    assert (
        resolve_effective_evidence_level("UNKNOWN_STRING", "SIMULATED") == EvidenceLevel.SIMULATED
    )
