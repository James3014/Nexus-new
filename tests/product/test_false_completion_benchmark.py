from dataclasses import replace

from product.benchmark import (
    BENCHMARK_SCHEMA,
    CASE_SPEC,
    CASES,
    EXPECTED_CASE_IDS,
    FalseCompletionReport,
    _digest,
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


def _rehash(payload):
    payload = dict(payload)
    payload["report_hash"] = _digest({k: v for k, v in payload.items() if k != "report_hash"})
    return payload


def test_literal_suite_contract_and_full_mutation_matrix():
    report = run_benchmark()
    assert len(CASES) == len(EXPECTED_CASE_IDS) == len(CASE_SPEC) == 27
    base = report.payload()
    top_level = {
        "schema": "wrong",
        "benchmark_id": "wrong",
        "task_set_hash": "sha256:" + "0" * 64,
        "protocol_version": "wrong",
        "implementation_schema": "wrong",
        "case_ids": list(reversed(base["case_ids"])),
        "eligible_count": -1,
        "infra_invalid_count": -1,
        "hostile_case_count": -1,
        "detected_count": -1,
        "false_completion_count": -1,
        "false_completion_rate": 0.5,
        "detection_rate": 0.5,
        "trust_mismatch_count": -1,
        "trust_mismatch_rate": 0.5,
        "public_claim_gate": "OPEN",
        "claim_ceiling": ["MERGE"],
    }
    for field, value in top_level.items():
        assert field in verify_report(_rehash({**base, field: value}))
    for index in range(len(base["cases"])):
        for field, value in (
            ("case_id", "duplicate"),
            ("detected", not base["cases"][index]["detected"]),
            ("infra_invalid", True),
            ("error", "tampered"),
        ):
            cases = list(base["cases"])
            cases[index] = {**cases[index], field: value}
            assert f"cases[{index}].{field}" in verify_report(_rehash({**base, "cases": cases}))
        for outcome in ("expected", "actual"):
            for field in (
                "outcome_kind",
                "verification_status",
                "evidence_condition",
                "disposition",
            ):
                item = dict(base["cases"][index][outcome])
                item[field] = "WRONG_VALUE"
                case = {**base["cases"][index], outcome: item}
                cases = list(base["cases"])
                cases[index] = case
                assert f"cases[{index}].{outcome}.{field}" in verify_report(
                    _rehash({**base, "cases": cases})
                )
    for cases in (base["cases"][:-1], base["cases"][1:], base["cases"] + [base["cases"][0]]):
        assert "cases" in verify_report(_rehash({**base, "cases": cases}))
