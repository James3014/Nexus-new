import pytest

from nexus.calibration.provider_adoption.cohort import (
    CohortCase,
    CohortType,
    FrozenCohort,
    audit_cohort_leakage,
    compute_cohort_hashes,
    create_frozen_cohort,
    validate_contract_cohort_binding,
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


def test_apple_fm_v3_fixture_cohort_is_frozen_and_leakage_clean():
    from scripts.bench.experimental.run_provider_adoption_experiment import (
        build_apple_fm_fixture_cohort,
    )

    cohort = build_apple_fm_fixture_cohort()
    assert cohort.cohort_id == "COHORT-APPLE-FM-DETERMINISTIC-V3"
    assert cohort.cohort_revision == 5
    assert cohort.ground_truth_revision == 5
    assert (
        cohort.cohort_sha256 == "cbaee34f6618411f67575f1e17a62603227f895dd62cc81f74ed6185e72479e7"
    )
    assert (
        cohort.ground_truth_sha256
        == "e94c5f57205ee8782b0f52eda8ebeeebe8d3f43651106b57c293be0670e539d8"
    )
    assert len(cohort.cases) == 8
    assert {case.task_class for case in cohort.cases} == {"classification", "extraction"}
    is_clean, issues = audit_cohort_leakage(cohort, policy_revision=1)
    assert is_clean is True
    assert issues == []


def test_cohort_separate_input_and_ground_truth_hashes():
    cases = [
        CohortCase("C1", "classification", "Classify this error", "TIMEOUT"),
        CohortCase("C2", "extraction", "Extract port from :8080", "8080"),
    ]
    cohort_hash, gt_hash = compute_cohort_hashes(cases)
    assert cohort_hash != gt_hash
    assert len(cohort_hash) == 64
    assert len(gt_hash) == 64

    # Changing ground truth does NOT change cohort_hash
    cases_gt_changed = [
        CohortCase("C1", "classification", "Classify this error", "AUTH_FAIL"),
        CohortCase("C2", "extraction", "Extract port from :8080", "8080"),
    ]
    cohort_hash_2, gt_hash_2 = compute_cohort_hashes(cases_gt_changed)
    assert cohort_hash == cohort_hash_2
    assert gt_hash != gt_hash_2


def test_cohort_provenance_distinction_fix_6_5():
    """Verify Invariant 6.5: distinct cohort types for fixtures vs benchmark."""
    cases = [CohortCase("C1", "classification", "Input text", "PASS")]

    fixture_cohort = create_frozen_cohort(
        cohort_id="COHORT-FIXTURE",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=cases,
    )
    assert fixture_cohort.cohort_type == "FIXTURE_COHORT"

    benchmark_cohort = create_frozen_cohort(
        cohort_id="COHORT-BENCHMARK",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cases,
    )
    assert benchmark_cohort.cohort_type == "BENCHMARK_COHORT"


def test_leakage_defense_audit():
    # Leaky case: prompt contains the ground truth in non-extraction task
    leaky_case = CohortCase(
        "C-LEAK",
        "summarization",
        "The ground truth error code is ERR_404. What is it?",
        "ERR_404",
    )
    cohort_leaky = create_frozen_cohort(
        cohort_id="COHORT-LEAK",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[leaky_case],
    )
    is_clean, issues = audit_cohort_leakage(cohort_leaky)
    assert not is_clean
    assert len(issues) == 1
    assert "leaks ground truth" in issues[0]

    # Clean case
    clean_case = CohortCase(
        "C-CLEAN",
        "classification",
        "Is system memory full?",
        "YES",
    )
    cohort_clean = create_frozen_cohort(
        cohort_id="COHORT-CLEAN",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[clean_case],
    )
    is_clean2, issues2 = audit_cohort_leakage(cohort_clean)
    assert is_clean2
    assert len(issues2) == 0


def test_classification_multiple_choice_options_not_flagged_as_leakage():
    """Verify legitimate classification multiple-choice options are clean and not flagged."""
    # Inline options list (exact CASE-001 pattern from CLI smoke)
    case_inline = CohortCase(
        case_id="CASE-001",
        task_class="classification",
        input_prompt="Classify the sentiment of this text: 'The build passed cleanly without errors.' Options: POSITIVE, NEGATIVE, NEUTRAL.",
        ground_truth="POSITIVE",
        acceptable_variants=("positive", "POSITIVE."),
    )
    cohort = create_frozen_cohort(
        cohort_id="COHORT-INLINE-OPTS",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[case_inline],
    )
    is_clean, issues = audit_cohort_leakage(cohort)
    assert is_clean
    assert len(issues) == 0

    # Multiline bulleted options list
    case_multiline = CohortCase(
        case_id="CASE-BULLETS",
        task_class="classification",
        input_prompt="Classify priority:\nOptions:\n- HIGH\n- MEDIUM\n- LOW",
        ground_truth="HIGH",
    )
    cohort_multiline = create_frozen_cohort(
        cohort_id="COHORT-BULLETS",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[case_multiline],
    )
    is_clean_m, issues_m = audit_cohort_leakage(cohort_multiline)
    assert is_clean_m
    assert len(issues_m) == 0

    # Choices with 'or' delimiter
    case_or = CohortCase(
        case_id="CASE-OR",
        task_class="classification",
        input_prompt="Classify the state of the service. Choices: HEALTHY or UNHEALTHY.",
        ground_truth="HEALTHY",
    )
    cohort_or = create_frozen_cohort(
        cohort_id="COHORT-OR",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[case_or],
    )
    is_clean_or, issues_or = audit_cohort_leakage(cohort_or)
    assert is_clean_or
    assert len(issues_or) == 0


def test_leakage_policy_v1_semantics():
    """Verify Policy Revision 1 leakage semantics:
    - Extraction source containing ground truth token is CLEAN under v1.
    - Classification with premise leakage outside option list remains LEAK.
    - Classification single-option list remains LEAK.
    - Other task classes (e.g. summarization) leaking ground truth fail closed.
    - Unsupported policy revision fails closed.
    """
    # 1. Extraction source containing SECRET_TOKEN_99 is CLEAN under v1
    case_extract = CohortCase(
        case_id="C-EXTRACT-CLEAN",
        task_class="extraction",
        input_prompt="The target value is SECRET_TOKEN_99. Extract it.",
        ground_truth="SECRET_TOKEN_99",
    )
    cohort_ext = create_frozen_cohort(
        cohort_id="COHORT-EXT-CLEAN",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[case_extract],
    )
    is_clean, issues = audit_cohort_leakage(cohort_ext, policy_revision=1)
    assert is_clean
    assert len(issues) == 0

    # 2. Classification with premise leakage outside option list remains LEAK
    case_class_leak = CohortCase(
        case_id="C-CLASS-PREMISE-LEAK",
        task_class="classification",
        input_prompt="The answer is POSITIVE. Classify: 'The build passed.' Options: POSITIVE, NEGATIVE, NEUTRAL.",
        ground_truth="POSITIVE",
    )
    cohort_class_leak = create_frozen_cohort(
        cohort_id="COHORT-CLASS-LEAK",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[case_class_leak],
    )
    is_clean_cl, issues_cl = audit_cohort_leakage(cohort_class_leak, policy_revision=1)
    assert not is_clean_cl
    assert len(issues_cl) == 1
    assert (
        "Case C-CLASS-PREMISE-LEAK leaks ground truth 'POSITIVE' in input prompt." in issues_cl[0]
    )

    # 3. Single-option list does not count as legitimate multiple choice
    case_single = CohortCase(
        case_id="C-SINGLE-OPT",
        task_class="classification",
        input_prompt="Classify: 'Build passed.' Options: POSITIVE.",
        ground_truth="POSITIVE",
    )
    cohort_single = create_frozen_cohort(
        cohort_id="COHORT-SINGLE",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[case_single],
    )
    is_clean_s, issues_s = audit_cohort_leakage(cohort_single, policy_revision=1)
    assert not is_clean_s
    assert "Case C-SINGLE-OPT leaks ground truth 'POSITIVE' in input prompt." in issues_s[0]

    # 4. Other task classes (e.g. summarization) leaking ground truth fail closed
    case_sum_leak = CohortCase(
        case_id="C-SUM-LEAK",
        task_class="summarization",
        input_prompt="The error code is SECRET_TOKEN_99. Summarize the incident.",
        ground_truth="SECRET_TOKEN_99",
    )
    cohort_sum = create_frozen_cohort(
        cohort_id="COHORT-SUM-LEAK",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=[case_sum_leak],
    )
    is_clean_sum, issues_sum = audit_cohort_leakage(cohort_sum, policy_revision=1)
    assert not is_clean_sum
    assert "Case C-SUM-LEAK leaks ground truth 'SECRET_TOKEN_99' in input prompt." in issues_sum[0]

    # 5. Unsupported leakage policy revision fails closed
    is_clean_unsupp, issues_unsupp = audit_cohort_leakage(cohort_ext, policy_revision=99)
    assert not is_clean_unsupp
    assert "UNSUPPORTED_LEAKAGE_POLICY_REVISION" in issues_unsupp[0]


def _make_contract_for_cohort(cohort: FrozenCohort, **dataset_overrides):
    ds_kwargs = {
        "cohort_id": cohort.cohort_id,
        "cohort_revision": cohort.cohort_revision,
        "cohort_sha256": cohort.cohort_sha256,
        "ground_truth_revision": cohort.ground_truth_revision,
        "ground_truth_sha256": cohort.ground_truth_sha256,
        "leakage_policy_revision": 1,
        "cohort_type": cohort.cohort_type,
        "ground_truth_ready": cohort.ground_truth_ready,
    }
    ds_kwargs.update(dataset_overrides)
    dataset = DatasetRef(**ds_kwargs)
    return build_experiment_contract(
        experiment_id="EXP-COHORT-BIND",
        experiment_revision=1,
        candidate=CandidateIdentity("simulated", "sim-1", "in_memory", "rt"),
        baseline=None,
        job_to_be_done="Cohort binding test",
        allowed_capabilities=("CAP-001",),
        forbidden_capabilities=(),
        dataset=dataset,
        metrics_config=MetricsConfig(500, 2000, 0.05, 1.0),
        pass_thresholds=PassThresholds(0.8, 0.9, 0.85),
        stop_conditions=StopConditions(3, 0.2, True, 5),
        environment_constraints=EnvironmentConstraints("Darwin", "arm64", 8),
        authority_boundary=AuthorityBoundary(),
        claim_ceiling="L1",
        created_at="2026-09-27T00:00:00Z",
    )


def test_validate_contract_cohort_binding_success():
    cases = [CohortCase("C1", "classification", "Input text", "PASS")]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-OK",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cases,
    )
    contract = _make_contract_for_cohort(cohort)
    # Must succeed without exception
    validate_contract_cohort_binding(contract, cohort)


