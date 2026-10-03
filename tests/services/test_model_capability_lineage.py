from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from nexus.contracts.workforce_admission import (
    AdmissionDecision,
    WorkforceAdmissionRequest,
)
from nexus.services.model_capability_lineage import (
    ADMISSION_AUTHORITY_SEPARATE,
    CalibrationPlanner,
    ChangeClass,
    EvidencePhase,
    ExecutionConfigQualification,
    ExecutionConfiguration,
    LineageResolutionError,
    LineageValidationError,
    ModelCapabilityLineageRegistry,
    QualificationDisposition,
    TrialKind,
    classify_change,
    tiers_strictly_below,
)
from nexus.services.model_workforce_policy import WorkforcePolicyLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
LINEAGE_PATH = REPO_ROOT / "nexus/config/model_capability_lineage.yaml"


def _registry() -> ModelCapabilityLineageRegistry:
    registry = ModelCapabilityLineageRegistry(LINEAGE_PATH)
    registry.load()
    return registry


def _planner() -> CalibrationPlanner:
    return CalibrationPlanner(_registry())


def _minimal_lineage_yaml(*, admission_authority: bool = False) -> dict:
    return {
        "schema": "nexus.model_capability_lineage.v1",
        "status": "current",
        "owner": "test",
        "admission_authority": admission_authority,
        "route_authority": "none",
        "lineages": {
            "lineage-a": {
                "lineage_id": "lineage-a",
                "canonical_family": "family-a",
                "execution_identities": [
                    {"provider": "p", "model": "m-a", "identity_kind": "primary"}
                ],
                "stable_floor": "L2",
                "current_frontier": "L3",
                "conditional_ceiling": "L3",
                "experimental_ceiling": "L4",
            }
        },
    }


def test_registry_loads_seeded_lineages() -> None:
    registry = _registry()
    lineages = registry.lineages()
    assert set(lineages) == {
        "deepseek-v4-flash",
        "gemini-3.7-flash-medium",
        "occamy-1.0",
        "qwen-3.8-27b",
    }


def test_deepseek_lineage_seed_shape() -> None:
    lineage = _registry().resolve_by_lineage_id("deepseek-v4-flash")
    identities = {(i.provider, i.model, i.identity_kind) for i in lineage.execution_identities}
    assert identities == {
        ("opencode", "opencode/deepseek-v4-flash-free", "primary"),
        ("opencode", "opencode-go/deepseek-v4-flash", "alias"),
    }
    assert lineage.stable_floor == "L2"
    assert lineage.current_frontier == "L3"
    assert lineage.conditional_ceiling == "L3"
    assert lineage.experimental_ceiling == "L4"
    assert lineage.frontier_experimental is False
    phases = {record.phase for record in lineage.evidence}
    assert EvidencePhase.FIRST_PASS in phases
    assert EvidencePhase.VERIFIER_GUIDED_REPAIR in phases
    assert lineage.known_failure_families


def test_gemini_lineage_seed_shape() -> None:
    lineage = _registry().resolve_by_lineage_id("gemini-3.7-flash-medium")
    identities = {(i.provider, i.model) for i in lineage.execution_identities}
    assert identities == {("agy", "gemini-3.7-flash-medium")}
    assert lineage.stable_floor == "L3"
    assert lineage.current_frontier == "L4"
    assert lineage.frontier_experimental is True
    assert lineage.conditional_ceiling == "L3"
    assert lineage.experimental_ceiling == "L4"
    assert any("non-admitted" in note for note in lineage.experimental_notes)


def test_resolve_by_execution_identity_for_both_deepseek_aliases() -> None:
    registry = _registry()
    assert (
        registry.resolve_by_execution_identity("opencode", "opencode/deepseek-v4-flash-free")
        is not None
    )
    assert (
        registry.resolve_by_execution_identity("opencode", "opencode-go/deepseek-v4-flash")
        is not None
    )
    assert (
        registry.resolve(provider="opencode", model="opencode-go/deepseek-v4-flash").lineage_id
        == "deepseek-v4-flash"
    )
    assert registry.resolve(lineage_id="deepseek-v4-flash").canonical_family == "deepseek-v4-flash"


def test_resolve_unknown_fails_closed() -> None:
    registry = _registry()
    assert registry.resolve_by_execution_identity("opencode", "opencode/unknown-model") is None
    with pytest.raises(LineageResolutionError, match="Unknown lineage_id"):
        registry.resolve_by_lineage_id("does-not-exist")
    with pytest.raises(LineageResolutionError, match="No registered lineage"):
        registry.resolve(provider="opencode", model="opencode/unknown-model")
    with pytest.raises(LineageResolutionError, match="requires lineage_id OR both"):
        registry.resolve()


def test_unknown_alias_does_not_inherit_lineage_by_fuzzy_name_match() -> None:
    registry = _registry()
    assert registry.resolve_by_execution_identity("opencode", "opencode/deepseek-v4-flash") is None
    assert (
        registry.resolve_by_execution_identity("opencode", "opencode-go/deepseek-v4-flash-free")
        is None
    )
    assert registry.resolve_by_execution_identity("opencode", "deepseek-v4-flash") is None
    assert (
        registry.resolve_by_execution_identity("opencode", "opencode/DeepSeek-V4-Flash-Free")
        is None
    )


