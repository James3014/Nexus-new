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
    create_frozen_cohort,
)
from nexus.calibration.provider_adoption.contracts import (
    AuthorityBoundary,
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
from nexus.calibration.provider_adoption.identity import PhysicalIdentity
from nexus.calibration.provider_adoption.orchestrator import (
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


def test_orchestrator_unready_ground_truth_blocks_benchmark_6_5():
    """Verify Invariant 6.5: ground truth not ready blocks benchmark."""
    contract, cohort = _make_test_contract("EXP-GT-UNREADY")
    # Mark cohort ground truth as unready
    unready_cohort = create_frozen_cohort(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cohort.cases,
        ground_truth_ready=False,
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
    contract_tmpl, cohort = _make_test_contract("EXP-THRESH-FAIL")
    # Pass thresholds requiring 100% accuracy and 100% format compliance
    strict_thresholds = PassThresholds(
        accuracy_min=0.99,
        format_compliance_min=0.99,
        semantic_correctness_min=0.99,
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
        pass_thresholds=strict_thresholds,
        stop_conditions=contract_tmpl.stop_conditions,
        environment_constraints=contract_tmpl.environment_constraints,
        authority_boundary=contract_tmpl.authority_boundary,
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
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
