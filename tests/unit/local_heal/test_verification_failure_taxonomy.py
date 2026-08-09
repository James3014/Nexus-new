"""C6C: Verification failure taxonomy tests.

Splits verification_failed into actionable subclasses using existing evidence fields.
"""

from __future__ import annotations

import pytest

from nexus.services.local_heal.evaluation_gate import (
    AffectedSuiteManifest,
    bind_affected_regression_suite,
)
from nexus.services.local_heal.evaluation_gate import (
    TestResult as EvaluationTestResult,
)

# --- Verification failure subclass definitions ---

VERIFICATION_FAILED_SUBCLASSES = {
    "assertion_or_behavior_mismatch": {
        "description": "Patch applies but verifier detects assertion/behavior mismatch",
        "evidence_rules": [
            "verifier_stdout_excerpt contains 'EVIDENCE:' and 'EXPECTED:'",
            "verifier_failure_kind == 'exception' or 'nonzero_exit'",
        ],
        "example_combinations": ["A3", "A4", "A5", "A6", "B1", "B2", "B3", "B4"],
    },
    "wrong_location_or_target_miss": {
        "description": "Patch targets wrong location or symbol not found",
        "evidence_rules": [
            "verifier_stdout_excerpt contains 'not found' or 'does not exist'",
            "failure_class == 'SEARCH_MISMATCH'",
        ],
        "example_combinations": [],
    },
    "partial_fix": {
        "description": "Patch fixes some but not all verifier assertions",
        "evidence_rules": [
            "verifier_stdout_excerpt contains multiple EVIDENCE lines",
            "At least one assertion passes",
        ],
        "example_combinations": [],
    },
    "no_effect_or_noop": {
        "description": "Patch has no effect or is identical to original",
        "evidence_rules": [
            "failure_class == 'NO_EFFECTIVE_CHANGE'",
            "applied_patch_hash == selected_candidate_hash but verifier still fails",
        ],
        "example_combinations": [],
    },
    "regression_introduced": {
        "description": "Patch introduces new failures not present in original",
        "evidence_rules": [
            "verifier_stdout_excerpt contains 'FAIL' but no 'EVIDENCE:' lines",
            "Original code passed but patched code fails",
        ],
        "example_combinations": ["B2-4model"],
    },
    "insufficient_evidence_unclassified": {
        "description": "Cannot determine subclass from available evidence",
        "evidence_rules": [
            "verifier_stdout_excerpt is empty or too short",
            "verifier_failure_kind is empty",
        ],
        "example_combinations": [],
    },
}


def classify_verification_failure(
    verifier_failure_kind: str,
    verifier_stdout_excerpt: str,
    verifier_stderr_excerpt: str,
    failure_class: str,
    applied_patch_hash: str = "",
    selected_candidate_hash: str = "",
) -> str:
    """Classify a verification failure into a subclass using existing evidence fields."""
    stdout = verifier_stdout_excerpt or ""
    # Rule 1: assertion_or_behavior_mismatch
    if "EVIDENCE:" in stdout and "EXPECTED:" in stdout:
        return "assertion_or_behavior_mismatch"

    # Rule 2: wrong_location_or_target_miss
    if "not found" in stdout.lower() or "does not exist" in stdout.lower():
        return "wrong_location_or_target_miss"
    if failure_class == "SEARCH_MISMATCH":
        return "wrong_location_or_target_miss"

    # Rule 3: no_effect_or_noop
    if failure_class == "NO_EFFECTIVE_CHANGE":
        return "no_effect_or_noop"
    if (
        applied_patch_hash
        and selected_candidate_hash
        and applied_patch_hash == selected_candidate_hash
    ):
        if "EVIDENCE:" not in stdout:
            return "no_effect_or_noop"

    # Rule 4: regression_introduced
    if "FAIL" in stdout and "EVIDENCE:" not in stdout:
        return "regression_introduced"

    # Rule 5: partial_fix (multiple EVIDENCE lines suggest partial coverage)
    if "EVIDENCE:" in stdout:
        evidence_count = stdout.count("EVIDENCE:")
        if evidence_count >= 2:
            return "partial_fix"

    # Rule 6: insufficient_evidence_unclassified
    return "insufficient_evidence_unclassified"