def test_same_marketing_text_is_insufficient_without_registry_binding() -> None:
    planner = _planner()
    with pytest.raises(LineageResolutionError, match="No registered lineage"):
        planner.evidence_bundle(provider="opencode", model="opencode/deepseek-v4-flash")
    with pytest.raises(LineageResolutionError, match="No registered lineage"):
        planner.evidence_bundle(
            provider="opencode", model="opencode-go/deepseek-v4-flash-pro"
        )  # same family, unbound


def test_registry_fails_closed_when_file_missing(tmp_path: Path) -> None:
    with pytest.raises(LineageValidationError, match="Lineage registry file not found"):
        ModelCapabilityLineageRegistry(tmp_path / "missing.yaml").load()


def test_registry_fails_closed_on_invalid_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.dump({"schema": "other.v1", "lineages": {}}), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="Invalid schema"):
        ModelCapabilityLineageRegistry(bad).load()


def test_registry_rejects_admission_authority_true(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.dump(_minimal_lineage_yaml(admission_authority=True)), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="admission_authority"):
        ModelCapabilityLineageRegistry(bad).load()


def test_registry_rejects_duplicate_execution_identity(tmp_path: Path) -> None:
    data = _minimal_lineage_yaml()
    data["lineages"]["lineage-b"] = {
        "lineage_id": "lineage-b",
        "canonical_family": "family-b",
        "execution_identities": [{"provider": "p", "model": "m-a", "identity_kind": "primary"}],
        "stable_floor": "L1",
        "current_frontier": "L2",
        "conditional_ceiling": "L2",
        "experimental_ceiling": "L3",
    }
    bad = tmp_path / "dup.yaml"
    bad.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="Duplicate execution identity"):
        ModelCapabilityLineageRegistry(bad).load()


def test_registry_rejects_unknown_tier(tmp_path: Path) -> None:
    data = _minimal_lineage_yaml()
    data["lineages"]["lineage-a"]["stable_floor"] = "L9"
    bad = tmp_path / "bad-tier.yaml"
    bad.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="invalid tier"):
        ModelCapabilityLineageRegistry(bad).load()


def test_classify_change_classes() -> None:
    cases = [
        ({"new_lineage": True}, False, ChangeClass.NEW_LINEAGE),
        ({"alias_only": True}, True, ChangeClass.ALIAS_ONLY),
        ({}, True, ChangeClass.ALIAS_ONLY),
        ({"transport_change": True}, False, ChangeClass.TRANSPORT_ONLY),
        ({"cli_or_adapter_change": True}, False, ChangeClass.CLI_OR_ADAPTER_CHANGE),
        ({"prompt_template_change": True}, False, ChangeClass.PROMPT_TEMPLATE_OR_THINKING_CHANGE),
        ({"thinking_change": True}, False, ChangeClass.PROMPT_TEMPLATE_OR_THINKING_CHANGE),
        ({"model_revision_change": True}, False, ChangeClass.MODEL_REVISION_OR_BACKEND_CHANGE),
        ({"backend_change": True}, False, ChangeClass.MODEL_REVISION_OR_BACKEND_CHANGE),
        ({}, False, ChangeClass.UNKNOWN_MATERIAL_CHANGE),
        (
            {"description": "changed something unclassified"},
            False,
            ChangeClass.UNKNOWN_MATERIAL_CHANGE,
        ),
    ]
    from nexus.services.model_capability_lineage import ChangeDeclaration

    for kwargs, as_alias, expected in cases:
        assert (
            classify_change(ChangeDeclaration(**kwargs), registered_as_alias=as_alias) is expected
        )


def test_deepseek_alias_requalification_does_not_restart_from_l1() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode-go/deepseek-v4-flash",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    assert plan.change_class is ChangeClass.ALIAS_ONLY
    assert plan.stable_floor == "L2"
    assert plan.current_frontier == "L3"
    kinds = [trial.kind for trial in plan.required_trials]
    assert TrialKind.STABLE_FLOOR_REGRESSION in kinds
    floor_regression = next(
        t for t in plan.required_trials if t.kind is TrialKind.STABLE_FLOOR_REGRESSION
    )
    assert floor_regression.tier == "L2"
    frontier = next(t for t in plan.required_trials if t.kind is TrialKind.FRONTIER_EVALUATION)
    assert frontier.tier == "L3"
    assert TrialKind.IDENTITY_RESOLUTION in kinds
    assert TrialKind.TRANSPORT_PREFLIGHT in kinds
    not_required_tiers = [trial.tier for trial in plan.not_required_trials]
    assert "L0" in not_required_tiers and "L0.25" in not_required_tiers
    assert "L0.5" in not_required_tiers and "L1" in not_required_tiers
    assert not any(trial.tier in {"L0", "L0.25", "L0.5", "L1"} for trial in plan.required_trials)


def test_alias_requalification_retains_semantic_evidence_and_revalidates_transport() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode-go/deepseek-v4-flash",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    assert plan.reusable_evidence, "L2 semantic capability evidence must remain reusable"
    assert all(entry["scope"] == "SEMANTIC" for entry in plan.reusable_evidence)
    assert plan.invalidated_evidence == ()


