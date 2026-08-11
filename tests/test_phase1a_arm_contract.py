from __future__ import annotations

import pytest

from nexus.research.epistemic_benchmark.phase1a_contracts import (
    ComparabilityReason,
    ComparabilityStatus,
    Phase1AArm,
    Phase1AArmIdentity,
    compare_arm_identities,
    compute_triplet_comparability_fingerprint,
    validate_triplet_comparability,
)


def make_valid_identity(arm: Phase1AArm = Phase1AArm.A, **kwargs) -> Phase1AArmIdentity:
    defaults = {
        "arm": arm,
        "task_id": "task-143",
        "task_contract_hash": "a" * 64,
        "source_corpus_id": "corpus-v1",
        "online_provider": "anthropic",
        "online_model": "claude-3-5-sonnet",
        "online_prompt_policy_hash": "b" * 64,
        "tool_surface": {"tools": ["search", "read"]},
        "budgets_timeouts": {"timeout_sec": 300},
        "final_verifier_contract_hash": "c" * 64,
        "quality_gate_contract_hash": "d" * 64,
        "planner_decision_id": "planner-dec-001",
        "has_online_stage": True,
        "local_provider_called": False,
        "local_is_routing_authority": False,
        "local_is_final_verifier": False,
        "local_is_approval_authority": False,
        "local_is_authoritative_patch_producer": False,
    }
    defaults.update(kwargs)
    return Phase1AArmIdentity(**defaults)


def test_local_provider_call_in_a_and_b_rejected():
    with pytest.raises(ValueError, match="Arm A Nexus baseline rejects"):
        make_valid_identity(arm=Phase1AArm.A, local_provider_called=True)
    with pytest.raises(ValueError, match="Arm B rejects any Phase 1A Local provider call"):
        make_valid_identity(arm=Phase1AArm.B, local_provider_called=True)


def test_exact_arm_semantics_are_physically_encoded():
    sem_a = make_valid_identity(arm=Phase1AArm.A).treatment_semantics()
    sem_b = make_valid_identity(arm=Phase1AArm.B).treatment_semantics()
    sem_c = make_valid_identity(arm=Phase1AArm.C, local_provider_called=True).treatment_semantics()

    assert sem_a.nexus_baseline is True
    assert sem_a.deterministic_evidence_mediation is False
    assert sem_a.bounded_local_semantic_exploration is False
    assert sem_b.nexus_baseline is False
    assert sem_b.deterministic_evidence_mediation is True
    assert sem_b.bounded_local_semantic_exploration is False
    assert sem_c.nexus_baseline is False
    assert sem_c.deterministic_evidence_mediation is True
    assert sem_c.bounded_local_semantic_exploration is True
    assert sem_a.online_required and sem_b.online_required and sem_c.online_required
    assert (
        sem_a.independent_final_verifier_required
        and sem_b.independent_final_verifier_required
        and sem_c.independent_final_verifier_required
    )


def test_missing_online_stage_rejected():
    for arm in (Phase1AArm.A, Phase1AArm.B, Phase1AArm.C):
        with pytest.raises(ValueError, match="Phase 1A arms require an Online stage"):
            make_valid_identity(arm=arm, has_online_stage=False)


def test_bc_arm_substitution_rejected_distinctly_from_treatment_drift():
    spec_b = make_valid_identity(arm=Phase1AArm.B)
    spec_c = make_valid_identity(arm=Phase1AArm.C, local_provider_called=True)

    res = compare_arm_identities(spec_b, spec_c, require_same_arm=True)
    assert not res.is_comparable
    assert ComparabilityReason.ARM_MISMATCH in res.reasons
    assert ComparabilityReason.ONLINE_PROVIDER_DRIFT not in res.reasons

    spec_a = make_valid_identity(arm=Phase1AArm.A)
    res_triplet = validate_triplet_comparability(spec_a, spec_c, spec_b)
    assert not res_triplet.is_comparable
    assert ComparabilityReason.ARM_MISMATCH in res_triplet.reasons


