"""
Tests for Epistemic Benchmark Contracts.
"""
import pytest
from nexus.research.epistemic_benchmark.contracts import (
    BENCHMARK_CASE_SCHEMA,
    BENCHMARK_ORACLE_SCHEMA,
    BENCHMARK_ARM_SCHEMA,
    BENCHMARK_PACKET_SCHEMA,
    BENCHMARK_RUN_SCHEMA,
    BENCHMARK_OBSERVATION_SCHEMA,
    BENCHMARK_REPORT_SCHEMA,
    FORBIDDEN_TRUTH_STATUSES,
    BenchmarkArm,
    BenchmarkDecision,
    OracleClass,
    DefectSeverity,
    validate_public_case,
    validate_oracle_record,
    validate_packet,
    validate_observation,
    compute_canonical_sha256,
    validate_sha256,
    _sha256,
)
import hashlib, json


def _canonical_json(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _make_material(ref, type_, content):
    return {"ref": ref, "type": type_, "sha256": _sha256_str(content), "content": content}


def _make_minimal_case(**overrides):
    mats = sorted([
        _make_material("mat-a", "test_report", "content_a"),
        _make_material("mat-b", "evidence_summary", "content_b"),
    ], key=lambda m: m["ref"])
    body = {
        "schema": BENCHMARK_CASE_SCHEMA,
        "case_id": "TEST-001",
        "case_version": "v0",
        "title_neutral": "A neutral title",
        "task_contract": "Review this candidate.",
        "candidate_summary": "Candidate summary here.",
        "materials": mats,
        "available_evidence_refs": ["mat-a"],
        "response_contract": "Return ACCEPT, REJECT, or BLOCK.",
    }
    body.update(overrides)
    # Recompute hash
    body_for_hash = {k: v for k, v in body.items() if k != "public_case_sha256"}
    body["public_case_sha256"] = compute_canonical_sha256(body_for_hash)
    return body


def _make_minimal_oracle(case_id="TEST-001", **overrides):
    body = {
        "schema": BENCHMARK_ORACLE_SCHEMA,
        "case_id": case_id,
        "oracle_class": "CLEAN",
        "oracle_decision": "ACCEPT",
        "known_defects": [],
        "indeterminate_reason": "",
    }
    body.update(overrides)
    body_for_hash = {k: v for k, v in body.items() if k != "oracle_sha256"}
    body["oracle_sha256"] = compute_canonical_sha256(body_for_hash)
    return body


def _make_minimal_packet(**overrides):
    common_mat = _make_material("mat-a", "test_report", "content_a")
    body = {
        "schema": BENCHMARK_PACKET_SCHEMA,
        "benchmark_run_id": "BRN-ABC123",
        "arm": "standard_review",
        "arm_protocol_version": "STANDARD_REVIEW_V1",
        "case_alias": "CASE-ABCD1234ABCD1234",
        "case_version": "v0",
        "common_materials": {"task_contract": "Review this.", "candidate_summary": "Sum.",
                              "materials": [common_mat], "available_evidence_refs": ["mat-a"]},
        "common_materials_sha256": "a" * 64,
        "arm_overlay": {"review_instruction": "Return ACCEPT, REJECT, or BLOCK."},
        "response_contract": "Return ACCEPT, REJECT, or BLOCK.",
    }
    body.update(overrides)
    body_for_hash = {k: v for k, v in body.items() if k != "packet_sha256"}
    body["packet_sha256"] = compute_canonical_sha256(body_for_hash)
    return body


# ---------------------------------------------------------------------------
# Test 1: Closed enums
# ---------------------------------------------------------------------------

def test_01_closed_enums():
    assert set(e.value for e in BenchmarkArm) == {"standard_review", "strong_protocol", "epistemic_workflow"}
    assert set(e.value for e in BenchmarkDecision) == {"ACCEPT", "REJECT", "BLOCK"}
    assert set(e.value for e in OracleClass) == {"CLEAN", "DEFECTIVE", "INDETERMINATE"}
    assert set(e.value for e in DefectSeverity) == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


# ---------------------------------------------------------------------------
# Test 2: Case exact keys
# ---------------------------------------------------------------------------

def test_02_case_exact_keys():
    case = _make_minimal_case()
    errors = validate_public_case(case)
    assert errors == [], f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# Test 3: Oracle exact keys
# ---------------------------------------------------------------------------

def test_03_oracle_exact_keys():
    oracle = _make_minimal_oracle()
    errors = validate_oracle_record(oracle)
    assert errors == [], f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# Test 4: Packet exact keys
# ---------------------------------------------------------------------------

def test_04_packet_exact_keys():
    packet = _make_minimal_packet()
    errors = validate_packet(packet)
    assert errors == [], f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# Test 5: Invalid hash rejected
# ---------------------------------------------------------------------------

def test_05_invalid_hash_rejected():
    # Case with wrong hash
    case = _make_minimal_case()
    case["public_case_sha256"] = "not_a_valid_hash"
    errors = validate_public_case(case)
    assert any("SHA256" in e or "sha256" in e.lower() for e in errors)

    # Oracle with invalid hash
    oracle = _make_minimal_oracle()
    oracle["oracle_sha256"] = "bad"
    errors = validate_oracle_record(oracle)
    assert any("SHA256" in e.upper() for e in errors)


# ---------------------------------------------------------------------------
# Test 6: Duplicate refs rejected
# ---------------------------------------------------------------------------

def test_06_duplicate_refs_rejected():
    mat = _make_material("mat-a", "test", "content_a")
    case = _make_minimal_case(materials=[mat, mat])
    errors = validate_public_case(case)
    assert any("DUPLICATE" in e.upper() or "MISMATCH" in e.upper() or "SORTED" in e.upper() for e in errors)


# ---------------------------------------------------------------------------
# Test 7: Oracle ref must exist in public materials
# ---------------------------------------------------------------------------

def test_07_oracle_ref_must_exist_in_case():
    case = _make_minimal_case()
    oracle = _make_minimal_oracle()
    # Add defect with ref that doesn't exist in case
    oracle_body = {k: v for k, v in oracle.items() if k != "oracle_sha256"}
    oracle_body["oracle_class"] = "DEFECTIVE"
    oracle_body["oracle_decision"] = "REJECT"
    oracle_body["known_defects"] = [{
        "defect_id": "D1",
        "severity": "HIGH",
        "category": "test",
        "description": "desc",
        "required_detection": True,
        "supporting_public_refs": ["nonexistent-ref"],
    }]
    oracle_body["oracle_sha256"] = compute_canonical_sha256(oracle_body)
    errors = validate_oracle_record(oracle_body, case)
    assert any("REF_NOT_IN_CASE" in e or "not_in_case" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Test 8: Unknown enum rejected
# ---------------------------------------------------------------------------

def test_08_unknown_enum_rejected():
    oracle = _make_minimal_oracle()
    oracle_body = {k: v for k, v in oracle.items() if k != "oracle_sha256"}
    oracle_body["oracle_class"] = "UNKNOWN_CLASS"
    oracle_body["oracle_sha256"] = compute_canonical_sha256(oracle_body)
    errors = validate_oracle_record(oracle_body)
    assert any("INVALID" in e for e in errors)

    packet = _make_minimal_packet()
    packet_body = {k: v for k, v in packet.items() if k != "packet_sha256"}
    packet_body["arm"] = "invalid_arm"
    packet_body["packet_sha256"] = compute_canonical_sha256(packet_body)
    errors = validate_packet(packet_body)
    assert any("INVALID" in e for e in errors)


# ---------------------------------------------------------------------------
# Test 9: Forbidden truth statuses absent from enums
# ---------------------------------------------------------------------------

def test_09_forbidden_truth_statuses_absent():
    all_enum_values = (
        {e.value for e in BenchmarkArm}
        | {e.value for e in BenchmarkDecision}
        | {e.value for e in OracleClass}
        | {e.value for e in DefectSeverity}
    )
    for forbidden in FORBIDDEN_TRUTH_STATUSES:
        assert forbidden not in all_enum_values, f"Forbidden status in enum: {forbidden}"