def test_reusable_evidence_preserves_provenance_from_lineage_evidence() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode-go/deepseek-v4-flash",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    by_ref = {entry["ref"]: entry for entry in plan.reusable_evidence}
    l2_ref = "lineage:deepseek-v4-flash/evidence:ds-v4-flash-l2-stable-floor"
    l4_first_pass_ref = "lineage:deepseek-v4-flash/evidence:ds-v4-flash-l4-first-pass"
    l4_repair_ref = "lineage:deepseek-v4-flash/evidence:ds-v4-flash-l4-verifier-guided-repair"
    assert l2_ref in by_ref
    assert l4_first_pass_ref in by_ref
    assert l4_repair_ref in by_ref
    assert by_ref[l2_ref]["provenance"] == "OWNER_DECISION"
    assert (
        by_ref[l4_first_pass_ref]["provenance"]
        == "EXTERNAL_CALIBRATION_RECEIPT_PENDING_DURABLE_WRITEBACK"
    )
    assert (
        by_ref[l4_repair_ref]["provenance"]
        == "EXTERNAL_CALIBRATION_RECEIPT_PENDING_DURABLE_WRITEBACK"
    )
    lineage_evidence_ids = {
        record.id for record in _registry().resolve_by_lineage_id("deepseek-v4-flash").evidence
    }
    for entry in plan.reusable_evidence:
        if (
            entry["ref"].startswith("lineage:")
            and entry["ref"].rsplit(":", 1)[-1] in lineage_evidence_ids
        ):
            assert entry["provenance"] not in (None, "")


def test_core_invariant_floor_l2_target_l3_no_lower_suite() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode/deepseek-v4-flash-free",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    required_tiers = [trial.tier for trial in plan.required_trials]
    assert not set(tiers_strictly_below(plan.stable_floor)).intersection(required_tiers)
    not_required = [trial.tier for trial in plan.not_required_trials]
    assert set(not_required) == {"L0", "L0.25", "L0.5", "L1"}


def test_new_lineage_requires_full_baseline_path() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode/brand-new-model",
        target_role="compact_code_candidate",
        change_kind="new_lineage",
    )
    assert plan.change_class is ChangeClass.NEW_LINEAGE
    assert plan.plan_status == "PLANNED_FULL_BASELINE"
    assert {trial.kind for trial in plan.required_trials} == {TrialKind.FULL_BASELINE}
    assert {trial.tier for trial in plan.required_trials} == {
        "L0",
        "L0.25",
        "L0.5",
        "L1",
        "L2",
        "L3",
    }


def test_unregistered_model_plan_fails_closed_without_new_lineage_declaration() -> None:
    with pytest.raises(LineageResolutionError, match="only an explicit new_lineage request"):
        _planner().build_calibration_plan(
            provider="opencode",
            model="opencode/brand-new-model",
            target_role="compact_code_candidate",
            change_kind="alias_only",
        )


def test_unknown_material_change_fails_closed_and_requests_broader_requalification() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode/deepseek-v4-flash-free",
        target_role="compact_code_candidate",
        change_kind="unknown_material_change",
    )
    assert plan.change_class is ChangeClass.UNKNOWN_MATERIAL_CHANGE
    assert plan.plan_status == "FAIL_CLOSED"
    assert plan.required_trials == ()
    assert any("broader requalification" in reason for reason in plan.reasons)
    assert plan.invalidated_evidence


def test_model_revision_change_invalidates_semantic_evidence() -> None:
    plan = _planner().build_calibration_plan(
        provider="agy",
        model="gemini-3.7-flash-medium",
        target_role="focused_verification",
        change_kind="model_revision_or_backend_change",
    )
    assert plan.change_class is ChangeClass.MODEL_REVISION_OR_BACKEND_CHANGE
    assert plan.invalidated_evidence
    assert all(entry["scope"] == "SEMANTIC" for entry in plan.invalidated_evidence)
    assert not any(entry["scope"] == "SEMANTIC" for entry in plan.reusable_evidence)
    assert any("explicitly invalidated" in reason for reason in plan.reasons)
    assert any("family-name equivalence" in reason for reason in plan.reasons)


def test_prompt_or_thinking_change_reruns_around_floor_frontier_only() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode/deepseek-v4-flash-free",
        target_role="compact_code_candidate",
        change_kind="prompt_template_or_thinking_change",
    )
    assert plan.change_class is ChangeClass.PROMPT_TEMPLATE_OR_THINKING_CHANGE
    assert plan.invalidated_evidence
    assert not any(trial.tier in {"L0", "L0.25", "L0.5", "L1"} for trial in plan.required_trials)
    assert {trial.tier for trial in plan.required_trials} <= {"L2", "L3"}


def test_evidence_phases_never_collapse() -> None:
    lineage = _registry().resolve_by_lineage_id("deepseek-v4-flash")
    first_pass = [record for record in lineage.evidence if record.phase is EvidencePhase.FIRST_PASS]
    repair = [
        record
        for record in lineage.evidence
        if record.phase is EvidencePhase.VERIFIER_GUIDED_REPAIR
    ]
    assert first_pass and repair
    assert all(record.status == "PASS" for record in repair)
    assert len(first_pass) + len(repair) == len(lineage.evidence)
    l4_first_pass = next(record for record in first_pass if record.tier == "L4")
    l4_repair = next(record for record in repair if record.tier == "L4")
    assert l4_first_pass.status == "PARTIAL"
    assert l4_first_pass.score == "9/15"
    assert l4_repair.status == "PASS"
    assert l4_repair.score == "15/15"
    assert l4_first_pass.phase is EvidencePhase.FIRST_PASS
    assert l4_repair.phase is EvidencePhase.VERIFIER_GUIDED_REPAIR