def test_task_identity_drift_isolated():
    spec1 = make_valid_identity(task_id="task-1")
    spec2 = make_valid_identity(task_id="task-2")
    res = compare_arm_identities(spec1, spec2)
    assert not res.is_comparable
    assert res.status == ComparabilityStatus.NON_COMPARABLE
    assert res.reasons == (ComparabilityReason.TASK_IDENTITY_DRIFT,)


def test_source_corpus_identity_drift_isolated():
    spec1 = make_valid_identity(source_corpus_id="corpus-1")
    spec2 = make_valid_identity(source_corpus_id="corpus-2")
    res = compare_arm_identities(spec1, spec2)
    assert not res.is_comparable
    assert res.reasons == (ComparabilityReason.SOURCE_CORPUS_DRIFT,)


def test_online_provider_model_prompt_drift_isolated():
    res_prov = compare_arm_identities(
        make_valid_identity(online_provider="prov-a"),
        make_valid_identity(online_provider="prov-b"),
    )
    assert not res_prov.is_comparable
    assert res_prov.reasons == (ComparabilityReason.ONLINE_PROVIDER_DRIFT,)

    res_mod = compare_arm_identities(
        make_valid_identity(online_model="model-1"),
        make_valid_identity(online_model="model-2"),
    )
    assert not res_mod.is_comparable
    assert res_mod.reasons == (ComparabilityReason.ONLINE_MODEL_DRIFT,)

    res_prompt = compare_arm_identities(
        make_valid_identity(online_prompt_policy_hash="p1" * 32),
        make_valid_identity(online_prompt_policy_hash="p2" * 32),
    )
    assert not res_prompt.is_comparable
    assert res_prompt.reasons == (ComparabilityReason.ONLINE_PROMPT_POLICY_DRIFT,)


def test_tool_surface_and_budget_timeout_drift_isolated():
    res_tool = compare_arm_identities(
        make_valid_identity(tool_surface={"tools": ["a"]}),
        make_valid_identity(tool_surface={"tools": ["b"]}),
    )
    assert not res_tool.is_comparable
    assert res_tool.reasons == (ComparabilityReason.TOOL_SURFACE_DRIFT,)

    res_budget = compare_arm_identities(
        make_valid_identity(budgets_timeouts={"t": 100}),
        make_valid_identity(budgets_timeouts={"t": 200}),
    )
    assert not res_budget.is_comparable
    assert res_budget.reasons == (ComparabilityReason.BUDGET_TIMEOUT_DRIFT,)


def test_final_verifier_and_quality_gate_drift_isolated():
    res_v = compare_arm_identities(
        make_valid_identity(final_verifier_contract_hash="v1" * 32),
        make_valid_identity(final_verifier_contract_hash="v2" * 32),
    )
    assert not res_v.is_comparable
    assert res_v.reasons == (ComparabilityReason.FINAL_VERIFIER_CONTRACT_DRIFT,)

    res_q = compare_arm_identities(
        make_valid_identity(quality_gate_contract_hash="q1" * 32),
        make_valid_identity(quality_gate_contract_hash="q2" * 32),
    )
    assert not res_q.is_comparable
    assert res_q.reasons == (ComparabilityReason.QUALITY_GATE_CONTRACT_DRIFT,)


def test_planner_decision_identity_drift_isolated():
    res_p = compare_arm_identities(
        make_valid_identity(planner_decision_id="plan-1"),
        make_valid_identity(planner_decision_id="plan-2"),
    )
    assert not res_p.is_comparable
    assert res_p.reasons == (ComparabilityReason.PLANNER_DECISION_DRIFT,)


def test_legacy_benchmark_arm_values_rejected():
    legacy_values = ["standard_review", "strong_protocol", "epistemic_workflow"]
    for val in legacy_values:
        with pytest.raises(ValueError, match="Legacy BenchmarkArm"):
            make_valid_identity(arm=val)


def test_legacy_vap_bd_semantics_labels_rejected():
    legacy_bd = ["B_LEGACY", "D_LEGACY", "D", "TREATMENT_B", "TREATMENT_D"]
    for val in legacy_bd:
        with pytest.raises(ValueError, match="Legacy VAP B/D"):
            make_valid_identity(arm=val)


