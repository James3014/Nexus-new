from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import replace

import pytest

from nexus.research.epistemic_benchmark.phase1a_contracts import (
    Phase1AArm,
    Phase1AArmIdentity,
)
from nexus.research.epistemic_benchmark.phase1a_measurement import (
    ActionEvent,
    ActionKind,
    AdmissibleObservationSet,
    EpistemicType,
    EvidenceObservation,
    EvidenceProducerPhase,
    EvidenceRef,
    TrajectoryPhase,
    ValidationState,
    build_admissible_observation_set,
    validate_trajectory,
)
from nexus.research.epistemic_benchmark.phase1a_qualification import (
    Phase1AFrozenManifest,
    Phase1ARunRow,
    RunClassification,
    RunKind,
)
from nexus.research.epistemic_benchmark.phase1a_report import (
    Phase1ADecisionEvidence,
    Phase1AReportRunSource,
    Phase1AReportSource,
    build_phase1a_report,
    verify_phase1a_report,
)
from nexus.services.verified_assist_contract import (
    build_verified_assist_packet,
    record_packet_consumption,
    settle_main_chain,
)


def _h(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _manifest(**overrides) -> Phase1AFrozenManifest:
    values = {
        "phase1a_contract_hash": _h("contract"),
        "repository_source_snapshots": {"git_main": "a" * 40, "corpus": _h("corpus")},
        "qualification_task_ids": ("qual-1",),
        "formal_task_ids": ("task-1",),
        "arm_semantics_hash": _h("arm-semantics"),
        "treatment_fingerprint_policy_hash": _h("treatment-policy"),
        "planner_route_policy_hash": _h("planner-route"),
        "online_prompt_policy_hash": _h("online-prompt"),
        "final_verifier_contract_hash": _h("final-verifier"),
        "quality_gate_contract_hash": _h("quality-gate"),
        "deterministic_pipeline_hash": _h("pipeline"),
        "evidence_observation_contract_hash": _h("evidence-observation"),
        "provider_safe_projection_contract_hash": _h("provider-safe"),
        "consumption_proof_contract_hash": _h("consumption-proof"),
        "settlement_contract_hash": _h("settlement"),
        "trajectory_schema_hash": _h("trajectory"),
        "action_normalization_rule_hash": _h("action-normalization"),
        "recomputation_formula_hash": _h("recomputation"),
        "invalid_run_taxonomy_hash": _h("invalid-taxonomy"),
        "online_provider": "online-provider-v1",
        "online_model": "provider/model-v1",
        "local_provider": "ollama",
        "local_model": "qwen2.5-coder:7b-instruct",
        "accounting_policy_hash": _h("accounting"),
        "pairing_rule_hash": _h("pairing"),
        "execution_order_rule_id": "phase1a-six-permutation-v1",
        "execution_order_seed": 172,
        "meaningful_improvement_thresholds": {
            "ba_min_avoided_actions": 1.0,
            "cb_min_avoided_actions": 1.0,
        },
        "report_schema_verifier_hash": _h("report-schema-verifier"),
        "required_issue29_evidence_identity": _h("issue29"),
        "manifest_version": "phase1a-v1",
    }
    values.update(overrides)
    return Phase1AFrozenManifest(**values)


def _identity(arm: Phase1AArm, *, task_id: str = "task-1", **overrides) -> Phase1AArmIdentity:
    values = {
        "arm": arm,
        "task_id": task_id,
        "task_contract_hash": _h("task-contract"),
        "source_corpus_id": "phase1a-corpus-v1",
        "online_provider": "online-provider-v1",
        "online_model": "provider/model-v1",
        "online_prompt_policy_hash": _h("online-prompt"),
        "tool_surface": {"read": True, "test": True},
        "budgets_timeouts": {"seconds": 60, "tokens": 1000},
        "final_verifier_contract_hash": _h("final-verifier"),
        "quality_gate_contract_hash": _h("quality-gate"),
        "planner_decision_id": "planner-decision-1",
        "local_provider_called": arm == Phase1AArm.C,
    }
    values.update(overrides)
    return Phase1AArmIdentity(**values)


def _event(
    manifest: Phase1AFrozenManifest,
    arm: Phase1AArm,
    *,
    sequence: int,
    phase: TrajectoryPhase,
    action_kind: ActionKind,
    target: str,
    payload: str,
    provider: str = "",
    model: str = "",
    validation: bool = False,
) -> ActionEvent:
    return ActionEvent(
        experiment_id="exp-1",
        manifest_id=manifest.manifest_sha256,
        run_id=f"run-{arm.value}",
        scope_id="scope-1",
        task_id="task-1",
        arm=arm,
        session_id=f"session-{arm.value}",
        attempt_id=f"attempt-{arm.value}",
        sequence=sequence,
        phase=phase,
        actor_class="online" if phase == TrajectoryPhase.ONLINE else "prework",
        normalized_target=target,
        action_kind=action_kind,
        signature_payload={"operation": payload},
        evidence_refs=(f"evidence:{arm.value}:{sequence}",),
        provider=provider,
        model=model,
        status="OK",
        retry_count=0,
        started_at_ms=sequence * 1000,
        duration_ms=100,
        validation_evidence_refs=(f"validator:{arm.value}:{sequence}",) if validation else (),
        uncached_input_tokens=10,
    )


def _trajectory(manifest: Phase1AFrozenManifest, arm: Phase1AArm):
    online_provider = _event(
        manifest,
        arm,
        sequence=0 if arm != Phase1AArm.C else 2,
        phase=TrajectoryPhase.ONLINE,
        action_kind=ActionKind.PROVIDER_CALL,
        target="online-provider",
        payload="invoke-online",
        provider=manifest.online_provider,
        model=manifest.online_model,
    )
    if arm == Phase1AArm.A:
        events = (
            online_provider,
            _event(
                manifest,
                arm,
                sequence=1,
                phase=TrajectoryPhase.ONLINE,
                action_kind=ActionKind.FILE_READ,
                target="shared-ba.py",
                payload="read-ba",
            ),
        )
    elif arm == Phase1AArm.B:
        events = (
            _event(
                manifest,
                arm,
                sequence=0,
                phase=TrajectoryPhase.DETERMINISTIC_PREWORK,
                action_kind=ActionKind.FILE_READ,
                target="shared-ba.py",
                payload="read-ba",
                validation=True,
            ),
            _event(
                manifest,
                arm,
                sequence=1,
                phase=TrajectoryPhase.ONLINE,
                action_kind=ActionKind.FILE_READ,
                target="shared-cb.py",
                payload="read-cb",
            ),
            replace(online_provider, sequence=2, started_at_ms=2000),
        )
    else:
        events = (
            _event(
                manifest,
                arm,
                sequence=0,
                phase=TrajectoryPhase.LOCAL_EXPLORATION,
                action_kind=ActionKind.PROVIDER_CALL,
                target="local-provider",
                payload="invoke-local",
                provider=manifest.local_provider,
                model=manifest.local_model,
                validation=True,
            ),
            _event(
                manifest,
                arm,
                sequence=1,
                phase=TrajectoryPhase.LOCAL_EXPLORATION,
                action_kind=ActionKind.FILE_READ,
                target="shared-cb.py",
                payload="read-cb",
                validation=True,
            ),
            online_provider,
        )
    return validate_trajectory(events)


def _observation_set(arm: Phase1AArm, *, label: str = "obs"):
    phase = (
        EvidenceProducerPhase.DETERMINISTIC if arm == Phase1AArm.B else EvidenceProducerPhase.LOCAL
    )
    observation = EvidenceObservation(
        task_id="task-1",
        arm=arm,
        producer_phase=phase,
        epistemic_type=EpistemicType.OBSERVED,
        bounded_claim=f"bounded-{label}-{arm.value}",
        evidence_refs=(EvidenceRef(ref=f"ref-{label}", source_sha256=_h(f"src-{label}")),),
        derivation_lineage=(f"lineage-{label}",),
        validation_state=ValidationState.ADMISSIBLE,
        validator_contract_hash=_h("validator-contract"),
        validator_evidence_refs=(f"validator-evidence-{label}",),
        producer_verifier_independent=True,
    )
    return build_admissible_observation_set((observation,))


def _assist(
    task_id: str,
    observation_set: AdmissibleObservationSet,
    arm: Phase1AArm,
    *,
    treatment_run_id: str | None = None,
    planner_decision_id: str = "planner-decision-1",
    task_contract_hash: str | None = None,
):
    run_id = treatment_run_id or f"run-{arm.value}"
    contract_hash = task_contract_hash or _h("task-contract")
    packet = build_verified_assist_packet(
        task_id=task_id,
        treatment_run_id=run_id,
        planner_decision_id=planner_decision_id,
        task_contract_hash=contract_hash,
        target_files=("target.py",),
        semantic_assertions=(observation_set.vap_identity_marker, "bounded-only"),
        bounded_diagnosis="bounded diagnosis",
    )
    fragment = packet.compact_injection()
    consumption = record_packet_consumption(
        packet,
        injected_prompt_fragment=fragment,
        expected_packet_hash=packet.packet_hash,
        final_prompt="online-prefix\n" + fragment,
    )
    settlement = settle_main_chain(
        treatment_run_id=run_id,
        planner_decision_id=planner_decision_id,
        task_contract_hash=contract_hash,
        final_candidate_id=f"candidate-{arm.value}",
        verifier_result="pass",
        consumption=consumption,
    )
    return packet.to_dict(), consumption.to_dict(), settlement


def _run_source(manifest: Phase1AFrozenManifest, arm: Phase1AArm) -> Phase1AReportRunSource:
    trajectory = _trajectory(manifest, arm)
    row = Phase1ARunRow(
        task_id="task-1",
        run_kind=RunKind.FORMAL,
        classification=RunClassification.VALID_SUCCESS,
        metrics={"stored_total": 999, "semantic_score": 1.0},
    )
    if arm == Phase1AArm.A:
        return Phase1AReportRunSource(
            arm_identity=_identity(arm),
            trajectory=trajectory,
            run_row=row,
        )
    observation_set = _observation_set(arm)
    packet, consumption, settlement = _assist("task-1", observation_set, arm)
    return Phase1AReportRunSource(
        arm_identity=_identity(arm),
        trajectory=trajectory,
        run_row=row,
        observation_set=observation_set,
        verified_assist_packet=packet,
        verified_assist_consumption=consumption,
        settlement=settlement,
        reverified_observation_ids=observation_set.observation_ids,
    )


def _source(**overrides) -> Phase1AReportSource:
    manifest = overrides.pop("manifest", _manifest())
    values = {
        "manifest": manifest,
        "arm_a": _run_source(manifest, Phase1AArm.A),
        "arm_b": _run_source(manifest, Phase1AArm.B),
        "arm_c": _run_source(manifest, Phase1AArm.C),
        "decision_evidence": Phase1ADecisionEvidence(evidence_sha256=_h("decision-evidence")),
    }
    values.update(overrides)
    return Phase1AReportSource(**values)


def _replace_event(run: Phase1AReportRunSource, index: int, **changes) -> Phase1AReportRunSource:
    events = list(run.trajectory.events)
    events[index] = replace(events[index], **changes)
    return replace(run, trajectory=validate_trajectory(tuple(events)))


def test_build_and_replay_recompute_authoritative_report() -> None:
    source = _source()
    report = build_phase1a_report(source)
    verification = verify_phase1a_report(report, source)
    assert verification.ok is True
    assert verification.reasons == ()
    assert report["mechanisms"]["B_MINUS_A"]["avoided_total"] == 1
    assert report["mechanisms"]["C_MINUS_B"]["avoided_total"] == 1
    assert report["mechanisms"]["C_MINUS_A"]["kind"] == "TOTAL_EFFECT_ONLY"
    assert report["decision"] == "CONTINUE"
    assert report["metrics"]["A"]["provider_call_count"] == 1
    assert report["metrics"]["B"]["evidence_utilization_rate"] == 1.0
    assert report["metrics"]["C"]["provider_call_count"] == 2
    assert "stored_total" not in report["metrics"]["A"]
    assert report["claim_boundary"]["issue29_complete"] is False
    assert report["claim_boundary"]["g5_authorized"] is False
    assert report["claim_boundary"]["causal_benefit_proven"] is False


def test_mapping_order_is_deterministic() -> None:
    report = build_phase1a_report(_source())
    second = build_phase1a_report(_source())
    assert report == second
    assert report["report_sha256"] == second["report_sha256"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "other-task"),
        ("decision", "STOP"),
        ("manifest_sha256", _h("other-manifest")),
        ("formal_effect_arms", ["A", "C"]),
        ("thresholds", {"ba_min_avoided_actions": 999.0, "cb_min_avoided_actions": 1.0}),
    ],
)
def test_stored_report_projection_tamper_fails_replay(field: str, value) -> None:
    source = _source()
    report = build_phase1a_report(source)
    tampered = deepcopy(report)
    tampered[field] = value
    result = verify_phase1a_report(tampered, source)
    assert result.ok is False
    assert "REPORT_PROJECTION_TAMPERED" in result.reasons