def test_deepseek_l4_semantics_repair_proven_first_pass_not_proven() -> None:
    lineage = _registry().resolve_by_lineage_id("deepseek-v4-flash")
    notes = lineage.experimental_notes
    assert any(
        "verifier-guided repair capability observed" in note and "15/15" in note for note in notes
    )
    assert any("first-pass reliability NOT proven" in note and "9/15" in note for note in notes)
    assert any("experimental and non-admitted" in note for note in notes)


def test_capability_evidence_provenance_is_honest() -> None:
    registry = _registry()
    for lineage_id in ("deepseek-v4-flash", "gemini-3.7-flash-medium"):
        lineage = registry.resolve_by_lineage_id(lineage_id)
        capability_refs = [ref.ref for ref in lineage.role_evidence] + [
            record.id for record in lineage.evidence
        ]
        assert not any("model_workforce.yaml" in ref for ref in capability_refs)
        for record in lineage.evidence:
            assert record.provenance in {
                "OWNER_DECISION",
                "EXTERNAL_CALIBRATION_RECEIPT_PENDING_DURABLE_WRITEBACK",
            }
            assert record.digest is None
    assert (
        registry.resolve_by_lineage_id("gemini-3.7-flash-medium").evidence[0].provenance
        == "OWNER_DECISION"
    )


def test_workforce_authority_refs_separate_from_capability_evidence() -> None:
    registry = _registry()
    gemini = registry.resolve_by_lineage_id("gemini-3.7-flash-medium")
    gemini_refs = {
        (ref.provider, ref.model, ref.current_autonomy) for ref in gemini.workforce_authority_refs
    }
    assert gemini_refs == {("agy", "gemini-3.7-flash-medium", "L3")}

    deepseek = registry.resolve_by_lineage_id("deepseek-v4-flash")
    deepseek_refs = {
        (ref.provider, ref.model, ref.current_autonomy) for ref in deepseek.workforce_authority_refs
    }
    assert deepseek_refs == {("opencode", "opencode/deepseek-v4-flash-free", "L2")}

    # Workforce authority is current context only; it does not become semantic
    # calibration evidence and it does not admit unregistered aliases.
    assert all("model_workforce.yaml" in ref.ref for ref in gemini.workforce_authority_refs)
    assert all("model_workforce.yaml" in ref.ref for ref in deepseek.workforce_authority_refs)


def test_capability_evidence_provenance_contradiction_rejected(tmp_path: Path) -> None:
    data = yaml.safe_load(LINEAGE_PATH.read_text(encoding="utf-8"))
    gemini = data["lineages"]["gemini-3.7-flash-medium"]
    gemini["role_evidence"][0]["ref"] = "nexus/config/model_workforce.yaml#workers.agy_flash_medium"
    gemini["role_evidence"][0]["provenance"] = "WORKFORCE_AUTHORITY_REF"
    bad = tmp_path / "bad_prov.yaml"
    bad.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="contradicts referenced workforce identity"):
        ModelCapabilityLineageRegistry(bad).load()


def test_capability_evidence_provenance_matching_identity_accepted(tmp_path: Path) -> None:
    data = yaml.safe_load(LINEAGE_PATH.read_text(encoding="utf-8"))
    deepseek = data["lineages"]["deepseek-v4-flash"]
    deepseek["role_evidence"][0]["ref"] = (
        "nexus/config/model_workforce.yaml#workers.opencode_deepseek_v4_flash"
    )
    deepseek["role_evidence"][0]["provenance"] = "WORKFORCE_AUTHORITY_REF"
    ok = tmp_path / "ok_prov.yaml"
    ok.write_text(yaml.dump(data), encoding="utf-8")
    assert ModelCapabilityLineageRegistry(ok).load()


def test_frontier_plus_one_exploratory_uses_next_formal_tier() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode-go/deepseek-v4-flash",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    assert plan.current_frontier == "L3"
    exploratory = [
        trial
        for trial in plan.required_trials
        if trial.kind is TrialKind.FRONTIER_PLUS_ONE_EXPLORATORY
    ]
    assert len(exploratory) == 1
    assert exploratory[0].tier == "L4"
    assert exploratory[0].optional is True


def test_frontier_plus_one_omitted_at_highest_formal_tier() -> None:
    plan = _planner().build_calibration_plan(
        provider="agy",
        model="gemini-3.7-flash-medium",
        target_role="focused_verification",
        change_kind="model_revision_or_backend_change",
    )
    assert plan.current_frontier == "L4"
    exploratory = [
        trial
        for trial in plan.required_trials
        if trial.kind is TrialKind.FRONTIER_PLUS_ONE_EXPLORATORY
    ]
    assert exploratory == []


