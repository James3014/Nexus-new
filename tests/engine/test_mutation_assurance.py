from nexus.engine.mutation_assurance import (
    build_shadow_mutation_report,
    build_mutation_assurance_record,
    deterministic_mutants_for_concern,
    evaluate_mutation_assurance,
    mutation_assurance_required,
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
