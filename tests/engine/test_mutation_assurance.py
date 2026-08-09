from itertools import repeat

from nexus.engine.mutation_assurance import (
    build_mutation_assurance_record,
    build_shadow_mutation_report,
    deterministic_mutants_for_concern,
    evaluate_issue16_mutation_assurance,
    evaluate_mutation_assurance,
    mutation_assurance_required,
)


def _issue16_target_record(*, mutant_failed: bool = True, equivalent_suspected: bool = False):
    mutant = deterministic_mutants_for_concern("public_claim_safety")[0]
    return build_mutation_assurance_record(
        concern=mutant["concern"],
        mutant_id=mutant["mutant_id"],
        mutant_diff=mutant["mutant_diff"],
        original_passed=True,
        mutant_failed=mutant_failed,
        equivalent_suspected=equivalent_suspected,
        evidence_refs=("pytest:test_public_claim_gate",),
    )


def test_deterministic_mutant_library_contains_public_claim_safety_cases():
    mutants = {item["mutant_id"]: item for item in deterministic_mutants_for_concern()}

    assert "claim_always_true" in mutants
    assert "delivery_ignores_evidence" in mutants
    assert "policy_deny_to_allow" in mutants
    assert "public_safe_forced_true" in mutants
    assert mutants["public_safe_forced_true"]["expected_detector"] == "capability_receipt_policy"


def test_mutation_assurance_record_marks_killed_mutant():
    record = build_mutation_assurance_record(
        concern="claim_integrity",
        mutant_id="claim_always_true",
        original_passed=True,
        mutant_failed=True,
        mutant_diff="- claim=evidence\n+ claim=True",
        evidence_refs=("pytest:test_claim_gate",),
    )

    assert record["killed"] is True
    assert record["assurance_status"] == "KILLED"


def test_mutation_assurance_gate_blocks_survived_blind_spot():
    record = build_mutation_assurance_record(
        concern="claim_integrity",
        mutant_id="claim_always_true",
        original_passed=True,
        mutant_failed=False,
    )

    gate = evaluate_mutation_assurance([record], required=True)

    assert gate["passed"] is False
    assert gate["failures"] == ["no_mutant_killed", "survived_mutants_present"]
    assert gate["survived_mutant_ids"] == ["claim_always_true"]


def test_mutation_assurance_gate_requires_high_risk_public_claim_only():
    assert mutation_assurance_required(risk_score=80, public_claim=True) is True
    assert mutation_assurance_required(risk_score=20, public_claim=True) is False
    assert mutation_assurance_required(risk_score=95, public_claim=False) is False


def test_shadow_mutation_report_surfaces_blindspots_without_blocking_release():
    record = build_mutation_assurance_record(
        concern="claim_integrity",
        mutant_id="claim_always_true",
        original_passed=True,
        mutant_failed=False,
    )

    report = build_shadow_mutation_report([record], concern="claim_integrity")

    assert report["schema_version"] == "nexus_shadow_mutation_report.v1"
    assert report["survived_count"] == 1
    assert report["release_blocked"] is False
    assert report["recommended_action"] == "promote_targeted_tests"


def test_issue16_risk_trigger_selects_targeted_challenge_and_requires_its_record():
    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80, "public_claim": True},
        records=[],
    )

    assert decision["decision"] == "REQUIRED"
    assert decision["reason"] == "public_claim_or_high_risk"
    assert decision["targeted_mutant_ids"] == ["public_safe_forced_true"]
    assert decision["status"] == "FAIL"
    assert decision["failures"] == ["mutation_assurance_missing"]


def test_issue16_risk_trigger_passes_only_when_targeted_mutant_is_killed():
    record = _issue16_target_record()

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"high_risk": True},
        records=[record],
    )

    assert decision["status"] == "PASS"
    assert decision["passed"] is True
    assert decision["killed_count"] == 1
    assert decision["survived_count"] == 0
    assert decision["equivalent_suspected_count"] == 0
    assert decision["targeted_records"] == [record]


def test_issue16_risk_trigger_ignores_unrelated_records_and_fails_closed():
    record = build_mutation_assurance_record(
        concern="claim_integrity",
        mutant_id="claim_always_true",
        original_passed=True,
        mutant_failed=True,
    )

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 70},
        records=[record],
    )

    assert decision["status"] == "FAIL"
    assert decision["failures"] == ["mutation_assurance_missing"]
    assert decision["row_count"] == 0


