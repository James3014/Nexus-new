from __future__ import annotations

import pytest

from nexus.research.epistemic_benchmark.phase1a_contracts import Phase1AArm
from nexus.research.epistemic_benchmark.phase1a_measurement import (
    ActionEvent,
    ActionKind,
    EvidenceObservation,
    EvidenceProducerPhase,
    EvidenceRef,
    EpistemicType,
    FrozenTargetOracle,
    TrajectoryPhase,
    ValidationState,
    build_admissible_observation_set,
    compute_phase1a_metrics,
    compute_phase1a_recomputation,
    validate_trajectory,
)


def make_observation(
    *,
    arm: Phase1AArm = Phase1AArm.B,
    producer_phase: EvidenceProducerPhase = EvidenceProducerPhase.DETERMINISTIC,
    epistemic_type: EpistemicType = EpistemicType.OBSERVED,
    validation_state: ValidationState = ValidationState.ADMISSIBLE,
    claim: str = "bounded observation",
    task_id: str = "task-166",
    evidence_refs: tuple[EvidenceRef, ...] | None = None,
    derivation_lineage: tuple[str, ...] | None = None,
    validator_evidence_refs: tuple[str, ...] | None = None,
    independent: bool = True,
    **kwargs,
) -> EvidenceObservation:
    if evidence_refs is None:
        evidence_refs = (EvidenceRef("src-1", "a" * 64, physical=True),)
    if derivation_lineage is None:
        derivation_lineage = (
            ("OBS-parent",)
            if epistemic_type == EpistemicType.INFERRED
            else ()
        )
    if validator_evidence_refs is None:
        validator_evidence_refs = (
            ("VAL-1",)
            if validation_state == ValidationState.ADMISSIBLE
            else ()
        )
    return EvidenceObservation(
        task_id=task_id,
        arm=arm,
        producer_phase=producer_phase,
        epistemic_type=epistemic_type,
        bounded_claim=claim,
        evidence_refs=evidence_refs,
        derivation_lineage=derivation_lineage,
        validation_state=validation_state,
        validator_contract_hash="b" * 64,
        validator_evidence_refs=validator_evidence_refs,
        producer_verifier_independent=independent,
        **kwargs,
    )


def make_event(
    sequence: int,
    *,
    arm: Phase1AArm = Phase1AArm.A,
    phase: TrajectoryPhase = TrajectoryPhase.ONLINE,
    kind: ActionKind = ActionKind.FILE_READ,
    target: str = "file:a.py",
    payload: dict | None = None,
    task_id: str = "task-166",
    experiment_id: str = "exp-1",
    manifest_id: str = "manifest-1",
    run_id: str = "run-1",
    scope_id: str = "scope-1",
    session_id: str = "session-1",
    attempt_id: str = "attempt-1",
    validation_refs: tuple[str, ...] = (),
    retry_count: int = 0,
    started_at_ms: int | None = None,
    duration_ms: int = 10,
    uncached_input_tokens: int = 0,
    fuzzy_signature: str | None = None,
) -> ActionEvent:
    if payload is None:
        payload = {"target": target}
    provider = ""
    model = ""
    if kind == ActionKind.PROVIDER_CALL:
        provider = "online-provider"
        model = "online-model"
    return ActionEvent(
        experiment_id=experiment_id,
        manifest_id=manifest_id,
        run_id=run_id,
        scope_id=scope_id,
        task_id=task_id,
        arm=arm,
        session_id=session_id,
        attempt_id=attempt_id,
        sequence=sequence,
        phase=phase,
        actor_class="ONLINE" if phase == TrajectoryPhase.ONLINE else phase.value,
        normalized_target=target,
        action_kind=kind,
        signature_payload=payload,
        evidence_refs=(),
        provider=provider,
        model=model,
        status="OK",
        retry_count=retry_count,
        started_at_ms=sequence * 10 if started_at_ms is None else started_at_ms,
        duration_ms=duration_ms,
        validation_evidence_refs=validation_refs,
        uncached_input_tokens=uncached_input_tokens,
        fuzzy_signature=fuzzy_signature,
    )