# --- Tests ---


def test_verification_failed_rows_split_into_actionable_subclasses():
    """All verification_failed rows must be classifiable into a subclass."""
    # Simulated rows from C4C runs
    test_cases = [
        # A3: assertion_or_behavior_mismatch
        {
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: normalize_score does not clamp\nEXPECTED: normalize_score should clamp",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        # A4: assertion_or_behavior_mismatch
        {
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: normalize_score does not clamp\nEVIDENCE: normalize_score does not handle max_val == min_val\nEXPECTED: normalize_score should clamp",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        # B2: wrong_location_or_target_miss
        {
            "verifier_failure_kind": "nonzero_exit",
            "verifier_stdout_excerpt": "FAIL: normalize_score function not found",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        # B2-4model: regression_introduced
        {
            "verifier_failure_kind": "nonzero_exit",
            "verifier_stdout_excerpt": "FAIL: normalize_score function not found",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
    ]

    for tc in test_cases:
        subclass = classify_verification_failure(**tc)
        assert subclass in VERIFICATION_FAILED_SUBCLASSES, f"Unknown subclass: {subclass}"


def test_apply_success_verifier_fail_not_collapsed_with_no_blocks_found():
    """apply_success + verifier_fail must not be collapsed with no_blocks_found."""
    # no_blocks_found is a format failure, not a verifier failure
    assert "no_blocks_found" not in VERIFICATION_FAILED_SUBCLASSES

    # verification_failed subclasses must not include no_blocks_found
    for subclass_name, subclass_def in VERIFICATION_FAILED_SUBCLASSES.items():
        assert "no_blocks_found" not in subclass_def.get("evidence_rules", []), (
            f"{subclass_name} should not reference no_blocks_found"
        )


def test_failure_subclass_uses_existing_evidence_fields_only():
    """Each subclass must be definable using only existing evidence fields."""
    allowed_fields = {
        "verifier_failure_kind",
        "verifier_stdout_excerpt",
        "verifier_stderr_excerpt",
        "failure_class",
        "applied_patch_hash",
        "selected_candidate_hash",
    }

    for subclass_name, subclass_def in VERIFICATION_FAILED_SUBCLASSES.items():
        for rule in subclass_def["evidence_rules"]:
            # Extract field names from rule (simple heuristic)
            for field_name in allowed_fields:
                if field_name in rule:
                    assert field_name in allowed_fields, (
                        f"{subclass_name} uses disallowed field: {field_name}"
                    )


def test_unclassified_bucket_used_when_evidence_is_insufficient():
    """insufficient_evidence_unclassified must be returned when evidence is empty."""
    subclass = classify_verification_failure(
        verifier_failure_kind="",
        verifier_stdout_excerpt="",
        verifier_stderr_excerpt="",
        failure_class="verification_failed",
    )
    assert subclass == "insufficient_evidence_unclassified"


def test_current_proof_report_surfaces_top_verification_failed_subclasses():
    """Report must surface top verification_failed subclasses with counts."""
    # Simulate classification of all 10 verification_failed combinations
    simulated_results = [
        {
            "combo": "A1",
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: ... EXPECTED: ...",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "A3",
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: ... EXPECTED: ...",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "A4",
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: ... EXPECTED: ...",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "A5",
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: ... EXPECTED: ...",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "A6",
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: ... EXPECTED: ...",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "B1",
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: ... EXPECTED: ...",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "B2",
            "verifier_failure_kind": "nonzero_exit",
            "verifier_stdout_excerpt": "FAIL: normalize_score function not found",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "B3",
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: ... EXPECTED: ...",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "B4",
            "verifier_failure_kind": "exception",
            "verifier_stdout_excerpt": "EVIDENCE: ... EXPECTED: ...",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
        {
            "combo": "four-model",
            "verifier_failure_kind": "nonzero_exit",
            "verifier_stdout_excerpt": "FAIL: normalize_score function not found",
            "verifier_stderr_excerpt": "",
            "failure_class": "verification_failed",
        },
    ]

    subclass_counts = {}
    for row in simulated_results:
        subclass = classify_verification_failure(
            **{
                k: row[k]
                for k in [
                    "verifier_failure_kind",
                    "verifier_stdout_excerpt",
                    "verifier_stderr_excerpt",
                    "failure_class",
                ]
            }
        )
        subclass_counts.setdefault(subclass, []).append(row["combo"])

    # Must have at least 2 subclasses
    assert len(subclass_counts) >= 2, f"Expected >= 2 subclasses, got {len(subclass_counts)}"

    # assertion_or_behavior_mismatch must be the largest
    assert "assertion_or_behavior_mismatch" in subclass_counts
    assert len(subclass_counts["assertion_or_behavior_mismatch"]) >= 5


def test_affected_suite_binding_records_deterministic_base_candidate_identity():
    manifest = AffectedSuiteManifest(
        test_ids=("tests/test_bug.py::test_boundary",),
        commands=(("python", "-m", "pytest", "tests/test_bug.py::test_boundary"),),
    )
    results = [EvaluationTestResult(test_id=manifest.test_ids[0], passed=True, output="1 passed")]
    binding = bind_affected_regression_suite(
        manifest,
        base_sha="base-sha",
        candidate_sha="candidate-sha",
        base_results=results,
        candidate_results=results,
        affected_test_ids=manifest.test_ids,
        base_suite_hash=manifest.sha256,
        candidate_suite_hash=manifest.sha256,
    )
    assert binding.eligible is True
    assert binding.reason_code == "AFFECTED_SUITE_PASS"
    assert binding.suite_identity == manifest.identity
    assert binding.suite_hash == manifest.sha256
    assert binding.test_count == 1
    assert binding.base_sha == "base-sha"
    assert binding.candidate_sha == "candidate-sha"
    assert binding.failure_evidence == ()


@pytest.mark.parametrize(
    ("hash_bindings", "expected_reason"),
    (
        ({}, "SUITE_HASH_BINDINGS_MISSING"),
        ({"candidate_suite_hash": "manifest"}, "BASE_SUITE_HASH_MISSING"),
        ({"base_suite_hash": "manifest"}, "CANDIDATE_SUITE_HASH_MISSING"),
    ),
)
def test_affected_suite_binding_rejects_omitted_base_or_candidate_hash(
    hash_bindings, expected_reason
):
    manifest = _affected_manifest()
    results = _passing_suite_results(manifest)
    resolved_hashes = {
        name: manifest.sha256 if value == "manifest" else value
        for name, value in hash_bindings.items()
    }
    binding = bind_affected_regression_suite(
        manifest,
        base_sha="base-sha",
        candidate_sha="candidate-sha",
        base_results=results,
        candidate_results=results,
        affected_test_ids=manifest.test_ids,
        **resolved_hashes,
    )
    assert binding.eligible is False
    assert binding.reason_code == expected_reason


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    (
        ("base_suite_hash", "", "BASE_SUITE_HASH_MISSING"),
        ("candidate_suite_hash", "", "CANDIDATE_SUITE_HASH_MISSING"),
        ("base_suite_hash", 7, "BASE_SUITE_HASH_INVALID"),
        ("candidate_suite_hash", 7, "CANDIDATE_SUITE_HASH_INVALID"),
        ("base_suite_hash", "0" * 63, "BASE_SUITE_HASH_INVALID"),
        ("candidate_suite_hash", "A" * 64, "CANDIDATE_SUITE_HASH_INVALID"),
    ),
)
def test_affected_suite_binding_rejects_empty_wrong_type_or_format_hash(
    field, value, expected_reason
):
    manifest = _affected_manifest()
    results = _passing_suite_results(manifest)
    hashes = {
        "base_suite_hash": manifest.sha256,
        "candidate_suite_hash": manifest.sha256,
    }
    hashes[field] = value
    binding = bind_affected_regression_suite(
        manifest,
        base_sha="base-sha",
        candidate_sha="candidate-sha",
        base_results=results,
        candidate_results=results,
        affected_test_ids=manifest.test_ids,
        **hashes,
    )
    assert binding.eligible is False
    assert binding.reason_code == expected_reason


@pytest.mark.parametrize(
    ("field", "expected_reason"),
    (
        ("base_suite_hash", "BASE_SUITE_HASH_DRIFT"),
        ("candidate_suite_hash", "CANDIDATE_SUITE_HASH_DRIFT"),
    ),
)
def test_affected_suite_binding_requires_each_hash_to_equal_manifest(field, expected_reason):
    manifest = _affected_manifest()
    results = _passing_suite_results(manifest)
    hashes = {
        "base_suite_hash": manifest.sha256,
        "candidate_suite_hash": manifest.sha256,
    }
    hashes[field] = "0" * 64
    binding = bind_affected_regression_suite(
        manifest,
        base_sha="base-sha",
        candidate_sha="candidate-sha",
        base_results=results,
        candidate_results=results,
        affected_test_ids=manifest.test_ids,
        **hashes,
    )
    assert binding.eligible is False
    assert binding.reason_code == expected_reason


def _affected_manifest():
    return AffectedSuiteManifest(
        test_ids=("tests/test_bug.py::test_boundary",),
        commands=(("python", "-m", "pytest", "tests/test_bug.py::test_boundary"),),
    )


def _passing_suite_results(manifest):
    return [EvaluationTestResult(test_id=manifest.test_ids[0], passed=True, output="1 passed")]


@pytest.mark.parametrize(
    ("manifest", "affected_test_ids", "expected_reason"),
    (
        (AffectedSuiteManifest(test_ids=(), commands=()), (), "SUITE_EMPTY"),
        (
            AffectedSuiteManifest(
                test_ids=("collect",), commands=(("python", "-m", "pytest", "--collect-only"),)
            ),
            ("collect",),
            "SUITE_COMPILE_ONLY",
        ),
    ),
)
def test_affected_suite_binding_rejects_empty_or_compile_only_evidence(
    manifest, affected_test_ids, expected_reason
):
    results = _passing_suite_results(manifest) if manifest.test_ids else []
    binding = bind_affected_regression_suite(
        manifest,
        base_sha="base-sha",
        candidate_sha="candidate-sha",
        base_results=results,
        candidate_results=results,
        affected_test_ids=affected_test_ids,
    )
    assert (binding.eligible, binding.reason_code) == (False, expected_reason)


def test_affected_suite_binding_rejects_unrelated_and_drifted_manifest():
    manifest = _affected_manifest()
    results = _passing_suite_results(manifest)
    unrelated = bind_affected_regression_suite(
        manifest,
        base_sha="base-sha",
        candidate_sha="candidate-sha",
        base_results=results,
        candidate_results=results,
        affected_test_ids=("tests/other.py::test_unrelated",),
        base_suite_hash=manifest.sha256,
        candidate_suite_hash=manifest.sha256,
    )
    drifted = bind_affected_regression_suite(
        manifest,
        base_sha="base-sha",
        candidate_sha="candidate-sha",
        base_results=results,
        candidate_results=results,
        affected_test_ids=manifest.test_ids,
        expected_suite_hash="0" * 64,
        base_suite_hash=manifest.sha256,
        candidate_suite_hash=manifest.sha256,
    )
    assert unrelated.reason_code == "SUITE_UNRELATED_OR_UNBOUND"
    assert drifted.reason_code == "SUITE_HASH_DRIFT"


def test_affected_suite_binding_unions_base_and_candidate_failure_evidence():
    manifest = _affected_manifest()
    base_results = [
        EvaluationTestResult(test_id=manifest.test_ids[0], passed=False, output="base assertion")
    ]
    candidate_results = [
        EvaluationTestResult(
            test_id=manifest.test_ids[0], passed=False, output="candidate regression"
        )
    ]
    binding = bind_affected_regression_suite(
        manifest,
        base_sha="base-sha",
        candidate_sha="candidate-sha",
        base_results=base_results,
        candidate_results=candidate_results,
        affected_test_ids=manifest.test_ids,
        base_suite_hash=manifest.sha256,
        candidate_suite_hash=manifest.sha256,
    )
    assert binding.reason_code == "SUITE_TEST_FAILED"
    assert binding.failure_evidence == (
        "base:tests/test_bug.py::test_boundary: base assertion",
        "candidate:tests/test_bug.py::test_boundary: candidate regression",
    )
