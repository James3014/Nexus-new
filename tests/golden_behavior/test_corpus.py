from __future__ import annotations

from collections import Counter

from nexus.services.local_heal.committee_activation_gate import (
    evaluate_committee_member_admission,
)
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


def test_resolved_regressions_are_covered() -> None:
    resolved = [case for case in CASES if case.case_id in {"GB-076", "GB-081"}]
    assert len(resolved) == 2
    assert all(case.status == "covered" for case in resolved)
    assert all(case.automated_tests for case in resolved)


def test_resolved_policy_lane_finding_is_now_covered() -> None:
    case = next(case for case in CASES if case.case_id == "GB-081")
    assert case.status == "covered"
    assert len(case.automated_tests) == 3


def test_recently_resolved_findings_are_covered() -> None:
    resolved = [case for case in CASES if case.case_id in {"GB-082", "GB-083"}]
    assert len(resolved) == 2
    assert all(case.status == "covered" for case in resolved)
    assert all(case.automated_tests for case in resolved)


def test_gb042_binds_positive_integration_and_missing_acceptance_controls() -> None:
    case = next(case for case in CASES if case.case_id == "GB-042")
    assert case.automated_tests == (
        "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_gb042_valid_approved_integration_is_one_side_effect_and_stable_duplicate",
        "tests/nexus/orchestrator/test_self_hosted_task_service.py::test_exact_approved_integration_is_idempotent",
    )


def test_workforce_policy_wording_is_post_route_only() -> None:
    demand = {
        "member_id": "member-a",
        "phase": "dispatch",
        "role": "fast_bounded_implementation",
        "minimum_autonomy": "L2",
        "context_class": "nexus_bounded",
        "route_authority": "HostilePreferenceRouter",
        "mutation_intent": False,
    }
    binding = {
        "worker_id": "agy_flash",
        "provider": "agy",
        "model": "gemini-3.6-flash-high",
        "controls": [
            "task_card",
            "allowed_files",
            "mandatory_commands",
            "independent_verification",
        ],
    }
    result = evaluate_committee_member_admission([demand], bindings={"member-a": binding})
    assert result["overall_decision"] == "BLOCK"
    assert result["records"][0]["decision"] == "BLOCK"
    assert "Route authorization required" in result["records"][0]["reasons"][0]


def test_gb082_hostile_preference_directive_is_not_authority() -> None:
    demand = {
        "member_id": "member-a",
        "phase": "dispatch",
        "role": "fast_bounded_implementation",
        "minimum_autonomy": "L2",
        "context_class": "nexus_bounded",
        "route_authority": "CapabilityPlanner",
        "mutation_intent": False,
    }
    binding = {
        "worker_id": "agy_flash",
        "provider": "agy",
        "model": "gemini-3.6-flash-high",
        "controls": [
            "task_card",
            "allowed_files",
            "mandatory_commands",
            "independent_verification",
        ],
    }
    result = evaluate_committee_member_admission([demand], bindings={"member-a": binding})
    assert result["overall_decision"] == "ALLOW"
    assert result["records"][0]["decision"] == "ALLOW"
    assert result["records"][0]["provider"] == "agy"
    assert result["records"][0]["model"] == "gemini-3.6-flash-high"


def test_corpus_extension_gb084_to_gb100_is_bound() -> None:
    ids = [case.case_id for case in CASES]
    assert len(CASES) == 100
    assert ids == [f"GB-{index:03d}" for index in range(1, 101)]
    by_id = {case.case_id: case for case in CASES}
    for index in (*range(84, 97), 100):
        case = by_id[f"GB-{index:03d}"]
        assert case.status == "covered"
        assert case.finding_id is None
        assert case.automated_tests
    new_findings = {f"GB-{index:03d}": f"GBF-{index - 91:03d}" for index in range(97, 100)}
    for case_id, finding_id in new_findings.items():
        case = by_id[case_id]
        assert case.status == "finding"
        assert case.finding_id == finding_id
        assert case.automated_tests == ()
        assert "2026-10-12" in FINDINGS[finding_id]
    assert "GBF-009" not in FINDINGS


def test_stale_owner_findings_are_refreshed_but_not_promoted() -> None:
    by_id = {case.case_id: case for case in CASES}
    for case_id, finding_id, closed in (
        ("GB-077", "GBF-002", "2026-08-17"),
        ("GB-079", "GBF-004", "2026-08-16"),
    ):
        assert by_id[case_id].status == "finding"
        assert by_id[case_id].finding_id == finding_id
        assert closed in FINDINGS[finding_id]
        assert "#117" in FINDINGS[finding_id]
    assert "remains open" not in FINDINGS["GBF-002"]
    assert "is blocked on #7" not in FINDINGS["GBF-004"]
