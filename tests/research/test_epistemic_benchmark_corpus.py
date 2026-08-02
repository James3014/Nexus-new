"""
Epistemic Workflow Benchmark v0 — Corpus Tests.

Tests for corpus.py: 18 required case IDs, oracle classification,
hash integrity, and oracle leakage prevention.
"""
import hashlib
import json
from typing import Any, Dict

import pytest

from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_CASE_SCHEMA,
    BENCHMARK_ORACLE_SCHEMA,
    BenchmarkDecision,
    DefectSeverity,
    OracleClass,
    validate_oracle_record,
    validate_public_case,
)
from nexus.research.epistemic_benchmark.corpus import (
    REQUIRED_CASE_IDS,
    get_all_oracles,
    get_oracle,
    get_public_case,
    get_public_corpus,
    get_corpus_version,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Test 1: Exactly 18 required case IDs
# ---------------------------------------------------------------------------


def test_exactly_18_required_ids():
    assert len(REQUIRED_CASE_IDS) == 18
    expected = [f"EBR-{i:03d}" for i in range(1, 19)]
    assert REQUIRED_CASE_IDS == expected


def test_corpus_has_exactly_18_cases():
    cases = get_public_corpus()
    assert len(cases) == 18


def test_all_required_ids_present():
    cases = get_public_corpus()
    ids = {c["case_id"] for c in cases}
    for required_id in REQUIRED_CASE_IDS:
        assert required_id in ids, f"Missing case: {required_id}"


# ---------------------------------------------------------------------------
# Test 2: Two CLEAN / ACCEPT controls
# ---------------------------------------------------------------------------


def test_two_clean_controls():
    oracles = get_all_oracles()
    clean = [o for o in oracles if o["oracle_class"] == OracleClass.CLEAN.value]
    assert len(clean) == 2
    assert {o["case_id"] for o in clean} == {"EBR-001", "EBR-018"}


def test_clean_cases_have_accept():
    for case_id in ("EBR-001", "EBR-018"):
        oracle = get_oracle(case_id)
        assert oracle is not None
        assert oracle["oracle_decision"] == BenchmarkDecision.ACCEPT.value


# ---------------------------------------------------------------------------
# Test 3: Fourteen DEFECTIVE / REJECT cases
# ---------------------------------------------------------------------------


def test_fourteen_defective_cases():
    oracles = get_all_oracles()
    defective = [o for o in oracles if o["oracle_class"] == OracleClass.DEFECTIVE.value]
    assert len(defective) == 14


def test_defective_cases_have_reject():
    oracles = get_all_oracles()
    for o in oracles:
        if o["oracle_class"] == OracleClass.DEFECTIVE.value:
            assert o["oracle_decision"] == BenchmarkDecision.REJECT.value, (
                f"{o['case_id']}: DEFECTIVE should have REJECT"
            )


# ---------------------------------------------------------------------------
# Test 4: Two INDETERMINATE / BLOCK cases
# ---------------------------------------------------------------------------


def test_two_indeterminate_cases():
    oracles = get_all_oracles()
    indet = [o for o in oracles if o["oracle_class"] == OracleClass.INDETERMINATE.value]
    assert len(indet) == 2
    assert {o["case_id"] for o in indet} == {"EBR-016", "EBR-017"}


def test_indeterminate_cases_have_block():
    for case_id in ("EBR-016", "EBR-017"):
        oracle = get_oracle(case_id)
        assert oracle is not None
        assert oracle["oracle_decision"] == BenchmarkDecision.BLOCK.value


# ---------------------------------------------------------------------------
# Test 5: Every case has public evidence
# ---------------------------------------------------------------------------


def test_every_case_has_public_evidence():
    cases = get_public_corpus()
    for c in cases:
        assert len(c.get("available_evidence_refs", [])) >= 1, (
            f"{c['case_id']}: no evidence refs"
        )


def test_every_case_has_two_or_more_materials():
    cases = get_public_corpus()
    for c in cases:
        mats = c.get("materials", [])
        assert len(mats) >= 2, f"{c['case_id']}: has only {len(mats)} materials"


# ---------------------------------------------------------------------------
# Test 6: Every defect is observable from public refs
# ---------------------------------------------------------------------------


def test_every_defect_supporting_ref_is_in_public_case():
    cases = get_public_corpus()
    cases_by_id = {c["case_id"]: c for c in cases}
    oracles = get_all_oracles()
    for oracle in oracles:
        case_id = oracle["case_id"]
        case = cases_by_id[case_id]
        public_refs = {m["ref"] for m in case.get("materials", [])}
        public_refs |= set(case.get("available_evidence_refs", []))
        for defect in oracle.get("known_defects", []):
            for ref in defect.get("supporting_public_refs", []):
                assert ref in public_refs, (
                    f"{case_id}: defect {defect['defect_id']} "
                    f"refs {ref!r} not in public case"
                )


# ---------------------------------------------------------------------------
# Test 7: Public corpus has no oracle fields
# ---------------------------------------------------------------------------


ORACLE_FIELDS = {
    "oracle_class", "oracle_decision", "known_defects",
    "oracle", "required_detection", "defect_ids", "oracle_sha256",
    "expected_answer",
}


def test_public_corpus_has_no_oracle_fields():
    cases = get_public_corpus()
    for case in cases:
        leaked = ORACLE_FIELDS & set(case.keys())
        assert not leaked, f"{case['case_id']}: oracle fields leaked: {leaked}"


def test_public_corpus_no_oracle_strings_in_values():
    """Oracle strings must not appear in material content either."""
    cases = get_public_corpus()
    forbidden_substrings = ("oracle_class", "oracle_decision", "known_defects", "oracle_sha256")
    for case in cases:
        serialized = _canonical(case)
        for forbidden in forbidden_substrings:
            assert forbidden not in serialized, (
                f"{case['case_id']}: oracle string '{forbidden}' found in public case"
            )


# ---------------------------------------------------------------------------
# Test 8: Oracle hashes valid and consistent
# ---------------------------------------------------------------------------


def test_oracle_hashes_valid():
    oracles = get_all_oracles()
    assert len(oracles) == 18
    for oracle in oracles:
        errors = validate_oracle_record(oracle)
        assert not errors, f"{oracle['case_id']}: {errors}"


def test_oracle_hashes_are_recomputable():
    oracles = get_all_oracles()
    for oracle in oracles:
        body = {k: v for k, v in oracle.items() if k != "oracle_sha256"}
        expected = _sha256(_canonical(body))
        assert oracle["oracle_sha256"] == expected, (
            f"{oracle['case_id']}: oracle_sha256 mismatch"
        )


# ---------------------------------------------------------------------------
# Test 9: Case hashes valid
# ---------------------------------------------------------------------------


def test_case_hashes_valid():
    cases = get_public_corpus()
    for case in cases:
        errors = validate_public_case(case)
        assert not errors, f"{case['case_id']}: {errors}"


def test_case_hashes_are_recomputable():
    cases = get_public_corpus()
    for case in cases:
        body = {k: v for k, v in case.items() if k != "public_case_sha256"}
        expected = _sha256(_canonical(body))
        assert case["public_case_sha256"] == expected, (
            f"{case['case_id']}: public_case_sha256 mismatch"
        )


# ---------------------------------------------------------------------------
# Test 10: No duplicate defect IDs within a case
# ---------------------------------------------------------------------------


def test_no_duplicate_defect_ids_within_case():
    oracles = get_all_oracles()
    for oracle in oracles:
        defect_ids = [d["defect_id"] for d in oracle.get("known_defects", [])]
        assert len(defect_ids) == len(set(defect_ids)), (
            f"{oracle['case_id']}: duplicate defect IDs: {defect_ids}"
        )


# ---------------------------------------------------------------------------
# Bonus: schema fields and corpus version
# ---------------------------------------------------------------------------


def test_all_cases_have_correct_schema():
    cases = get_public_corpus()
    for c in cases:
        assert c["schema"] == BENCHMARK_CASE_SCHEMA, f"{c['case_id']}: wrong schema"


def test_all_oracles_have_correct_schema():
    oracles = get_all_oracles()
    for o in oracles:
        assert o["schema"] == BENCHMARK_ORACLE_SCHEMA, f"{o['case_id']}: wrong schema"


def test_corpus_version():
    assert get_corpus_version() == "v0"


def test_all_defects_have_valid_severity():
    oracles = get_all_oracles()
    valid_severities = {s.value for s in DefectSeverity}
    for oracle in oracles:
        for defect in oracle.get("known_defects", []):
            assert defect["severity"] in valid_severities, (
                f"{oracle['case_id']}: invalid severity {defect['severity']!r}"
            )


def test_case_materials_sorted_by_ref():
    cases = get_public_corpus()
    for case in cases:
        mats = case.get("materials", [])
        refs = [m["ref"] for m in mats]
        assert refs == sorted(refs), f"{case['case_id']}: materials not sorted"


def test_case_material_refs_unique():
    cases = get_public_corpus()
    for case in cases:
        mats = case.get("materials", [])
        refs = [m["ref"] for m in mats]
        assert len(refs) == len(set(refs)), f"{case['case_id']}: duplicate refs"


def test_case_material_hashes_correct():
    cases = get_public_corpus()
    for case in cases:
        for m in case.get("materials", []):
            content = m.get("content", "")
            expected = _sha256(content if isinstance(content, str) else _canonical(content))
            assert m["sha256"] == expected, (
                f"{case['case_id']}: material {m['ref']} sha256 mismatch"
            )