def test_stored_metric_total_tamper_fails_even_with_original_hash() -> None:
    source = _source()
    report = build_phase1a_report(source)
    tampered = deepcopy(report)
    tampered["metrics"]["A"]["provider_call_count"] = 999
    result = verify_phase1a_report(tampered, source)
    assert result.ok is False
    assert "REPORT_PROJECTION_TAMPERED" in result.reasons
    assert "REPORT_SELF_HASH_INVALID" in result.reasons


def test_recomputed_hash_cannot_bless_changed_stored_decision() -> None:
    source = _source()
    tampered = deepcopy(build_phase1a_report(source))
    tampered["decision"] = "STOP"
    body = {key: value for key, value in tampered.items() if key != "report_sha256"}
    from nexus.research.epistemic_benchmark.phase1a_contracts import compute_canonical_sha256

    tampered["report_sha256"] = compute_canonical_sha256(body)
    result = verify_phase1a_report(tampered, source)
    assert result.ok is False
    assert "REPORT_PROJECTION_TAMPERED" in result.reasons
    assert "REPORT_HASH_MISMATCH" in result.reasons


def test_report_self_hash_tamper_fails() -> None:
    source = _source()
    report = build_phase1a_report(source)
    report["report_sha256"] = _h("forged")
    result = verify_phase1a_report(report, source)
    assert result.ok is False
    assert "REPORT_HASH_MISMATCH" in result.reasons
    assert "REPORT_SELF_HASH_INVALID" in result.reasons