def test_issue16_low_risk_is_explicitly_not_required_not_mutation_pass():
    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 20, "public_claim": False},
        records=[],
    )

    assert decision["decision"] == "NOT_REQUIRED"
    assert decision["reason"] == "low_risk_internal_change"
    assert decision["status"] == "NOT_REQUIRED"
    assert decision["passed"] is False
    assert decision["failures"] == []


def test_issue16_rejects_malformed_killed_only_target_record():
    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80, "public_claim": True},
        records=[
            {
                "concern": "public_claim_safety",
                "mutant_id": "public_safe_forced_true",
                "killed": True,
            }
        ],
    )

    assert decision["status"] == "FAIL"
    assert decision["passed"] is False
    assert decision["row_count"] == 0
    assert decision["killed_count"] == 0
    assert decision["failures"] == [
        "mutation_assurance_missing",
        "mutation_record_schema_invalid",
    ]


def test_issue16_rejects_non_iterable_record_collection_without_exception():
    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80, "public_claim": True},
        records=7,
    )

    assert decision["status"] == "FAIL"
    assert decision["passed"] is False
    assert decision["row_count"] == 0
    assert decision["failures"] == [
        "mutation_assurance_missing",
        "records_invalid_type",
    ]


def test_issue16_duplicate_target_identity_fails_without_double_counting():
    record = _issue16_target_record()

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80, "public_claim": True},
        records=[record, dict(record)],
    )

    assert decision["status"] == "FAIL"
    assert decision["passed"] is False
    assert decision["targeted_records"] == []
    assert decision["row_count"] == 0
    assert decision["killed_count"] == 0
    assert decision["failures"] == [
        "duplicate_target_identity",
        "mutation_assurance_missing",
    ]


def test_issue16_rejects_wrong_boolean_type_and_inconsistent_status_semantics():
    wrong_boolean = _issue16_target_record()
    wrong_boolean["killed"] = 1
    inconsistent_status = _issue16_target_record(mutant_failed=False)
    inconsistent_status["assurance_status"] = "KILLED"

    wrong_type_decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80, "public_claim": True},
        records=[wrong_boolean],
    )
    inconsistent_decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80, "public_claim": True},
        records=[inconsistent_status],
    )

    assert wrong_type_decision["killed_count"] == 0
    assert wrong_type_decision["failures"] == [
        "mutation_assurance_missing",
        "mutation_record_schema_invalid",
    ]
    assert inconsistent_decision["survived_count"] == 0
    assert inconsistent_decision["failures"] == [
        "mutation_assurance_missing",
        "mutation_record_semantics_invalid",
    ]


def test_issue16_invalid_or_implicit_risk_inputs_fail_closed_not_not_required():
    malformed = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": "20", "public_claim": False},
        records=[],
    )
    implicit = evaluate_issue16_mutation_assurance(risk_inputs={}, records=[])

    for decision in (malformed, implicit):
        assert decision["decision"] == "REQUIRED"
        assert decision["reason"] == "invalid_risk_inputs"
        assert decision["status"] == "FAIL"
        assert decision["passed"] is False
        assert decision["failures"] == [
            "mutation_assurance_missing",
            "risk_inputs_invalid",
        ]


def test_issue16_valid_survived_and_equivalent_statuses_have_consistent_counts():
    survived = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=[_issue16_target_record(mutant_failed=False)],
    )
    equivalent = evaluate_issue16_mutation_assurance(
        risk_inputs={"high_risk": True},
        records=[_issue16_target_record(equivalent_suspected=True)],
    )

    assert survived["killed_count"] == 0
    assert survived["survived_count"] == 1
    assert survived["equivalent_suspected_count"] == 0
    assert survived["failures"] == ["no_mutant_killed", "survived_mutants_present"]
    assert equivalent["killed_count"] == 0
    assert equivalent["survived_count"] == 0
    assert equivalent["equivalent_suspected_count"] == 1
    assert equivalent["failures"] == ["no_mutant_killed"]