def test_observed_requires_physical_evidence_with_source_hash():
    with pytest.raises(ValueError, match="OBSERVED requires physical evidence"):
        make_observation(evidence_refs=())

    with pytest.raises(ValueError, match="must be a lowercase SHA-256"):
        EvidenceRef("src-bad", "bad", physical=True)

    with pytest.raises(ValueError, match="must be physical"):
        make_observation(
            evidence_refs=(EvidenceRef("src-1", "a" * 64, physical=False),)
        )


def test_inferred_requires_derivation_lineage():
    with pytest.raises(ValueError, match="INFERRED requires derivation lineage"):
        make_observation(
            epistemic_type=EpistemicType.INFERRED,
            derivation_lineage=(),
        )

    inferred = make_observation(epistemic_type=EpistemicType.INFERRED)
    assert inferred.derivation_lineage == ("OBS-parent",)


def test_admissible_requires_validator_evidence_and_independence():
    with pytest.raises(ValueError, match="requires validator evidence"):
        make_observation(validator_evidence_refs=())

    with pytest.raises(ValueError, match="producer/verifier independence"):
        make_observation(independent=False)


def test_observation_authority_claims_fail_closed():
    for field in (
        "claims_proven",
        "claims_final",
        "claims_approval_authority",
        "claims_routing_authority",
        "claims_final_semantic_correctness",
    ):
        with pytest.raises(ValueError, match="cannot claim authority"):
            make_observation(**{field: True})


def test_local_evidence_is_arm_c_only():
    with pytest.raises(ValueError, match="allowed only in Arm C"):
        make_observation(producer_phase=EvidenceProducerPhase.LOCAL)

    local_obs = make_observation(
        arm=Phase1AArm.C,
        producer_phase=EvidenceProducerPhase.LOCAL,
    )
    assert local_obs.arm == Phase1AArm.C


def test_only_admissible_observations_enter_handoff():
    rejected = make_observation(
        validation_state=ValidationState.REJECTED,
        validator_evidence_refs=(),
        independent=False,
    )
    with pytest.raises(ValueError, match="only ADMISSIBLE"):
        build_admissible_observation_set([rejected])

    admissible = make_observation()
    handoff = build_admissible_observation_set([admissible]).provider_safe_handoff()
    assert set(handoff) == {
        "task_id",
        "arm",
        "observation_ids",
        "admissible_observation_set_sha256",
    }
    assert "bounded_claim" not in handoff
    assert "physical_consumption" not in handoff


def test_observation_set_identity_is_order_deterministic_and_substitution_sensitive():
    obs1 = make_observation(claim="claim-1")
    obs2 = make_observation(
        claim="claim-2",
        evidence_refs=(EvidenceRef("src-2", "c" * 64, physical=True),),
    )
    forward = build_admissible_observation_set([obs1, obs2])
    reverse = build_admissible_observation_set([obs2, obs1])
    assert (
        forward.admissible_observation_set_sha256
        == reverse.admissible_observation_set_sha256
    )
    assert forward.observation_ids == reverse.observation_ids

    substituted = build_admissible_observation_set(
        [obs1, make_observation(claim="substituted")]
    )
    assert (
        forward.admissible_observation_set_sha256
        != substituted.admissible_observation_set_sha256
    )


def test_observation_set_rejects_duplicate_and_identity_drift():
    obs = make_observation()
    with pytest.raises(ValueError, match="duplicate observation identity"):
        build_admissible_observation_set([obs, obs])

    other_task = make_observation(task_id="other-task", claim="other")
    with pytest.raises(ValueError, match="task/arm identity drift"):
        build_admissible_observation_set([obs, other_task])


