from __future__ import annotations

from collections import Counter
from pathlib import Path

from scripts.ops.run_golden_behavior_eval import SCENARIOS, validate_corpus
from tests.golden_behavior.corpus import CASES, FINDINGS


def test_corpus_is_structurally_valid() -> None:
    assert validate_corpus() == []


def test_corpus_has_requested_size_and_taxonomy() -> None:
    assert 50 <= len(CASES) <= 100
    assert {case.scenario for case in CASES} == SCENARIOS
    assert {case.classification for case in CASES} == {
        "invariant",
        "regression",
        "compatibility",
        "security",
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


def test_recently_resolved_findings_are_covered() -> None:
    resolved = [case for case in CASES if case.case_id in {"GB-082", "GB-083"}]
    assert len(resolved) == 2
    assert all(case.status == "covered" for case in resolved)
    assert all(case.automated_tests for case in resolved)


def test_workforce_policy_wording_is_post_route_only() -> None:
    root = Path(__file__).resolve().parents[2]
    policy = (root / "docs/arch/MODEL_WORKFORCE_POLICY.md").read_text(encoding="utf-8")
    assert "## 6. Routing policy" not in policy
    assert "Nexus must route in this order:" not in policy
    assert "## 6. Post-route worker dispatch guidance" in policy
    assert "These preferences never choose or revise a route" in policy
