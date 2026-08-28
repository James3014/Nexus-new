import ast
from dataclasses import replace
from pathlib import Path

import product.benchmark as benchmark_module
from product.benchmark import (
    BENCHMARK_SCHEMA,
    CASE_SPEC,
    CASES,
    EXPECTED_CASE_IDS,
    CaseOutcome,
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


def test_rehashed_case_id_and_case_order_mutations_are_rejected():
    base = run_benchmark().payload()
    duplicate_ids = list(base["case_ids"])
    duplicate_ids[1] = duplicate_ids[0]
    assert "case_ids" in verify_report(_rehash({**base, "case_ids": duplicate_ids}))
    renamed_ids = list(base["case_ids"])
    renamed_ids[1] = "renamed_case"
    assert "case_ids" in verify_report(_rehash({**base, "case_ids": renamed_ids}))
    reversed_cases = list(reversed(base["cases"]))
    errors = verify_report(_rehash({**base, "cases": reversed_cases}))
    assert "cases" in errors or any(error.startswith("cases[") for error in errors)


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
    assert len(CASES) == len(EXPECTED_CASE_IDS) == len(CASE_SPEC) == 25
    assert tuple(case.case_id for case in CASES) == EXPECTED_CASE_IDS
    assert tuple((case.case_id, case.hostile, case.expected) for case in CASES) == CASE_SPEC
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


def test_rehashed_unknown_fields_and_hostile_infra_denominator():
    report = run_benchmark().payload()
    assert "unexpected" in verify_report(_rehash({**report, "unexpected": True}))
    case = {**report["cases"][0], "unexpected": True}
    assert "cases[0].unexpected" in verify_report(
        _rehash({**report, "cases": [case] + report["cases"][1:]})
    )
    outcome = {**report["cases"][0]["actual"], "unexpected": True}
    case = {**report["cases"][0], "actual": outcome}
    assert "cases[0].actual.unexpected" in verify_report(
        _rehash({**report, "cases": [case] + report["cases"][1:]})
    )


def test_production_denominator_excludes_hostile_infra(monkeypatch):
    cases = list(CASES)
    cases[1] = replace(
        cases[1], run=lambda: CaseOutcome("CERTIFICATION", "VERIFIED", "VALID", "CERTIFIED")
    )
    cases[3] = replace(cases[3], run=lambda: (_ for _ in ()).throw(RuntimeError("synthetic infra")))
    monkeypatch.setattr(benchmark_module, "CASES", tuple(cases))
    report = run_benchmark()
    assert (report.eligible_count, report.infra_invalid_count, report.hostile_case_count) == (
        24,
        1,
        23,
    )
    assert (report.false_completion_count, report.false_completion_rate) == (1, round(1 / 23, 12))
    assert (report.detected_count, report.detection_rate) == (22, round(22 / 23, 12))
    assert (report.trust_mismatch_count, report.trust_mismatch_rate) == (1, round(1 / 24, 12))
    assert verify_report(report) == ()


def test_ast_boundaries_and_exact_report_hash_mutation():
    source_path = Path(benchmark_module.__file__)
    tree = ast.parse(source_path.read_text())
    verifier = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "verify_report"
    )
    calls = [
        node.func.id
        for node in ast.walk(verifier)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "run_benchmark" not in calls
    assert not any(name in calls for name in ("_metrics", "_aggregate_report", "_build_report"))
    roots = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.append(node.module.split(".")[0])
    assert set(roots) <= {
        "__future__",
        "hashlib",
        "json",
        "dataclasses",
        "fractions",
        "typing",
        "product",
    }
    imported_text = " ".join(roots).lower()
    assert not any(
        token in imported_text
        for token in (
            "model",
            "provider",
            "network",
            "github",
            "mcp",
            "planner",
            "workforce",
            "runtime",
        )
    )
    report = run_benchmark().payload()
    bad = dict(report)
    bad["report_hash"] = "sha256:" + "0" * 64
    assert verify_report(bad) == ("report_hash",)
