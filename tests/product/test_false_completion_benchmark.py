from dataclasses import replace

from product.benchmark import (
    BENCHMARK_SCHEMA,
    CASES,
    FalseCompletionReport,
    run_benchmark,
    verify_report,
)


def test_fixed_suite_is_repeatable_and_detects_every_hostile_case():
    first = run_benchmark()
    second = run_benchmark()
    assert len(CASES) >= 20
    assert first.canonical_json() == second.canonical_json()
    assert first.report_hash == second.report_hash
    assert first.schema == BENCHMARK_SCHEMA
    assert first.infra_invalid_count == 0
    assert first.detected_count == first.hostile_case_count
    assert first.false_completion_count == 0
    assert first.public_claim_gate == "FAIL_CLOSED_EXPERIMENTAL"
    assert verify_report(first) == ()


def test_report_verifier_rejects_mutations():
    report = run_benchmark()
    for field, value in (
        ("case_ids", tuple(reversed(report.case_ids))),
        ("detected_count", report.detected_count + 1),
        ("claim_ceiling", report.claim_ceiling + ("MERGE",)),
    ):
        mutated = replace(report, **{field: value})
        assert verify_report(mutated)


def test_controller_callable_returns_immutable_objects():
    report = run_benchmark()
    assert isinstance(report, FalseCompletionReport)
    assert isinstance(report.case_ids, tuple)
    assert isinstance(report.cases, tuple)