def test_changed_task_identity_fails_closed() -> None:
    source = _source()
    bad_b = replace(source.arm_b, arm_identity=_identity(Phase1AArm.B, task_id="other-task"))
    with pytest.raises(ValueError, match="triplet is not comparable"):
        build_phase1a_report(replace(source, arm_b=bad_b))


def test_b_c_arm_swap_fails_closed() -> None:
    source = _source()
    with pytest.raises(ValueError, match="exact A/B/C arm order"):
        build_phase1a_report(replace(source, arm_b=source.arm_c, arm_c=source.arm_b))


def test_local_provider_call_injected_into_b_fails_closed() -> None:
    source = _source()
    event = source.arm_b.trajectory.events[0]
    injected = replace(
        event,
        phase=TrajectoryPhase.LOCAL_EXPLORATION,
        action_kind=ActionKind.PROVIDER_CALL,
        provider=source.manifest.local_provider,
        model=source.manifest.local_model,
        validation_evidence_refs=("validator:injected",),
    )
    events = (injected,) + source.arm_b.trajectory.events[1:]
    bad_b = replace(source.arm_b, trajectory=validate_trajectory(events))
    with pytest.raises(ValueError, match="Arm B rejects Local provider calls"):
        build_phase1a_report(replace(source, arm_b=bad_b))