def test_c_objects_attempting_local_authority_rejected():
    authorities = [
        "local_is_routing_authority",
        "local_is_final_verifier",
        "local_is_approval_authority",
        "local_is_authoritative_patch_producer",
    ]
    for auth in authorities:
        with pytest.raises(ValueError, match="Local can never be"):
            make_valid_identity(arm=Phase1AArm.C, local_provider_called=True, **{auth: True})


def test_deterministic_fingerprint_under_mapping_key_order_changes():
    spec1 = make_valid_identity(
        tool_surface={"b": 2, "a": 1, "nested": {"z": 10, "m": 5}},
        budgets_timeouts={"timeout": 300, "tokens": 5000},
    )
    spec2 = make_valid_identity(
        tool_surface={"a": 1, "nested": {"m": 5, "z": 10}, "b": 2},
        budgets_timeouts={"tokens": 5000, "timeout": 300},
    )
    assert spec1.triplet_fingerprint() == spec2.triplet_fingerprint()

    spec_a = make_valid_identity(arm=Phase1AArm.A, tool_surface={"b": 2, "a": 1})
    spec_b = make_valid_identity(arm=Phase1AArm.B, tool_surface={"a": 1, "b": 2})
    spec_c = make_valid_identity(
        arm=Phase1AArm.C, tool_surface={"a": 1, "b": 2}, local_provider_called=True
    )

    assert (
        compute_triplet_comparability_fingerprint(spec_a, spec_b, spec_c)
        == spec_a.triplet_fingerprint()
    )


def test_empty_identity_variants_fail_closed():
    str_fields = [
        "task_id",
        "task_contract_hash",
        "source_corpus_id",
        "online_provider",
        "online_model",
        "online_prompt_policy_hash",
        "final_verifier_contract_hash",
        "quality_gate_contract_hash",
        "planner_decision_id",
    ]
    for field in str_fields:
        with pytest.raises(ValueError, match="cannot be empty or whitespace"):
            make_valid_identity(**{field: ""})
        with pytest.raises(ValueError, match="cannot be empty or whitespace"):
            make_valid_identity(**{field: "   "})
        with pytest.raises(ValueError, match="cannot be None"):
            make_valid_identity(**{field: None})

    with pytest.raises(ValueError, match="cannot be empty"):
        make_valid_identity(tool_surface={})
    with pytest.raises(ValueError, match="cannot be empty"):
        make_valid_identity(tool_surface=[])
    with pytest.raises(ValueError, match="must be dict, list, tuple"):
        make_valid_identity(tool_surface={"alpha", "beta"})
    with pytest.raises(ValueError, match="unordered set/frozenset"):
        make_valid_identity(tool_surface={"tools": {"read", "search"}})
    with pytest.raises(ValueError, match="unordered set/frozenset"):
        make_valid_identity(tool_surface={"nested": [{"tools": frozenset({"read", "search"})}]})
    with pytest.raises(ValueError, match="cannot be empty"):
        make_valid_identity(budgets_timeouts={})
    with pytest.raises(ValueError, match="must be dict"):
        make_valid_identity(budgets_timeouts=[("timeout", 300)])
    with pytest.raises(ValueError, match="unordered set/frozenset"):
        make_valid_identity(budgets_timeouts={"limits": {"tiers": {"fast", "slow"}}})


def test_bare_arm_strings_rejected():
    bare_arms = ["A", "B", "C", "D", "a", "b", "c", "d"]
    for val in bare_arms:
        with pytest.raises(ValueError):
            make_valid_identity(arm=val)


def test_scoped_enum_values_roundtrip():
    for arm_enum in Phase1AArm:
        identity_from_str = make_valid_identity(arm=arm_enum.value)
        assert identity_from_str.arm == arm_enum
        assert identity_from_str.full_identity_dict()["arm"] == arm_enum.value

        identity_from_enum = make_valid_identity(arm=arm_enum)
        assert identity_from_enum.arm == arm_enum
        assert identity_from_enum.full_identity_dict()["arm"] == arm_enum.value
