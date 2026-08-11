from __future__ import annotations

import hashlib
from collections import Counter

import pytest

from nexus.research.epistemic_benchmark.phase1a_qualification import (
    SIX_ARM_PERMUTATIONS,
    Issue29PrerequisiteEvidence,
    Phase1AFrozenManifest,
    Phase1ARunRow,
    QualificationResult,
    QualificationStatus,
    RunClassification,
    RunKind,
    RunValidityEvidence,
    assign_counterbalanced_orders,
    classify_run,
    compare_frozen_manifests,
    evaluate_preformal_readiness,
    select_formal_effect_rows,
)


def _h(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def make_manifest(**overrides) -> Phase1AFrozenManifest:
    values = {
        "phase1a_contract_hash": _h("phase1a-contract"),
        "repository_source_snapshots": {"git_main": "a" * 40, "corpus_sha256": _h("corpus")},
        "qualification_task_ids": ("qual-1", "qual-2"),
        "formal_task_ids": tuple(f"formal-{index:02d}" for index in range(15)),
        "arm_semantics_hash": _h("arm-semantics"),
        "treatment_fingerprint_policy_hash": _h("treatment-policy"),
        "planner_route_policy_hash": _h("planner-route-policy"),
        "online_prompt_policy_hash": _h("online-prompt-policy"),
        "final_verifier_contract_hash": _h("final-verifier"),
        "quality_gate_contract_hash": _h("quality-gate"),
        "deterministic_pipeline_hash": _h("deterministic-pipeline"),
        "evidence_observation_contract_hash": _h("evidence-observation"),
        "provider_safe_projection_contract_hash": _h("provider-safe-projection"),
        "consumption_proof_contract_hash": _h("consumption-proof"),
        "settlement_contract_hash": _h("settlement"),
        "trajectory_schema_hash": _h("trajectory-schema"),
        "action_normalization_rule_hash": _h("action-normalization"),
        "recomputation_formula_hash": _h("recomputation-formula"),
        "invalid_run_taxonomy_hash": _h("invalid-run-taxonomy"),
        "online_provider": "online-provider-v1",
        "online_model": "provider/model-v1",
        "local_provider": "ollama",
        "local_model": "qwen2.5-coder:7b-instruct",
        "accounting_policy_hash": _h("accounting-policy"),
        "pairing_rule_hash": _h("pairing-rule"),
        "execution_order_rule_id": "phase1a-six-permutation-v1",
        "execution_order_seed": 166,
        "meaningful_improvement_thresholds": {"ba_min_avoided_actions": 1.0, "cb_min_avoided_actions": 1.0},
        "report_schema_verifier_hash": _h("report-schema-verifier"),
        "required_issue29_evidence_identity": _h("issue29-evidence"),
        "manifest_version": "phase1a-manifest-v1",
    }
    values.update(overrides)
    return Phase1AFrozenManifest(**values)


def test_manifest_requires_nonempty_disjoint_corpora():
    with pytest.raises(ValueError, match="must be non-empty"):
        make_manifest(qualification_task_ids=())
    with pytest.raises(ValueError, match="must be non-empty"):
        make_manifest(formal_task_ids=())
    with pytest.raises(ValueError, match="must be disjoint"):
        make_manifest(qualification_task_ids=("shared",), formal_task_ids=("shared", "formal-1"))


def test_manifest_mapping_order_is_deterministic():
    first = make_manifest(
        repository_source_snapshots={"git_main": "a" * 40, "corpus_sha256": _h("corpus")},
        meaningful_improvement_thresholds={"ba_min_avoided_actions": 1, "cb_min_avoided_actions": 2},
    )
    second = make_manifest(
        repository_source_snapshots={"corpus_sha256": _h("corpus"), "git_main": "a" * 40},
        meaningful_improvement_thresholds={"cb_min_avoided_actions": 2, "ba_min_avoided_actions": 1},
    )
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.to_dict() == second.to_dict()


def test_manifest_identity_is_frozen_against_caller_mutation():
    snapshots = {"git_main": "a" * 40, "corpus_sha256": _h("corpus")}
    thresholds = {"ba_min_avoided_actions": 1.0}
    manifest = make_manifest(repository_source_snapshots=snapshots, meaningful_improvement_thresholds=thresholds)
    before = manifest.to_dict()
    before_hash = manifest.manifest_sha256
    snapshots["git_main"] = "b" * 40
    thresholds["ba_min_avoided_actions"] = 999.0
    assert manifest.manifest_sha256 == before_hash
    assert manifest.to_dict() == before


def test_manifest_rejects_unordered_or_wrong_type_decision_inputs():
    with pytest.raises(ValueError):
        make_manifest(repository_source_snapshots={"bad": {"a", "b"}})
    with pytest.raises(ValueError):
        make_manifest(meaningful_improvement_thresholds={"metric": {1, 2}})


def test_thresholds_are_explicit_and_not_legacy_vap_defaults():
    with pytest.raises(ValueError, match="explicit and non-empty"):
        make_manifest(meaningful_improvement_thresholds={})
    with pytest.raises(ValueError, match="legacy VAP threshold"):
        make_manifest(meaningful_improvement_thresholds={"vap_online_token_ratio": 0.85})
    explicit = make_manifest(meaningful_improvement_thresholds={"phase1a_min_work_reduction": 0.85})
    assert explicit.meaningful_improvement_thresholds["phase1a_min_work_reduction"] == 0.85


def test_exact_provider_model_identities_required():
    for field in ("online_provider", "online_model", "local_provider", "local_model"):
        with pytest.raises(ValueError, match="exact bound identity"):
            make_manifest(**{field: "latest"})
    with pytest.raises(ValueError, match="exact machine identity"):
        make_manifest(online_model="Gemini 3.6 Flash (Medium)")


def test_hash_identities_fail_closed():
    with pytest.raises(ValueError, match="phase1a_contract_hash"):
        make_manifest(phase1a_contract_hash="")
    with pytest.raises(ValueError, match="report_schema_verifier_hash"):
        make_manifest(report_schema_verifier_hash="not-a-hash")


def test_post_freeze_drift_requires_new_manifest_version():
    original = make_manifest()
    changed = make_manifest(meaningful_improvement_thresholds={"ba_min_avoided_actions": 2.0, "cb_min_avoided_actions": 1.0})
    result = compare_frozen_manifests(original, changed)
    assert result.compatible_same_cohort is False
    assert result.reason == "NEW_MANIFEST_VERSION_REQUIRED"
    assert original.manifest_sha256 != changed.manifest_sha256
    same = compare_frozen_manifests(original, make_manifest())
    assert same.compatible_same_cohort is True


def test_counterbalanced_assignment_is_deterministic_and_balanced():
    tasks = tuple(f"task-{index:02d}" for index in range(15))
    first = assign_counterbalanced_orders(tasks, seed=42)
    second = assign_counterbalanced_orders(tuple(reversed(tasks)), seed=42)
    assert {item.task_id: item.permutation for item in first} == {item.task_id: item.permutation for item in second}
    counts = Counter(item.permutation for item in first)
    all_counts = [counts[permutation] for permutation in SIX_ARM_PERMUTATIONS]
    assert max(all_counts) - min(all_counts) <= 1


def test_counterbalanced_assignment_is_seed_deterministic():
    tasks = tuple(f"task-{index:02d}" for index in range(12))
    first = {item.task_id: item.permutation for item in assign_counterbalanced_orders(tasks, 1)}
    repeat = {item.task_id: item.permutation for item in assign_counterbalanced_orders(tasks, 1)}
    second_seed = {item.task_id: item.permutation for item in assign_counterbalanced_orders(tasks, 2)}
    assert first == repeat
    assert first != second_seed


def test_run_classifier_separates_semantic_failure_from_invalidity():
    assert classify_run(RunValidityEvidence(semantic_success=True)) == RunClassification.VALID_SUCCESS
    assert classify_run(RunValidityEvidence(semantic_success=False)) == RunClassification.VALID_FAILURE
    assert classify_run(RunValidityEvidence(semantic_success=False, provider_runtime_ok=False)) == RunClassification.INFRA_INVALID
    assert classify_run(RunValidityEvidence(semantic_success=False, fixture_ok=False)) == RunClassification.INFRA_INVALID
    assert classify_run(RunValidityEvidence(semantic_success=False, required_telemetry_complete=False)) == RunClassification.INFRA_INVALID
    assert classify_run(RunValidityEvidence(semantic_success=False, treatment_identity_ok=False)) == RunClassification.TREATMENT_INVALID
    assert classify_run(RunValidityEvidence(semantic_success=False, complete_triplet=False)) == RunClassification.TREATMENT_INVALID
    assert classify_run(RunValidityEvidence(semantic_success=False, forbidden_local_call_in_b=True)) == RunClassification.TREATMENT_INVALID
    assert classify_run(RunValidityEvidence(semantic_success=False, source_integrity_ok=False)) == RunClassification.INTEGRITY_INVALID


def test_formal_effect_rows_exclude_qualification_and_invalid_runs():
    manifest = make_manifest(qualification_task_ids=("qual-1",), formal_task_ids=("formal-1", "formal-2", "formal-3"))
    rows = (
        Phase1ARunRow("qual-1", RunKind.QUALIFICATION, RunClassification.VALID_SUCCESS, {"noise": 0.1}),
        Phase1ARunRow("formal-1", RunKind.FORMAL, RunClassification.VALID_FAILURE, {"quality": 0}),
        Phase1ARunRow("formal-2", RunKind.FORMAL, RunClassification.INFRA_INVALID, {"quality": 0}),
    )
    selected = select_formal_effect_rows(manifest, rows)
    assert [row.task_id for row in selected] == ["formal-1"]
    mislabeled = Phase1ARunRow("qual-1", RunKind.FORMAL, RunClassification.VALID_FAILURE, {})
    with pytest.raises(ValueError, match="outside formal corpus"):
        select_formal_effect_rows(manifest, (mislabeled,))


def test_qualification_projection_cannot_be_formal_effect_decision():
    result = QualificationResult(
        status=QualificationStatus.READY,
        qualification_task_ids=("qual-1", "qual-2"),
        readiness_evidence_refs=("noise-estimate", "harness-checks"),
        measurement_noise_summary={"wall_time_cv": 0.03},
    )
    assert result.formal_effect_allowed is False
    assert not hasattr(result, "causal_benefit")
    assert not hasattr(result, "treatment_winner")


def test_preformal_readiness_requires_exact_external_issue29_evidence():
    manifest = make_manifest()
    missing = evaluate_preformal_readiness(manifest, issue29_evidence=None, current_report_schema_verifier_hash=manifest.report_schema_verifier_hash)
    assert missing.preformal_ready is False
    assert "ISSUE29_EVIDENCE_MISSING" in missing.reasons
    assert missing.g5_authorized is False
    with pytest.raises(ValueError, match="identity-bound evidence"):
        evaluate_preformal_readiness(manifest, issue29_evidence=True, current_report_schema_verifier_hash=manifest.report_schema_verifier_hash)
    mismatch = Issue29PrerequisiteEvidence(
        evidence_identity=_h("wrong-issue29"),
        acceptance_receipt_sha256=_h("acceptance"),
        verified_source_revision="commit-29",
        independently_accepted=True,
    )
    mismatch_result = evaluate_preformal_readiness(manifest, issue29_evidence=mismatch, current_report_schema_verifier_hash=manifest.report_schema_verifier_hash)
    assert mismatch_result.preformal_ready is False
    assert "ISSUE29_EVIDENCE_IDENTITY_MISMATCH" in mismatch_result.reasons


def test_matching_preformal_prerequisites_still_do_not_authorize_g5():
    manifest = make_manifest()
    issue29 = Issue29PrerequisiteEvidence(
        evidence_identity=manifest.required_issue29_evidence_identity,
        acceptance_receipt_sha256=_h("issue29-acceptance"),
        verified_source_revision="commit-29-accepted",
        independently_accepted=True,
    )
    ready = evaluate_preformal_readiness(manifest, issue29_evidence=issue29, current_report_schema_verifier_hash=manifest.report_schema_verifier_hash)
    assert ready.preformal_ready is True
    assert ready.reasons == ("PREFORMAL_PREREQUISITES_SATISFIED",)
    assert ready.g5_authorized is False


def test_report_verifier_identity_must_match_manifest():
    manifest = make_manifest()
    issue29 = Issue29PrerequisiteEvidence(
        evidence_identity=manifest.required_issue29_evidence_identity,
        acceptance_receipt_sha256=_h("issue29-acceptance"),
        verified_source_revision="commit-29-accepted",
        independently_accepted=True,
    )
    result = evaluate_preformal_readiness(manifest, issue29_evidence=issue29, current_report_schema_verifier_hash=_h("different-report-verifier"))
    assert result.preformal_ready is False
    assert "REPORT_SCHEMA_VERIFIER_IDENTITY_MISMATCH" in result.reasons
    assert result.g5_authorized is False