def test_issue16_target_records_and_reasons_are_canonical_under_input_shuffle():
    valid = _issue16_target_record()
    malformed_identity = {
        **valid,
        "mutant_id": "not_the_canonical_target",
        "killed": False,
    }
    risk_inputs = {"risk_score": 80, "public_claim": True}

    forward = evaluate_issue16_mutation_assurance(
        risk_inputs=risk_inputs,
        records=[valid, malformed_identity],
    )
    reversed_order = evaluate_issue16_mutation_assurance(
        risk_inputs=risk_inputs,
        records=[malformed_identity, valid],
    )

    assert forward == reversed_order
    assert forward["targeted_records"] == [valid]
    assert forward["killed_count"] == 1
    assert forward["status"] == "FAIL"
    assert forward["failures"] == ["mutation_record_schema_invalid"]


def test_issue16_accepts_finite_mapping_iterable_and_bounds_non_finite_input():
    record = _issue16_target_record()
    finite = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=(item for item in [record]),
    )
    non_finite = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=repeat(record),
    )

    assert finite["status"] == "PASS"
    assert finite["killed_count"] == 1
    assert non_finite["status"] == "FAIL"
    assert non_finite["row_count"] == 0
    assert non_finite["failures"] == [
        "mutation_assurance_missing",
        "records_not_finite_or_too_large",
    ]


def test_issue16_rejects_non_mapping_record_member():
    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=[7],
    )

    assert decision["status"] == "FAIL"
    assert decision["failures"] == [
        "mutation_assurance_missing",
        "mutation_record_invalid_type",
    ]


def test_issue16_rejects_empty_evidence_refs_with_typed_failure():
    record = _issue16_target_record()
    record["evidence_refs"] = []

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=[record],
    )

    assert decision["status"] == "FAIL"
    assert decision["passed"] is False
    assert decision["targeted_records"] == []
    assert decision["killed_count"] == 0
    assert decision["failures"] == [
        "evidence_refs_empty",
        "mutation_assurance_missing",
    ]


def test_issue16_rejects_missing_evidence_refs_with_typed_failure():
    record = _issue16_target_record()
    del record["evidence_refs"]

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=[record],
    )

    assert decision["failures"] == [
        "evidence_refs_missing",
        "mutation_assurance_missing",
    ]


def test_issue16_rejects_wrong_evidence_refs_collection_type():
    record = _issue16_target_record()
    record["evidence_refs"] = "pytest:test_public_claim_gate"

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=[record],
    )

    assert decision["failures"] == [
        "evidence_refs_invalid_type",
        "mutation_assurance_missing",
    ]


def test_issue16_accepts_non_empty_canonical_evidence_refs_tuple():
    record = _issue16_target_record()
    record["evidence_refs"] = tuple(record["evidence_refs"])

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=[record],
    )

    assert decision["status"] == "PASS"
    assert decision["targeted_records"] == [record]
    assert decision["killed_count"] == 1


def test_issue16_rejects_blank_evidence_ref_with_typed_failure():
    record = _issue16_target_record()
    record["evidence_refs"] = ["pytest:test_public_claim_gate", "   "]

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=[record],
    )

    assert decision["failures"] == [
        "evidence_ref_blank",
        "mutation_assurance_missing",
    ]


def test_issue16_rejects_duplicate_evidence_refs_with_typed_failure():
    record = _issue16_target_record()
    record["evidence_refs"] = [
        "pytest:test_public_claim_gate",
        "pytest:test_public_claim_gate",
    ]

    decision = evaluate_issue16_mutation_assurance(
        risk_inputs={"risk_score": 80},
        records=[record],
    )

    assert decision["failures"] == [
        "evidence_ref_duplicate",
        "mutation_assurance_missing",
    ]


def test_issue16_rejects_noncanonical_or_malformed_evidence_ref_strings():
    malformed_values = (
        [7],
        [" pytest:test_public_claim_gate"],
        ["pytest:test_public_claim_gate\nforged"],
    )

    for evidence_refs in malformed_values:
        record = _issue16_target_record()
        record["evidence_refs"] = evidence_refs
        decision = evaluate_issue16_mutation_assurance(
            risk_inputs={"risk_score": 80},
            records=[record],
        )

        assert decision["status"] == "FAIL"
        assert decision["failures"] == [
            "evidence_ref_malformed",
            "mutation_assurance_missing",
        ]
