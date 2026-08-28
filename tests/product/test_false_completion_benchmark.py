import ast
import math
from dataclasses import replace
from pathlib import Path

import product.benchmark as bm
from product.benchmark import (
    BENCHMARK_ID, BENCHMARK_SCHEMA, CASES, CASE_SPEC, EXPECTED_CASE_IDS,
    TASK_SET_HASH, CaseDefinition, CaseOutcome, _build, _digest, _make_specs,
    _run, run_benchmark, verify_report,
)


def _rehash(payload):
    body = {k: v for k, v in payload.items() if k != "report_hash"}
    return {**body, "report_hash": _digest(body)}


def test_normal_suite_descriptor_hash_repeatability_and_gate():
    first, second = run_benchmark(), run_benchmark()
    assert len(CASES) == len(CASE_SPEC) == len(EXPECTED_CASE_IDS) == 25
    assert first.canonical_json() == second.canonical_json()
    assert first.report_hash == second.report_hash
    assert (first.schema, first.benchmark_id, first.task_set_hash) == (BENCHMARK_SCHEMA, BENCHMARK_ID, TASK_SET_HASH)
    assert first.case_ids == EXPECTED_CASE_IDS
    assert tuple((c.case_id, c.hostile, c.expected, c.operation, c.params) for c in CASES) == CASE_SPEC
    assert (first.eligible_count, first.hostile_case_count, first.detected_count, first.false_completion_count) == (25, 24, 24, 0)
    assert (first.infra_invalid_count, first.false_completion_rate, first.detection_rate, first.trust_mismatch_rate) == (0, 0.0, 1.0, 0.0)
    assert verify_report(first) == ()


def test_exported_globals_cannot_rebind_run_or_verifier(monkeypatch):
    genuine = run_benchmark()
    fake = CaseDefinition("fake", False, CaseOutcome("CERTIFICATION"), "reject", {"kind": "status"})
    for name, value in {"CASES": (fake,), "CASE_SPEC": (("fake", False, "CERTIFICATION", "reject", ()),), "EXPECTED_CASE_IDS": ("fake",), "TASK_SET_HASH": "sha256:" + "f" * 64}.items():
        monkeypatch.setattr(bm, name, value)
        assert run_benchmark().canonical_json() == genuine.canonical_json()
        assert run_benchmark().report_hash == genuine.report_hash
    assert verify_report(genuine) == ()
    forged = _rehash({**genuine.payload(), "task_set_hash": bm.TASK_SET_HASH})
    assert verify_report(forged)


def test_report_verifier_rejects_full_mutation_matrix_with_rehashed_attacks():
    base = run_benchmark().payload()
    top_values = {
        "schema": "wrong", "benchmark_id": "wrong", "task_set_hash": "sha256:" + "0" * 64,
        "protocol_version": "wrong", "implementation_schema": "wrong", "case_ids": list(reversed(base["case_ids"])),
        "eligible_count": -1, "infra_invalid_count": -1, "hostile_case_count": -1, "detected_count": -1,
        "false_completion_count": -1, "false_completion_rate": 0.5, "detection_rate": 0.5,
        "trust_mismatch_count": -1, "trust_mismatch_rate": 0.5, "public_claim_gate": "OPEN", "claim_ceiling": ["MERGE"],
    }
    for field, value in top_values.items():
        assert field in verify_report(_rehash({**base, field: value}))
    for i, original in enumerate(base["cases"]):
        for field, value in (("case_id", "renamed"), ("detected", not original["detected"]), ("infra_invalid", True), ("error", "tampered")):
            cases = list(base["cases"]); cases[i] = {**original, field: value}
            assert verify_report(_rehash({**base, "cases": cases}))
        for section in ("expected", "actual"):
            for field in ("outcome_kind", "verification_status", "evidence_condition", "disposition"):
                outcome = {**original[section], field: "WRONG"}; cases = list(base["cases"]); cases[i] = {**original, section: outcome}
                assert verify_report(_rehash({**base, "cases": cases}))
    for cases in (base["cases"][:-1], base["cases"][1:], base["cases"] + [base["cases"][0]], list(reversed(base["cases"]))):
        errors = verify_report(_rehash({**base, "cases": cases}))
        assert "cases" in errors or any(x.startswith("cases[") for x in errors)


