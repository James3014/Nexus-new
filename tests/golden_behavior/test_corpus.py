from __future__ import annotations

from collections import Counter

from scripts.ops.run_golden_behavior_eval import SCENARIOS, validate_corpus
from tests.golden_behavior.corpus import CASES, FINDINGS


def test_corpus_is_structurally_valid() -> None:
    assert validate_corpus() == []


def test_corpus_has_requested_size_and_taxonomy() -> None:
    assert 50 <= len(CASES) <= 100
    assert {case.scenario for case in CASES} == SCENARIOS
    assert {case.classification for case in CASES} == {
        "invariant", "regression", "compatibility", "security",
    }


def test_every_case_has_expected_behavior_and_authority() -> None:
    assert all(case.expected_behavior.strip() for case in CASES)
    assert all(case.authority_sources for case in CASES)


def test_findings_are_explicit_and_do_not_claim_coverage() -> None:
    finding_cases = [case for case in CASES if case.status == "finding"]
    assert {case.finding_id for case in finding_cases} == set(FINDINGS)
    assert all(case.status != "covered" for case in finding_cases)


def test_automated_coverage_is_the_majority() -> None:
    counts = Counter(case.status for case in CASES)
    assert counts["covered"] >= 70
    assert counts["finding"] >= 1


def test_finding_and_resolved_regression_statuses_are_distinct() -> None:
    case = next(case for case in CASES if case.case_id == "GB-076")
    assert case.status == "finding"
    policy_lane = next(case for case in CASES if case.case_id == "GB-081")
    assert policy_lane.status == "covered"
    assert len(policy_lane.automated_tests) == 3


def test_resolved_policy_lane_finding_is_now_covered() -> None:
    case = next(case for case in CASES if case.case_id == "GB-081")
    assert case.status == "covered"
    assert len(case.automated_tests) == 3


def test_testable_open_findings_bind_automated_probes() -> None:
    probes = {
        case.case_id: case.finding_probe
        for case in CASES
        if case.finding_probe
    }
    assert probes == {
        "GB-082": "workforce_wording",
        "GB-083": "manifest_updater_idempotency",
    }