def test_negative_control_cohort_hash_mismatch_fails_closed():
    """Verify D2: cohort_sha256 mismatch fails closed with exact error."""
    cases = [CohortCase("C1", "classification", "Input text", "PASS")]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-HASH-TEST",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cases,
    )
    contract = _make_contract_for_cohort(cohort, cohort_sha256="0" * 64)
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Contract cohort_sha256"):
        validate_contract_cohort_binding(contract, cohort)


def test_negative_control_ground_truth_hash_mismatch_fails_closed():
    """Verify D2: ground_truth_sha256 mismatch fails closed with exact error."""
    cases = [CohortCase("C1", "classification", "Input text", "PASS")]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-GT-HASH-TEST",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cases,
    )
    contract = _make_contract_for_cohort(cohort, ground_truth_sha256="f" * 64)
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Contract ground_truth_sha256"):
        validate_contract_cohort_binding(contract, cohort)


def test_negative_control_cohort_id_and_revision_mismatch_fails_closed():
    """Verify D2: cohort_id or cohort_revision mismatch fails closed."""
    cases = [CohortCase("C1", "classification", "Input text", "PASS")]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-ID-TEST",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cases,
    )
    # ID mismatch
    contract_id = _make_contract_for_cohort(cohort, cohort_id="WRONG-COHORT-ID")
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Contract cohort_id"):
        validate_contract_cohort_binding(contract_id, cohort)

    # Revision mismatch
    contract_rev = _make_contract_for_cohort(cohort, cohort_revision=99)
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Contract cohort_revision"):
        validate_contract_cohort_binding(contract_rev, cohort)