def test_nested_unordered_signature_input_fails_closed():
    with pytest.raises(ValueError, match="unordered or invalid"):
        make_event(
            0,
            payload={"nested": {"tools": {"read", "search"}}},
        )


def test_fuzzy_signature_cannot_be_decision_bearing():
    with pytest.raises(ValueError, match="exploratory-only"):
        make_event(0, fuzzy_signature="similarity:0.93")


def test_trajectory_rejects_duplicate_and_non_monotonic_sequence():
    first = make_event(0)
    duplicate = make_event(0, target="file:b.py")
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_trajectory([first, duplicate])

    later = make_event(2)
    earlier = make_event(1, target="file:c.py")
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_trajectory([later, earlier])


def test_trajectory_rejects_task_arm_and_run_identity_drift():
    first = make_event(0)
    task_drift = make_event(1, task_id="other-task")
    with pytest.raises(ValueError, match="trajectory identity drift"):
        validate_trajectory([first, task_drift])

    arm_drift = make_event(1, arm=Phase1AArm.B)
    with pytest.raises(ValueError, match="trajectory identity drift"):
        validate_trajectory([first, arm_drift])

    run_drift = make_event(1, run_id="other-run")
    with pytest.raises(ValueError, match="trajectory identity drift"):
        validate_trajectory([first, run_drift])


def test_trajectory_hash_is_replay_deterministic():
    events1 = [
        make_event(0, payload={"b": 2, "a": 1}),
        make_event(1, target="file:b.py", payload={"nested": {"z": 9, "a": 1}}),
    ]
    events2 = [
        make_event(0, payload={"a": 1, "b": 2}),
        make_event(1, target="file:b.py", payload={"nested": {"a": 1, "z": 9}}),
    ]
    assert (
        validate_trajectory(events1).trajectory_sha256
        == validate_trajectory(events2).trajectory_sha256
    )


def _build_recomputation_triplet():
    a_events = [
        make_event(0, arm=Phase1AArm.A, target="x", run_id="run-a"),
        make_event(1, arm=Phase1AArm.A, target="x", run_id="run-a"),
        make_event(2, arm=Phase1AArm.A, target="y", run_id="run-a"),
    ]
    b_events = [
        make_event(
            0,
            arm=Phase1AArm.B,
            phase=TrajectoryPhase.DETERMINISTIC_PREWORK,
            target="x",
            run_id="run-b",
            validation_refs=("VAL-x",),
        ),
        make_event(
            1,
            arm=Phase1AArm.B,
            phase=TrajectoryPhase.DETERMINISTIC_PREWORK,
            target="x",
            run_id="run-b",
            validation_refs=("VAL-x",),
        ),
        make_event(
            2,
            arm=Phase1AArm.B,
            phase=TrajectoryPhase.DETERMINISTIC_PREWORK,
            target="x",
            run_id="run-b",
            validation_refs=("VAL-x",),
        ),
        make_event(
            3,
            arm=Phase1AArm.B,
            phase=TrajectoryPhase.DETERMINISTIC_PREWORK,
            target="z-extra",
            run_id="run-b",
            validation_refs=("VAL-z",),
        ),
        make_event(4, arm=Phase1AArm.B, target="x", run_id="run-b"),
        make_event(5, arm=Phase1AArm.B, target="y", run_id="run-b"),
    ]
    c_events = [
        make_event(
            0,
            arm=Phase1AArm.C,
            phase=TrajectoryPhase.LOCAL_EXPLORATION,
            target="x",
            run_id="run-c",
            validation_refs=("VAL-x",),
        ),
        make_event(
            1,
            arm=Phase1AArm.C,
            phase=TrajectoryPhase.LOCAL_EXPLORATION,
            target="y",
            run_id="run-c",
            validation_refs=("VAL-y",),
        ),
        make_event(
            2,
            arm=Phase1AArm.C,
            phase=TrajectoryPhase.LOCAL_EXPLORATION,
            target="y",
            run_id="run-c",
            validation_refs=("VAL-y",),
        ),
        make_event(
            3,
            arm=Phase1AArm.C,
            phase=TrajectoryPhase.LOCAL_EXPLORATION,
            target="z-extra",
            run_id="run-c",
            validation_refs=("VAL-z",),
        ),
        make_event(4, arm=Phase1AArm.C, target="x", run_id="run-c"),
    ]
    return (
        validate_trajectory(a_events),
        validate_trajectory(b_events),
        validate_trajectory(c_events),
    )