def test_known_failure_families_remain_queryable() -> None:
    registry = _registry()
    families = registry.known_failure_families("deepseek-v4-flash")
    assert any(family.family == "full_context_envelope_failure" for family in families)
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode/deepseek-v4-flash-free",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    assert plan.failure_family_probes
    assert all(
        probe["probe_kind"] == "adjacent_variant" and probe["hidden_case"] == "fresh"
        for probe in plan.failure_family_probes
    )


def test_frontier_probe_shape_matches_expected_pipeline() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode-go/deepseek-v4-flash",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    order = [trial.kind for trial in plan.required_trials]
    assert order.index(TrialKind.STABLE_FLOOR_REGRESSION) < order.index(
        TrialKind.FRONTIER_EVALUATION
    )
    assert order.index(TrialKind.FRONTIER_EVALUATION) < order.index(TrialKind.FRONTIER_HIDDEN_PROBE)
    assert order.index(TrialKind.FRONTIER_HIDDEN_PROBE) < order.index(
        TrialKind.VERIFIER_GUIDED_REPAIR
    )
    assert order.index(TrialKind.VERIFIER_GUIDED_REPAIR) < order.index(
        TrialKind.FRONTIER_PLUS_ONE_EXPLORATORY
    )


def test_evidence_bundle_reports_calibration_only_admission_authority() -> None:
    bundle = _planner().evidence_bundle(lineage_id="deepseek-v4-flash")
    assert bundle["admission_authority"] == ADMISSION_AUTHORITY_SEPARATE
    assert "NOT Workforce Admission" in bundle["disclaimer"]
    assert bundle["frontier"] == "L3"
    assert bundle["conditional_ceiling"] == "L3"
    assert bundle["experimental_ceiling"] == "L4"


def test_lineage_evidence_cannot_raise_model_workforce_autonomy() -> None:
    loader = WorkforcePolicyLoader()
    snapshot = loader.load()
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode-go/deepseek-v4-flash",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    assert plan.admission_authority == ADMISSION_AUTHORITY_SEPARATE
    registered = {(w.provider, w.model) for w in snapshot.workers.values()}
    assert ("opencode", "opencode/deepseek-v4-flash-free") in registered
    assert ("opencode", "opencode-go/deepseek-v4-flash") not in registered
    request = WorkforceAdmissionRequest(
        provider="opencode",
        model="opencode-go/deepseek-v4-flash",
        role="compact_code_candidate",
        autonomy="L1",
        context="nexus_bounded",
        route_authorized=True,
    )
    decision = loader.admit(request, snapshot)
    assert decision.decision is AdmissionDecision.BLOCK
    assert any("Unknown worker" in reason for reason in decision.decision_reasons)


