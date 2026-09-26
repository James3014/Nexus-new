"""Unit tests for G2 Capability Matrix module in Provider Adoption Framework."""

import json

from nexus.calibration.provider_adoption.capability import (
    CAP_001_PLAIN_TEXT,
    CAP_002_STRUCTURED_JSON,
    CapabilityStatus,
    create_initial_capability_matrix,
    evaluate_capability_probe,
)


def test_initial_capability_matrix_all_not_evaluated():
    matrix = create_initial_capability_matrix()
    for cid, probe in matrix.probes.items():
        assert probe.status == CapabilityStatus.NOT_EVALUATED
    assert not matrix.is_supported(CAP_001_PLAIN_TEXT)


def test_capability_false_green_exit_zero_empty_output_fails_6_2():
    """Verify Invariant 6.2: exit code 0 with empty output is NOT SUPPORTED."""
    res = evaluate_capability_probe(
        CAP_001_PLAIN_TEXT,
        executed=True,
        exit_code=0,
        output_text="   \n  ",
        latency_ms=10,
    )
    assert res.status == CapabilityStatus.UNSUPPORTED
    assert "empty or whitespace" in res.physical_evidence


def test_capability_false_green_semantic_validation_failure():
    """Verify Invariant 6.2: output failing semantic validator is not SUPPORTED."""

    def json_validator(text: str) -> tuple[bool, str]:
        try:
            json.loads(text)
            return True, ""
        except Exception as e:
            return False, f"JSON parse error: {e}"

    # Invalid JSON output despite exit 0
    res = evaluate_capability_probe(
        CAP_002_STRUCTURED_JSON,
        executed=True,
        exit_code=0,
        output_text="Not a JSON object",
        latency_ms=15,
        semantic_validator=json_validator,
    )
    assert res.status == CapabilityStatus.PARTIAL
    assert "failed semantic validation" in res.physical_evidence


def test_capability_physical_success_proves_supported():
    res = evaluate_capability_probe(
        CAP_001_PLAIN_TEXT,
        executed=True,
        exit_code=0,
        output_text="Hello world from candidate.",
        latency_ms=25,
    )
    assert res.status == CapabilityStatus.SUPPORTED
    assert "Physical execution succeeded" in res.physical_evidence


def test_unprobed_capabilities_serialize_as_not_evaluated_no_draft():
    """Verify that unprobed capabilities strictly serialize and read back as NOT_EVALUATED and never DRAFT."""
    from nexus.calibration.provider_adoption.adapter import SimulatedCandidateAdapter
    from nexus.calibration.provider_adoption.capability import ALL_CAPABILITY_IDS
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
    from nexus.calibration.provider_adoption.orchestrator import (
        run_provider_adoption_experiment,
    )

    cohort = create_frozen_cohort(
        cohort_id="COHORT-MIN",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[
            CohortCase(
                case_id="C1",
                task_class="plain",
                input_prompt="Hi",
                ground_truth="Hi",
            )
        ],
    )
    contract = build_experiment_contract(
        experiment_id="EXP-CAP-ISOLATION",
        experiment_revision=1,
        candidate=CandidateIdentity("sim", "m1", "in_memory", "rt"),
        baseline=None,
        job_to_be_done="Test capability isolation",
        allowed_capabilities=(CAP_001_PLAIN_TEXT,),  # ONLY CAP-001
        forbidden_capabilities=(),
        dataset=DatasetRef(
            cohort_id=cohort.cohort_id,
            cohort_revision=cohort.cohort_revision,
            cohort_sha256=cohort.cohort_sha256,
            ground_truth_revision=cohort.ground_truth_revision,
            ground_truth_sha256=cohort.ground_truth_sha256,
            leakage_policy_revision=1,
            cohort_type=cohort.cohort_type,
            ground_truth_ready=True,
        ),
        metrics_config=MetricsConfig(
            latency_p50_max_ms=500,
            latency_p95_max_ms=2000,
            max_error_rate=0.05,
            min_throughput_rps=1.0,
        ),
        pass_thresholds=PassThresholds(
            accuracy_min=0.5,
            format_compliance_min=0.5,
            semantic_correctness_min=0.5,
        ),
        stop_conditions=StopConditions(
            max_consecutive_failures=5,
            max_error_rate=0.5,
            safety_abort_on_timeout=True,
        ),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )

    receipt = run_provider_adoption_experiment(
        contract=contract,
        adapter=SimulatedCandidateAdapter(),
        cohort=cohort,
    )

    cap_dict = receipt.capability_matrix.to_dict()
    cap_json_str = json.dumps(cap_dict)

    # Ensure DRAFT never appears in serialized capability matrix
    assert "DRAFT" not in cap_json_str

    # Ensure CAP-001 was evaluated (SUPPORTED)
    assert cap_dict["probes"][CAP_001_PLAIN_TEXT]["status"] == "SUPPORTED"

    # Deserialization / readback test
    readback = json.loads(cap_json_str)
    assert readback["schema"] == "nexus.provider_experiment.capability_matrix.v1"
    assert "DRAFT" not in json.dumps(readback)

    # Ensure all other canonical capabilities CAP-002..CAP-011 are NOT_EVALUATED upon serialization and readback
    for cap_id in ALL_CAPABILITY_IDS:
        if cap_id != CAP_001_PLAIN_TEXT:
            probe = cap_dict["probes"][cap_id]
            assert probe["status"] == "NOT_EVALUATED"
            assert probe["status"] != "DRAFT"

            readback_probe = readback["probes"][cap_id]
            assert readback_probe["status"] == "NOT_EVALUATED"
            assert readback_probe["status"] != "DRAFT"
