"""Unit tests for G3 Frozen Evaluation Cohort in Provider Adoption Framework."""

from nexus.calibration.provider_adoption.cohort import (
    CohortCase,
    CohortType,
    audit_cohort_leakage,
    compute_cohort_hashes,
    create_frozen_cohort,
)


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
    # Leaky case: prompt contains the ground truth
    leaky_case = CohortCase(
        "C-LEAK",
        "extraction",
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