def test_calibration_service_never_invokes_provider_subprocess(monkeypatch) -> None:
    def _fail(*args, **kwargs):
        raise AssertionError("calibration planner must never spawn a subprocess")

    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(subprocess, "run", _fail)
    planner = _planner()
    planner.build_calibration_plan(
        provider="opencode",
        model="opencode-go/deepseek-v4-flash",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    planner.evidence_bundle(lineage_id="deepseek-v4-flash")


def test_plan_action_does_not_mutate_workforce_yaml() -> None:
    workforce_path = REPO_ROOT / "nexus/config/model_workforce.yaml"
    before = workforce_path.read_bytes()
    _planner().build_calibration_plan(
        provider="opencode",
        model="opencode/deepseek-v4-flash-free",
        target_role="compact_code_candidate",
        change_kind="alias_only",
    )
    assert workforce_path.read_bytes() == before


def test_plan_serializes_to_machine_readable_dict() -> None:
    plan = _planner().build_calibration_plan(
        provider="opencode",
        model="opencode/deepseek-v4-flash-free",
        target_role="compact_code_candidate",
        change_kind="transport_only",
    )
    data = plan.to_dict()
    assert data["schema"] == "nexus.model_calibration_plan.v1"
    assert data["change_class"] == "TRANSPORT_ONLY"
    for key in (
        "lineage_id",
        "stable_floor",
        "current_frontier",
        "reusable_evidence",
        "invalidated_evidence",
        "required_trials",
        "not_required_trials",
        "reasons",
        "admission_authority",
    ):
        assert key in data
    assert isinstance(data["required_trials"], list)
    assert isinstance(data["admission_authority"], str)


def test_occamy_lineage_seed_shape() -> None:
    registry = _registry()
    lineage = registry.resolve_by_lineage_id("occamy-1.0")
    identities = {(i.provider, i.model, i.identity_kind) for i in lineage.execution_identities}
    assert identities == {
        ("local", "occamy-1.0", "primary"),
        ("local", "occamy-1.0-q4", "alias"),
    }
    assert lineage.stable_floor == "L0.5"
    assert lineage.current_frontier == "L1"
    assert lineage.conditional_ceiling == "L1"
    assert lineage.experimental_ceiling == "L2"
    assert lineage.frontier_experimental is True
    assert len(lineage.execution_configurations) == 2

    by_id = {c.config_id: c for c in lineage.execution_configurations}
    assert "occamy-1.0-q4-opencode-llama32k" in by_id
    assert "occamy-1.0-q4-typed-decision-selective-shadow" in by_id

    agent_cfg = by_id["occamy-1.0-q4-opencode-llama32k"]
    assert isinstance(agent_cfg, ExecutionConfiguration)
    assert agent_cfg.model == "occamy-1.0-q4"
    assert agent_cfg.quant == "Q4_K_M"
    assert agent_cfg.package == "GGUF"
    assert agent_cfg.runtime == "llama.cpp"
    assert "build10964" in agent_cfg.runtime_build
    assert agent_cfg.context_limit == 32768
    assert agent_cfg.scaffold == "opencode_serve"
    assert agent_cfg.tool_surface == "opencode_builtin_tools"
    assert agent_cfg.write_mode == "workspace_edit"
    assert agent_cfg.state_preservation == "same_session_continuation"
    assert (
        agent_cfg.model_digest == "ffb25f763ff9c27f5f4e2adcdef399c5654f9f840fdac33dffe7035ba8266a87"
    )

    agent_quals = {q.task_family: q for q in agent_cfg.qualifications}
    assert isinstance(agent_quals["short_tool_use"], ExecutionConfigQualification)
    assert agent_quals["short_tool_use"].disposition is QualificationDisposition.PASS
    assert agent_quals["short_tool_use"].score == "PASS"
    assert agent_quals["short_tool_use"].phase is EvidencePhase.PROTOCOL_TOOL_LOOP_QUALIFICATION

    long_qual = agent_quals["long_repo_episode"]
    assert long_qual.disposition is QualificationDisposition.STACK_UNQUALIFIED
    assert long_qual.score == "0/2_STOPPED_BY_GATE"
    assert long_qual.is_semantic_failure is False
    assert long_qual.runtime_admission is False
    assert set(long_qual.failure_families) == {
        "session_startup_readiness",
        "context_state_overflow_54902_gt_32768",
    }

    decision_cfg = by_id["occamy-1.0-q4-typed-decision-selective-shadow"]
    assert decision_cfg.scaffold == "nexus_selective_shadow"
    assert decision_cfg.write_mode == "read_only"
    decision_quals = {q.task_family: q for q in decision_cfg.qualifications}
    dec_qual = decision_quals["bounded_decision"]
    assert dec_qual.disposition is QualificationDisposition.WATCH
    assert dec_qual.score == "30/30"
    assert dec_qual.false_safe_count == 0
    assert dec_qual.decision_delta == "UNPROVEN"
    assert dec_qual.runtime_admission is False


def test_qwen27b_lineage_seed_shape() -> None:
    registry = _registry()
    lineage = registry.resolve_by_lineage_id("qwen-3.8-27b")
    identities = {(i.provider, i.model) for i in lineage.execution_identities}
    assert identities == {("tensorfold", "Vontra/Qwen3.8-27B-MLX-4bit")}
    assert len(lineage.execution_configurations) == 1

    cfg = lineage.execution_configurations[0]
    assert cfg.config_id == "qwen3.8-27b-mlx4bit-tensorfold-drafted"
    assert cfg.model == "Vontra/Qwen3.8-27B-MLX-4bit"
    assert cfg.model_digest == "70ae7fac63274ff2eac54152031433374cb80f2f"
    assert "DFlash2" in str(cfg.drafter)
    assert cfg.runtime == "tensorfold"
    assert cfg.context_limit == 32768
    assert cfg.scaffold == "tensorfold_server"
    assert cfg.write_mode == "read_only"

    quals = {q.task_family: q for q in cfg.qualifications}
    assist_qual = quals["semantic_assist"]
    assert assist_qual.disposition is QualificationDisposition.WATCH
    assert assist_qual.score == "4 ACCEPTABLE + 1 CORRECT_ABSTAIN"
    assert assist_qual.false_safe_count == 0
    assert assist_qual.online_escalation_ratio == "4/5"
    assert assist_qual.decision_delta == "UNPROVEN"
    assert assist_qual.runtime_admission is False


def test_negative_control_short_tool_pass_does_not_promote_long_repo() -> None:
    registry = _registry()
    _, short_qual = registry.resolve_execution_qualification(
        "occamy-1.0-q4-opencode-llama32k", "short_tool_use"
    )
    _, long_qual = registry.resolve_execution_qualification(
        "occamy-1.0-q4-opencode-llama32k", "long_repo_episode"
    )
    assert short_qual.disposition is QualificationDisposition.PASS
    assert long_qual.disposition is QualificationDisposition.STACK_UNQUALIFIED
    assert short_qual.disposition != long_qual.disposition


def test_negative_control_stack_unqualified_is_not_semantic_fail() -> None:
    registry = _registry()
    _, long_qual = registry.resolve_execution_qualification(
        "occamy-1.0-q4-opencode-llama32k", "long_repo_episode"
    )
    assert long_qual.disposition is QualificationDisposition.STACK_UNQUALIFIED
    assert long_qual.is_semantic_failure is False
    assert long_qual.disposition is not QualificationDisposition.FAIL
    assert "54902_gt_32768" in str(long_qual.failure_families)


def test_negative_control_watch_does_not_promote_workforce_admission() -> None:
    registry = _registry()
    _, qual = registry.resolve_execution_qualification(
        "qwen3.8-27b-mlx4bit-tensorfold-drafted", "semantic_assist"
    )
    assert qual.disposition is QualificationDisposition.WATCH
    assert qual.runtime_admission is False

    loader = WorkforcePolicyLoader()
    snapshot = loader.load()
    req = WorkforceAdmissionRequest(
        provider="tensorfold",
        model="Vontra/Qwen3.8-27B-MLX-4bit",
        role="semantic_assist",
        autonomy="L1",
        context="nexus_bounded",
        route_authorized=True,
    )
    decision = loader.admit(req, snapshot)
    assert decision.decision is AdmissionDecision.BLOCK
    assert any("Unknown worker" in r for r in decision.decision_reasons)


def test_negative_control_not_evaluated_does_not_become_pass() -> None:
    registry = _registry()
    _, qual = registry.resolve_execution_qualification(
        "occamy-1.0-q4-opencode-llama32k", "bounded_code_repair"
    )
    assert qual.disposition is QualificationDisposition.NOT_EVALUATED
    assert qual.disposition is not QualificationDisposition.PASS


def test_negative_control_semantic_lineage_equivalence_does_not_imply_configuration_equivalence() -> (
    None
):
    registry = _registry()
    lineage = registry.resolve_by_lineage_id("occamy-1.0")
    by_id = {c.config_id: c for c in lineage.execution_configurations}
    c1 = by_id["occamy-1.0-q4-opencode-llama32k"]
    c2 = by_id["occamy-1.0-q4-typed-decision-selective-shadow"]

    assert c1.config_id != c2.config_id
    assert c1.scaffold != c2.scaffold
    assert c1.write_mode != c2.write_mode
    assert c1.state_preservation != c2.state_preservation
    assert {q.task_family for q in c1.qualifications} != {q.task_family for q in c2.qualifications}


def test_negative_control_execution_configuration_qualification_cannot_grant_admission(
    tmp_path: Path,
) -> None:
    data = _minimal_lineage_yaml()
    data["lineages"]["lineage-a"]["execution_configurations"] = [
        {
            "config_id": "cfg-invalid-admission",
            "model": "m-a",
            "qualifications": [
                {
                    "task_family": "short_tool_use",
                    "disposition": "PASS",
                    "phase": "FIRST_PASS",
                    "runtime_admission": True,
                }
            ],
        }
    ]
    bad = tmp_path / "bad-admission.yaml"
    bad.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="cannot grant runtime admission"):
        ModelCapabilityLineageRegistry(bad).load()