def test_strict_schema_types_unknown_missing_and_nested_fields():
    base = run_benchmark().payload()
    for field in tuple(k for k in base if k != "report_hash"):
        missing = dict(base); missing.pop(field)
        assert verify_report(_rehash(missing))
    missing_hash = dict(base); missing_hash.pop("report_hash")
    assert verify_report(missing_hash)
    assert "unexpected" in verify_report(_rehash({**base, "unexpected": True}))
    for field in ("eligible_count", "infra_invalid_count", "hostile_case_count", "detected_count", "false_completion_count", "trust_mismatch_count"):
        value = dict(base); value[field] = True
        assert field in verify_report(_rehash(value))
    for field in ("false_completion_rate", "detection_rate", "trust_mismatch_rate"):
        for bad in (1, True, float("nan"), float("inf"), float("-inf")):
            value = dict(base); value[field] = bad
            if isinstance(bad, float) and not math.isfinite(bad):
                assert verify_report(value)
            else:
                assert field in verify_report(_rehash(value))
    for field in ("cases", "case_ids", "claim_ceiling"):
        value = dict(base); value[field] = "bad"
        assert field in verify_report(_rehash(value))
    case = dict(base["cases"][0]); case["actual"] = {**case["actual"], "disposition": 1}
    assert "cases[0].actual.disposition" in verify_report(_rehash({**base, "cases": [case] + base["cases"][1:]}))
    for field in ("case_id", "expected", "actual", "detected", "infra_invalid", "error"):
        case = dict(base["cases"][0]); case.pop(field)
        assert verify_report(_rehash({**base, "cases": [case] + base["cases"][1:]}))
    for section in ("expected", "actual"):
        for field in ("outcome_kind", "verification_status", "evidence_condition", "disposition"):
            outcome = dict(base["cases"][0][section]); outcome.pop(field)
            case = {**base["cases"][0], section: outcome}
            assert verify_report(_rehash({**base, "cases": [case] + base["cases"][1:]}))


def test_false_completion_predicate_parity_for_malformed_kind():
    spec = (CaseDefinition("malformed", True, CaseOutcome("CERTIFIED"), "x", {}),)
    result = _run(spec, lambda _op, _params: CaseOutcome("CERTIFIED", disposition="CERTIFIED"))[0]
    assert result.detected is False
    assert not bm._false(spec[0], result.actual)
    report = _build(spec, (result,))
    assert (report.false_completion_count, report.false_completion_rate) == (0, 0.0)


def test_zero_eligible_hostile_and_hostile_denominator():
    spec = tuple(replace(c, hostile=True, operation="hostile") for c in _make_specs()[:2])
    all_infra = _run(spec, lambda _op, _params: (_ for _ in ()).throw(RuntimeError("infra")))
    report = _build(spec, all_infra)
    assert (report.eligible_count, report.infra_invalid_count) == (0, 2)
    assert report.false_completion_rate is report.detection_rate is report.trust_mismatch_rate is None
    certified = _run(spec, lambda _op, _params: CaseOutcome("CERTIFICATION", disposition="CERTIFIED"))[0]
    report = _build(spec, (certified, all_infra[1]))
    assert (report.eligible_count, report.hostile_case_count, report.false_completion_count, report.false_completion_rate) == (1, 1, 1, 1.0)


def test_canonicalizer_rejects_hostile_values_and_verifier_never_raises():
    cyclic = []; cyclic.append(cyclic)
    for value in (float("nan"), float("inf"), cyclic, b"bytes", {"x"}, object(), {1: "key"}):
        try: _digest(value)
        except (TypeError, ValueError): pass
        else: raise AssertionError(value)
    for malformed in ({"report_hash": "bad"}, {"cases": cyclic}, {"schema": object()}):
        assert verify_report(malformed)


def test_ast_verifier_has_no_execution_dependency_and_stdlib_product_imports_only():
    tree = ast.parse(Path(bm.__file__).read_text())
    verifier = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "verify_report")
    calls = [n.func.id for n in ast.walk(verifier) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "run_benchmark" not in calls
    assert not any(name in calls for name in ("_run", "_dispatch", "_build_report", "_aggregate_report"))
    roots = []
    for node in tree.body:
        if isinstance(node, ast.Import): roots.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module: roots.append(node.module.split(".")[0])
    assert set(roots) <= {"__future__", "hashlib", "json", "math", "dataclasses", "fractions", "types", "typing", "product"}
    bad = run_benchmark().payload(); bad["report_hash"] = "sha256:" + "0" * 64
    assert verify_report(bad) == ("report_hash",)