def test_negative_control_cohort_type_and_gt_ready_mismatch_fails_closed():
    """Verify D2: cohort_type and ground_truth_ready mismatch fail closed."""
    cases = [CohortCase("C1", "classification", "Input text", "PASS")]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-META-TEST",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cases,
        ground_truth_ready=True,
    )
    # Type mismatch
    contract_type = _make_contract_for_cohort(cohort, cohort_type="FIXTURE_COHORT")
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Contract cohort_type"):
        validate_contract_cohort_binding(contract_type, cohort)

    # Ground truth ready mismatch
    contract_gt = _make_contract_for_cohort(cohort, ground_truth_ready=False)
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Contract ground_truth_ready"):
        validate_contract_cohort_binding(contract_gt, cohort)


def test_negative_control_tampered_cohort_cases_hash_fails_closed():
    """Verify D2: case tampering invalidating computed hashes fails closed."""
    cases = [CohortCase("C1", "classification", "Input text", "PASS")]
    cohort = create_frozen_cohort(
        cohort_id="COHORT-TAMPER",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=cases,
    )
    contract = _make_contract_for_cohort(cohort)

    # Tamper cases while keeping declared cohort_sha256 unchanged
    tampered_cases = [CohortCase("C1", "classification", "Tampered input prompt", "PASS")]
    tampered_cohort = FrozenCohort(
        schema=cohort.schema,
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_type=cohort.cohort_type,
        cases=tuple(tampered_cases),
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        ground_truth_ready=cohort.ground_truth_ready,
    )
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Cohort declared cohort_sha256"):
        validate_contract_cohort_binding(contract, tampered_cohort)

    # Tamper ground truth while keeping declared ground_truth_sha256 unchanged
    tampered_gt_cases = [CohortCase("C1", "classification", "Input text", "TAMPERED_GT")]
    tampered_gt_cohort = FrozenCohort(
        schema=cohort.schema,
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_type=cohort.cohort_type,
        cases=tuple(tampered_gt_cases),
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        ground_truth_ready=cohort.ground_truth_ready,
    )
    with pytest.raises(
        ValueError, match="DATASET_COHORT_MISMATCH: Cohort declared ground_truth_sha256"
    ):
        validate_contract_cohort_binding(contract, tampered_gt_cohort)