def test_negative_control_stack_unqualified_cannot_be_marked_semantic_failure(
    tmp_path: Path,
) -> None:
    data = _minimal_lineage_yaml()
    data["lineages"]["lineage-a"]["execution_configurations"] = [
        {
            "config_id": "cfg-invalid-stack-fail",
            "model": "m-a",
            "qualifications": [
                {
                    "task_family": "long_repo_episode",
                    "disposition": "STACK_UNQUALIFIED",
                    "phase": "RESOURCE_CONTEXT_QUALIFICATION",
                    "is_semantic_failure": True,
                }
            ],
        }
    ]
    bad = tmp_path / "bad-stack-fail.yaml"
    bad.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="stack/protocol limits are not semantic FAIL"):
        ModelCapabilityLineageRegistry(bad).load()


def test_unknown_and_ambiguous_configuration_identity_fails_closed() -> None:
    registry = _registry()
    with pytest.raises(LineageResolutionError, match="Unknown execution configuration identity"):
        registry.get_execution_configuration("non-existent-cfg")

    with pytest.raises(LineageResolutionError, match="Ambiguous execution configuration"):
        registry.resolve_configuration(model="occamy-1.0-q4")

    with pytest.raises(
        LineageResolutionError, match="requires config_id or discriminating parameters"
    ):
        registry.resolve_configuration()

    with pytest.raises(
        LineageResolutionError, match="No registered execution configuration matches criteria"
    ):
        registry.resolve_configuration(model="non-existent-model")


def test_resolve_configuration_exact_match() -> None:
    registry = _registry()
    lineage, cfg = registry.resolve_configuration(config_id="occamy-1.0-q4-opencode-llama32k")
    assert lineage.lineage_id == "occamy-1.0"
    assert cfg.config_id == "occamy-1.0-q4-opencode-llama32k"

    lineage2, cfg2 = registry.resolve_configuration(
        model="occamy-1.0-q4", scaffold="opencode_serve"
    )
    assert cfg2.config_id == "occamy-1.0-q4-opencode-llama32k"


def test_read_only_evidence_bundle_exposes_configuration_without_provider_call(
    monkeypatch,
) -> None:
    def _fail(*args, **kwargs):
        raise AssertionError("calibration queries must never spawn a subprocess")

    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(subprocess, "run", _fail)

    bundle = _planner().evidence_bundle(config_id="occamy-1.0-q4-opencode-llama32k")
    assert bundle["selected_configuration"]["config_id"] == "occamy-1.0-q4-opencode-llama32k"
    assert len(bundle["execution_configurations"]) >= 2
    assert bundle["admission_authority"] == ADMISSION_AUTHORITY_SEPARATE


def test_duplicate_config_id_rejected(tmp_path: Path) -> None:
    data = _minimal_lineage_yaml()
    data["lineages"]["lineage-a"]["execution_configurations"] = [
        {"config_id": "dup-id", "model": "m-a"},
        {"config_id": "dup-id", "model": "m-a"},
    ]
    bad = tmp_path / "bad-dup-config.yaml"
    bad.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="Duplicate execution configuration config_id"):
        ModelCapabilityLineageRegistry(bad).load()