def test_online_provider_call_removed_fails_closed() -> None:
    source = _source()
    events = tuple(
        event
        for event in source.arm_a.trajectory.events
        if event.action_kind != ActionKind.PROVIDER_CALL
    )
    bad_a = replace(source.arm_a, trajectory=validate_trajectory(events))
    with pytest.raises(ValueError, match="requires an Online provider call"):
        build_phase1a_report(replace(source, arm_a=bad_a))


def test_source_action_signature_change_is_detected_by_replay() -> None:
    source = _source()
    report = build_phase1a_report(source)
    event = source.arm_a.trajectory.events[1]
    bad_a = _replace_event(source.arm_a, 1, signature_payload={"operation": "different-read"})
    changed_source = replace(source, arm_a=bad_a)
    result = verify_phase1a_report(report, changed_source)
    assert result.ok is False
    assert "REPORT_PROJECTION_TAMPERED" in result.reasons
    assert event.event_sha256 != bad_a.trajectory.events[1].event_sha256


def test_trajectory_event_drop_is_detected() -> None:
    source = _source()
    report = build_phase1a_report(source)
    events = source.arm_b.trajectory.events[:-1]
    bad_b = replace(source.arm_b, trajectory=validate_trajectory(events))
    result = verify_phase1a_report(report, replace(source, arm_b=bad_b))
    assert result.ok is False