def test_recomputation_formulas_use_conservative_multiset_matching():
    arm_a, arm_b, arm_c = _build_recomputation_triplet()
    result = compute_phase1a_recomputation(arm_a, arm_b, arm_c)

    assert result.ba.potential_total == 2
    assert result.ba.recomputed_total == 1
    assert result.ba.avoided_total == 1

    assert result.cb.potential_total == 2
    assert result.cb.recomputed_total == 1
    assert result.cb.avoided_total == 1


def test_extra_prework_absent_from_baseline_gets_zero_credit():
    arm_a, arm_b, arm_c = _build_recomputation_triplet()
    result = compute_phase1a_recomputation(arm_a, arm_b, arm_c)

    ba_extra = next(
        row
        for row in result.ba.per_signature
        if row.baseline_count == 0 and row.validated_prework_count > 0
    )
    assert ba_extra.potential == 0
    assert ba_extra.avoided == 0

    cb_extra = next(
        row
        for row in result.cb.per_signature
        if row.baseline_count == 0 and row.validated_prework_count > 0
    )
    assert cb_extra.potential == 0
    assert cb_extra.avoided == 0


def test_unvalidated_prework_cannot_create_recomputation_credit():
    arm_a = validate_trajectory(
        [make_event(0, arm=Phase1AArm.A, target="x", run_id="run-a")]
    )
    arm_b = validate_trajectory(
        [
            make_event(
                0,
                arm=Phase1AArm.B,
                phase=TrajectoryPhase.DETERMINISTIC_PREWORK,
                target="x",
                run_id="run-b",
                validation_refs=(),
            ),
            make_event(1, arm=Phase1AArm.B, target="x", run_id="run-b"),
        ]
    )
    arm_c = validate_trajectory(
        [make_event(0, arm=Phase1AArm.C, target="x", run_id="run-c")]
    )
    result = compute_phase1a_recomputation(arm_a, arm_b, arm_c)
    assert result.ba.potential_total == 0
    assert result.ba.avoided_total == 0


def test_recomputation_rejects_triplet_measurement_identity_drift():
    arm_a, arm_b, arm_c = _build_recomputation_triplet()
    drifted_b = validate_trajectory(
        [
            make_event(
                0,
                arm=Phase1AArm.B,
                task_id="other-task",
                run_id="run-b2",
            )
        ]
    )
    with pytest.raises(ValueError, match="A/B measurement identity drift"):
        compute_phase1a_recomputation(arm_a, drifted_b, arm_c)


def test_evidence_utilization_requires_exact_physical_consumption_binding():
    obs1 = make_observation(claim="claim-1")
    obs2 = make_observation(
        claim="claim-2",
        evidence_refs=(EvidenceRef("src-2", "c" * 64, physical=True),),
    )
    obs_set = build_admissible_observation_set([obs1, obs2])
    trajectory = validate_trajectory(
        [make_event(0, arm=Phase1AArm.B, run_id="run-b")]
    )

    absent = compute_phase1a_metrics(
        trajectory,
        observation_set=obs_set,
        reverified_observation_ids=(obs1.observation_id,),
        contradictory_observation_ids=(obs2.observation_id,),
    )
    assert absent["evidence_utilization_rate"] == 0.0
    assert absent["evidence_reverification_rate"] == 0.5
    assert absent["contradictory_evidence_rate"] == 0.5

    consumed = compute_phase1a_metrics(
        trajectory,
        observation_set=obs_set,
        consumed_observation_set_sha256=(
            obs_set.admissible_observation_set_sha256
        ),
        physical_consumption_proof_sha256="d" * 64,
    )
    assert consumed["evidence_utilization_rate"] == 1.0

    with pytest.raises(ValueError, match="substitution detected"):
        compute_phase1a_metrics(
            trajectory,
            observation_set=obs_set,
            consumed_observation_set_sha256="0" * 64,
            physical_consumption_proof_sha256="d" * 64,
        )