def test_truthful_provenance_preserved_for_local_models() -> None:
    registry = _registry()
    for lineage_id in ("occamy-1.0", "qwen-3.8-27b"):
        lineage = registry.resolve_by_lineage_id(lineage_id)
        for record in lineage.evidence:
            assert record.provenance == "EXTERNAL_CALIBRATION_RECEIPT_PENDING_DURABLE_WRITEBACK"
            assert record.provenance != "DURABLE_REPOSITORY_RECEIPT"
        for cfg in lineage.execution_configurations:
            for q in cfg.qualifications:
                assert q.provenance == "EXTERNAL_CALIBRATION_RECEIPT_PENDING_DURABLE_WRITEBACK"
                assert q.provenance != "DURABLE_REPOSITORY_RECEIPT"



def test_config_id_conflicting_exact_criteria_fail_closed() -> None:
    registry = _registry()
    with pytest.raises(LineageResolutionError, match="conflicts with supplied exact criteria"):
        registry.resolve_configuration(
            config_id="occamy-1.0-q4-opencode-llama32k",
            model="occamy-1.0",
        )
    with pytest.raises(LineageResolutionError, match="conflicts with supplied exact criteria"):
        registry.resolve_configuration(
            config_id="occamy-1.0-q4-opencode-llama32k",
            scaffold="nexus_selective_shadow",
        )


def test_evidence_bundle_config_id_rejects_same_lineage_wrong_model() -> None:
    with pytest.raises(LineageResolutionError, match="conflicts with supplied exact criteria"):
        _planner().evidence_bundle(
            config_id="occamy-1.0-q4-opencode-llama32k",
            model="occamy-1.0",
        )


def test_execution_configuration_model_must_be_registered_lineage_identity(tmp_path: Path) -> None:
    data = _minimal_lineage_yaml()
    data["lineages"]["lineage-a"]["execution_configurations"] = [
        {"config_id": "cfg-foreign-model", "model": "not-a-lineage-identity"}
    ]
    bad = tmp_path / "bad-config-model.yaml"
    bad.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="not a registered execution identity"):
        ModelCapabilityLineageRegistry(bad).load()


def test_duplicate_task_family_phase_qualification_rejected(tmp_path: Path) -> None:
    data = _minimal_lineage_yaml()
    data["lineages"]["lineage-a"]["execution_configurations"] = [
        {
            "config_id": "cfg-duplicate-phase",
            "model": "m-a",
            "qualifications": [
                {
                    "task_family": "bounded_code_repair",
                    "disposition": "PASS",
                    "phase": "FIRST_PASS",
                },
                {
                    "task_family": "bounded_code_repair",
                    "disposition": "WATCH",
                    "phase": "FIRST_PASS",
                },
            ],
        }
    ]
    bad = tmp_path / "bad-duplicate-phase.yaml"
    bad.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(LineageValidationError, match="duplicate qualification"):
        ModelCapabilityLineageRegistry(bad).load()


def test_multi_phase_qualification_requires_phase_for_exact_resolution(tmp_path: Path) -> None:
    data = _minimal_lineage_yaml()
    data["lineages"]["lineage-a"]["execution_configurations"] = [
        {
            "config_id": "cfg-multi-phase",
            "model": "m-a",
            "qualifications": [
                {
                    "task_family": "bounded_code_repair",
                    "disposition": "PASS",
                    "phase": "FIRST_PASS",
                },
                {
                    "task_family": "bounded_code_repair",
                    "disposition": "WATCH",
                    "phase": "INDEPENDENT_HIDDEN_PROBE",
                },
            ],
        }
    ]
    path = tmp_path / "multi-phase.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    registry = ModelCapabilityLineageRegistry(path)
    with pytest.raises(LineageResolutionError, match="Ambiguous qualification"):
        registry.resolve_execution_qualification("cfg-multi-phase", "bounded_code_repair")

    _, hidden = registry.resolve_execution_qualification(
        "cfg-multi-phase",
        "bounded_code_repair",
        EvidencePhase.INDEPENDENT_HIDDEN_PROBE,
    )
    assert hidden.disposition is QualificationDisposition.WATCH
    assert hidden.phase is EvidencePhase.INDEPENDENT_HIDDEN_PROBE


def test_parameter_count_not_used_as_capability_identity() -> None:
    registry = _registry()
    occamy = registry.resolve_by_lineage_id("occamy-1.0")
    by_id = {c.config_id: c for c in occamy.execution_configurations}
    c_agent = by_id["occamy-1.0-q4-opencode-llama32k"]
    c_decision = by_id["occamy-1.0-q4-typed-decision-selective-shadow"]

    # Both share the same base model and quantization
    assert c_agent.model == c_decision.model
    assert c_agent.quant == c_decision.quant
    # Capability identity is distinguished by runtime + scaffold + tool surface + state preservation
    assert c_agent.runtime_build != c_decision.runtime_build
    assert c_agent.scaffold != c_decision.scaffold
    assert c_agent.tool_surface != c_decision.tool_surface
    assert c_agent.state_preservation != c_decision.state_preservation