def test_trajectory_duplicate_or_reorder_fails_at_authoritative_trajectory_gate() -> None:
    source = _source()
    event = source.arm_b.trajectory.events[0]
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_trajectory((event, event) + source.arm_b.trajectory.events[1:])
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_trajectory(tuple(reversed(source.arm_b.trajectory.events)))


def test_admissible_observation_set_substitution_fails_physical_binding() -> None:
    source = _source()
    substituted = _observation_set(Phase1AArm.B, label="substituted")
    bad_b = replace(source.arm_b, observation_set=substituted)
    with pytest.raises(ValueError, match="physical consumption verification failed"):
        build_phase1a_report(replace(source, arm_b=bad_b))


def test_evidence_epistemic_type_change_changes_admissible_identity_and_fails_binding() -> None:
    source = _source()
    inferred = EvidenceObservation(
        task_id="task-1",
        arm=Phase1AArm.B,
        producer_phase=EvidenceProducerPhase.DETERMINISTIC,
        epistemic_type=EpistemicType.INFERRED,
        bounded_claim="bounded-inferred",
        evidence_refs=(),
        derivation_lineage=("derived-from-observed",),
        validation_state=ValidationState.ADMISSIBLE,
        validator_contract_hash=_h("validator-contract"),
        validator_evidence_refs=("validator-evidence",),
        producer_verifier_independent=True,
    )
    changed_set = build_admissible_observation_set((inferred,))
    bad_b = replace(source.arm_b, observation_set=changed_set)
    with pytest.raises(ValueError, match="physical consumption verification failed"):
        build_phase1a_report(replace(source, arm_b=bad_b))


def test_provider_safe_packet_substitution_fails_closed() -> None:
    source = _source()
    packet = deepcopy(source.arm_b.verified_assist_packet)
    assert packet is not None
    packet["packet_hash"] = _h("other-packet")
    bad_b = replace(source.arm_b, verified_assist_packet=packet)
    with pytest.raises(ValueError, match="physical consumption verification failed"):
        build_phase1a_report(replace(source, arm_b=bad_b))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "other-task"),
        ("treatment_run_id", "other-run"),
        ("planner_decision_id", "other-planner"),
        ("task_contract_hash", _h("other-contract")),
    ],
)
def test_packet_metadata_tamper_with_stale_hash_fails_closed(field: str, value: str) -> None:
    source = _source()
    packet = deepcopy(source.arm_b.verified_assist_packet)
    assert packet is not None
    packet[field] = value
    bad_b = replace(source.arm_b, verified_assist_packet=packet)
    with pytest.raises(ValueError, match="verified assist packet hash mismatch"):
        build_phase1a_report(replace(source, arm_b=bad_b))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("task_id", "other-task", "packet task identity mismatch"),
        ("treatment_run_id", "other-run", "packet treatment-run identity mismatch"),
        ("planner_decision_id", "other-planner", "packet planner-decision identity mismatch"),
        ("task_contract_hash", _h("other-contract"), "packet task-contract identity mismatch"),
    ],
)
def test_coherently_rebuilt_foreign_assist_identity_fails_closed(
    field: str, value: str, reason: str
) -> None:
    source = _source()
    kwargs = {
        "task_id": "task-1",
        "treatment_run_id": None,
        "planner_decision_id": "planner-decision-1",
        "task_contract_hash": None,
    }
    kwargs[field] = value
    packet, consumption, settlement = _assist(
        kwargs["task_id"],
        source.arm_b.observation_set,
        Phase1AArm.B,
        treatment_run_id=kwargs["treatment_run_id"],
        planner_decision_id=kwargs["planner_decision_id"],
        task_contract_hash=kwargs["task_contract_hash"],
    )
    bad_b = replace(
        source.arm_b,
        verified_assist_packet=packet,
        verified_assist_consumption=consumption,
        settlement=settlement,
    )
    with pytest.raises(ValueError, match=reason):
        build_phase1a_report(replace(source, arm_b=bad_b))