def test_cohort_hash_changes_on_difficulty_mutation():
    """Verify D9: difficulty mutation changes cohort_sha256 but preserves ground_truth_sha256."""
    case_med = CohortCase("C1", "classification", "Input text", "PASS", difficulty="medium")
    case_hard = CohortCase("C1", "classification", "Input text", "PASS", difficulty="hard")
    cohort_hash_med, gt_hash_med = compute_cohort_hashes([case_med])
    cohort_hash_hard, gt_hash_hard = compute_cohort_hashes([case_hard])
    assert cohort_hash_med != cohort_hash_hard
    assert gt_hash_med == gt_hash_hard


def test_cohort_hash_changes_on_metadata_mutation():
    """Verify D9: metadata mutation changes cohort_sha256 but preserves ground_truth_sha256."""
    case_meta1 = CohortCase(
        "C1", "classification", "Input text", "PASS", metadata={"domain": "finance"}
    )
    case_meta2 = CohortCase(
        "C1", "classification", "Input text", "PASS", metadata={"domain": "health"}
    )
    case_empty_meta = CohortCase("C1", "classification", "Input text", "PASS", metadata={})
    cohort_hash_1, gt_hash_1 = compute_cohort_hashes([case_meta1])
    cohort_hash_2, gt_hash_2 = compute_cohort_hashes([case_meta2])
    cohort_hash_empty, gt_hash_empty = compute_cohort_hashes([case_empty_meta])

    assert cohort_hash_1 != cohort_hash_2
    assert cohort_hash_1 != cohort_hash_empty
    assert gt_hash_1 == gt_hash_2 == gt_hash_empty


def test_negative_control_difficulty_mutation_invalidates_contract_binding():
    """Verify D9: mutating difficulty invalidates contract binding and fails closed."""
    case_orig = CohortCase("C1", "classification", "Input text", "PASS", difficulty="medium")
    cohort = create_frozen_cohort(
        cohort_id="COHORT-DIFF-TEST",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=[case_orig],
    )
    contract = _make_contract_for_cohort(cohort)

    # Tamper case difficulty
    tampered_case = CohortCase("C1", "classification", "Input text", "PASS", difficulty="hard")
    tampered_cohort = FrozenCohort(
        schema=cohort.schema,
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_type=cohort.cohort_type,
        cases=(tampered_case,),
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        ground_truth_ready=cohort.ground_truth_ready,
    )
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Cohort declared cohort_sha256"):
        validate_contract_cohort_binding(contract, tampered_cohort)


def test_negative_control_metadata_mutation_invalidates_contract_binding():
    """Verify D9: mutating metadata invalidates contract binding and fails closed."""
    case_orig = CohortCase(
        "C1", "classification", "Input text", "PASS", metadata={"source": "v1_annotated"}
    )
    cohort = create_frozen_cohort(
        cohort_id="COHORT-META-MUT-TEST",
        cohort_revision=1,
        cohort_type=CohortType.BENCHMARK_COHORT,
        cases=[case_orig],
    )
    contract = _make_contract_for_cohort(cohort)

    # Tamper case metadata
    tampered_case = CohortCase(
        "C1", "classification", "Input text", "PASS", metadata={"source": "tampered"}
    )
    tampered_cohort = FrozenCohort(
        schema=cohort.schema,
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_type=cohort.cohort_type,
        cases=(tampered_case,),
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        ground_truth_ready=cohort.ground_truth_ready,
    )
    with pytest.raises(ValueError, match="DATASET_COHORT_MISMATCH: Cohort declared cohort_sha256"):
        validate_contract_cohort_binding(contract, tampered_cohort)