def test_physical_consumption_proof_without_set_identity_fails_closed():
    obs_set = build_admissible_observation_set([make_observation()])
    trajectory = validate_trajectory(
        [make_event(0, arm=Phase1AArm.B, run_id="run-b")]
    )
    with pytest.raises(ValueError, match="lacks set identity"):
        compute_phase1a_metrics(
            trajectory,
            observation_set=obs_set,
            physical_consumption_proof_sha256="e" * 64,
        )


def test_time_to_first_correct_target_requires_independent_frozen_oracle():
    trajectory = validate_trajectory(
        [
            make_event(0, target="start", started_at_ms=100),
            make_event(1, target="correct-target", started_at_ms=250),
        ]
    )
    without_oracle = compute_phase1a_metrics(trajectory)
    assert without_oracle["time_to_first_correct_target_seconds"] is None

    oracle = FrozenTargetOracle(
        oracle_id="oracle-1",
        oracle_sha256="f" * 64,
        normalized_target="correct-target",
        independent=True,
    )
    with_oracle = compute_phase1a_metrics(
        trajectory,
        frozen_target_oracle=oracle,
    )
    assert with_oracle["time_to_first_correct_target_seconds"] == 0.15

    with pytest.raises(ValueError, match="explicitly independent"):
        FrozenTargetOracle(
            oracle_id="oracle-bad",
            oracle_sha256="f" * 64,
            normalized_target="correct-target",
            independent=False,
        )


def test_required_metric_families_are_deterministically_projected():
    trajectory = validate_trajectory(
        [
            make_event(0, target="read", kind=ActionKind.FILE_READ),
            make_event(1, target="read", kind=ActionKind.FILE_READ),
            make_event(2, target="search", kind=ActionKind.SEARCH),
            make_event(3, target="search", kind=ActionKind.SEARCH),
            make_event(4, target="test", kind=ActionKind.TEST),
            make_event(5, target="test", kind=ActionKind.TEST),
            make_event(
                6,
                target="provider",
                kind=ActionKind.PROVIDER_CALL,
                retry_count=2,
                duration_ms=50,
                uncached_input_tokens=123,
            ),
            make_event(
                7,
                phase=TrajectoryPhase.FINAL_VERIFIER,
                kind=ActionKind.VERIFICATION,
                target="final-verifier",
                duration_ms=200,
            ),
        ]
    )
    metrics = compute_phase1a_metrics(trajectory)
    assert metrics["online_tool_action_count"] == 6
    assert metrics["repeated_file_reads"] == 1
    assert metrics["repeated_searches"] == 1
    assert metrics["repeated_tests"] == 1
    assert metrics["final_verifier_action_count"] == 1
    assert metrics["final_verifier_wall_time_seconds"] == 0.2
    assert metrics["provider_call_count"] == 1
    assert metrics["provider_retry_count"] == 2
    assert metrics["uncached_equivalent_online_input_tokens"] == 123
    assert "weighted_productivity_score" not in metrics
    assert "token_reduction_threshold" not in metrics


def test_g1_phase1a_arm_identity_is_not_reinterpreted():
    assert {arm.value for arm in Phase1AArm} == {
        "PHASE1A_ARM_A",
        "PHASE1A_ARM_B",
        "PHASE1A_ARM_C",
    }