def test_packet_id_must_match_physical_consumption_identity() -> None:
    source = _source()
    packet = deepcopy(source.arm_b.verified_assist_packet)
    assert packet is not None
    packet["packet_id"] = "foreign-packet-id"
    bad_b = replace(source.arm_b, verified_assist_packet=packet)
    with pytest.raises(ValueError, match="packet/consumption packet-id mismatch"):
        build_phase1a_report(replace(source, arm_b=bad_b))


def test_final_prompt_physical_consumption_proof_tamper_fails_closed() -> None:
    source = _source()
    consumption = deepcopy(source.arm_b.verified_assist_consumption)
    assert consumption is not None
    consumption["final_prompt_hash"] = _h("tampered-final-prompt")
    bad_b = replace(source.arm_b, verified_assist_consumption=consumption)
    with pytest.raises(
        ValueError, match="physical consumption verification failed|consumption proof invalid"
    ):
        build_phase1a_report(replace(source, arm_b=bad_b))


def test_settlement_projection_substitution_fails_closed() -> None:
    source = _source()
    settlement = deepcopy(source.arm_b.settlement)
    assert settlement is not None
    settlement["assist_credit"]["packet_hash"] = _h("substituted")
    bad_b = replace(source.arm_b, settlement=settlement)
    with pytest.raises(ValueError, match="settlement packet identity mismatch"):
        build_phase1a_report(replace(source, arm_b=bad_b))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("treatment_run_id", "foreign-run", "settlement treatment-run identity mismatch"),
        ("planner_decision_id", "foreign-planner", "settlement planner-decision identity mismatch"),
        (
            "task_contract_hash",
            _h("foreign-contract"),
            "settlement task-contract identity mismatch",
        ),
    ],
)
def test_settlement_cross_identity_substitution_fails_closed(
    field: str, value: str, reason: str
) -> None:
    source = _source()
    settlement = deepcopy(source.arm_b.settlement)
    assert settlement is not None
    settlement[field] = value
    bad_b = replace(source.arm_b, settlement=settlement)
    with pytest.raises(ValueError, match=reason):
        build_phase1a_report(replace(source, arm_b=bad_b))


def test_online_provider_model_drift_fails_closed() -> None:
    source = _source()
    index = next(
        index
        for index, event in enumerate(source.arm_c.trajectory.events)
        if event.phase == TrajectoryPhase.ONLINE and event.action_kind == ActionKind.PROVIDER_CALL
    )
    bad_c = _replace_event(source.arm_c, index, model="provider/other-model")
    with pytest.raises(ValueError, match="Online provider/model identity drift"):
        build_phase1a_report(replace(source, arm_c=bad_c))


def test_local_provider_model_drift_fails_closed() -> None:
    source = _source()
    bad_c = _replace_event(source.arm_c, 0, model="other-local-model")
    with pytest.raises(ValueError, match="Local provider/model identity drift"):
        build_phase1a_report(replace(source, arm_c=bad_c))


def test_manifest_or_scope_identity_drift_fails_closed() -> None:
    source = _source()
    changed_manifest = _manifest(
        meaningful_improvement_thresholds={
            "ba_min_avoided_actions": 2.0,
            "cb_min_avoided_actions": 1.0,
        }
    )
    with pytest.raises(ValueError, match="frozen-manifest identity drift"):
        build_phase1a_report(replace(source, manifest=changed_manifest))


def test_invalid_run_is_excluded_from_semantic_effect_rows() -> None:
    source = _source()
    invalid_row = replace(source.arm_b.run_row, classification=RunClassification.INTEGRITY_INVALID)
    report = build_phase1a_report(replace(source, arm_b=replace(source.arm_b, run_row=invalid_row)))
    assert report["decision"] == "EVIDENCE_INSUFFICIENT"
    assert report["formal_effect_arms"] == ["A", "C"]
    assert "B" not in report["metrics"]


def test_stored_run_metric_change_cannot_become_metric_truth_and_is_detected_as_source_drift() -> (
    None
):
    source = _source()
    report = build_phase1a_report(source)
    changed_row = replace(
        source.arm_a.run_row, metrics={"stored_total": 123456, "semantic_score": 1.0}
    )
    changed_source = replace(source, arm_a=replace(source.arm_a, run_row=changed_row))
    rebuilt = build_phase1a_report(changed_source)
    assert rebuilt["metrics"] == report["metrics"]
    assert rebuilt["source_binding"]["run_row_sha256"] != report["source_binding"]["run_row_sha256"]
    assert verify_phase1a_report(report, changed_source).ok is False


def test_frozen_threshold_change_cannot_be_tuned_from_report_outcome() -> None:
    source = _source()
    report = build_phase1a_report(source)
    tampered = deepcopy(report)
    tampered["thresholds"]["ba_min_avoided_actions"] = 0.0
    result = verify_phase1a_report(tampered, source)
    assert result.ok is False
    assert "REPORT_PROJECTION_TAMPERED" in result.reasons


@pytest.mark.parametrize(
    ("decision_evidence", "expected"),
    [
        (Phase1ADecisionEvidence(_h("d1"), integrity_sufficient=False), "EVIDENCE_INSUFFICIENT"),
        (Phase1ADecisionEvidence(_h("d2"), invalidity_excessive=True), "EVIDENCE_INSUFFICIENT"),
        (Phase1ADecisionEvidence(_h("d3"), false_success_detected=True), "STOP"),
        (Phase1ADecisionEvidence(_h("d4"), authority_regression_detected=True), "STOP"),
        (Phase1ADecisionEvidence(_h("d5"), safety_regression_detected=True), "STOP"),
        (Phase1ADecisionEvidence(_h("d6"), semantic_regression_detected=True), "REVISE"),
        (Phase1ADecisionEvidence(_h("d7"), quality_preserved=False), "NO_EFFECT"),
        (Phase1ADecisionEvidence(_h("d8")), "CONTINUE"),
    ],
)
def test_frozen_decision_order_is_deterministic(decision_evidence, expected: str) -> None:
    source = _source(decision_evidence=decision_evidence)
    assert build_phase1a_report(source)["decision"] == expected


def test_replay_pass_never_grants_issue29_g5_route_approval_release_runtime_or_causal_authority() -> (
    None
):
    source = _source()
    report = build_phase1a_report(source)
    result = verify_phase1a_report(report, source)
    assert result.ok is True
    forbidden_true = (
        "issue29_complete",
        "g5_authorized",
        "route_authority",
        "approval_authority",
        "release_authority",
        "runtime_integration_proven",
        "causal_benefit_proven",
        "public_claim_allowed",
    )
    assert all(report["claim_boundary"][name] is False for name in forbidden_true)
    assert all(
        result.claim_boundary[name] is False
        for name in forbidden_true
        if name in result.claim_boundary
    )


def test_claim_boundary_tamper_is_rejected_even_if_report_says_pass() -> None:
    source = _source()
    tampered = deepcopy(build_phase1a_report(source))
    tampered["claim_boundary"]["g5_authorized"] = True
    result = verify_phase1a_report(tampered, source)
    assert result.ok is False
    assert "REPORT_PROJECTION_TAMPERED" in result.reasons
    assert "REPORT_CLAIM_BOUNDARY_MISMATCH" in result.reasons
