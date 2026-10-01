"""Comprehensive tests for completion path telemetry contracts and hostile matrix (#440/#493)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.completion_path_telemetry import (
    NOT_OBSERVED,
    AffectedDimensionRebindEvent,
    BlockedLaneGlobalStopEvent,
    CompletionPathTelemetryProjection,
    DuplicateVerificationEvent,
    ExternalOwnerGateType,
    GenuineExternalOwnerGateEvent,
    MilestoneEvent,
    MilestoneType,
    ObservabilityStatus,
    ObservationWindowClosureWitness,
    RebindDimension,
    TelemetryEvent,
    UnnecessaryFullRebindEvent,
    UnnecessaryOwnerInterruptEvent,
    parse_telemetry_event,
    project_completion_path_telemetry,
)

REF_A = "a" * 64
REF_B = "b" * 64
REF_C = "c" * 64
REF_D = "d" * 64
REF_E = "e" * 64
REF_F = "f" * 64
REF_G = "1" * 64
REF_W = "2" * 64
REF_FR = "3" * 64

SHA_HEAD = "1111111111111111111111111111111111111111"
SHA_MERGE = "2222222222222222222222222222222222222222"
SHA_MAIN = "3333333333333333333333333333333333333333"

T0 = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 8, 20, 10, 5, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 8, 20, 10, 10, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 8, 20, 10, 15, 0, tzinfo=timezone.utc)
T4 = datetime(2026, 8, 20, 10, 20, 0, tzinfo=timezone.utc)
T5 = datetime(2026, 8, 20, 10, 25, 0, tzinfo=timezone.utc)
T6 = datetime(2026, 8, 20, 10, 30, 0, tzinfo=timezone.utc)
T7 = datetime(2026, 8, 20, 10, 35, 0, tzinfo=timezone.utc)


def _build_full_milestones(issue_id: str = "nexus-493") -> list[MilestoneEvent]:
    return [
        MilestoneEvent(
            issue_id=issue_id,
            timestamp=T0,
            evidence_ref=REF_A,
            milestone=MilestoneType.READY,
        ),
        MilestoneEvent(
            issue_id=issue_id,
            timestamp=T1,
            evidence_ref=REF_B,
            milestone=MilestoneType.CANDIDATE_READY,
            candidate_id="cand-1",
        ),
        MilestoneEvent(
            issue_id=issue_id,
            timestamp=T2,
            evidence_ref=REF_C,
            milestone=MilestoneType.VERIFIED,
            candidate_id="cand-1",
        ),
        MilestoneEvent(
            issue_id=issue_id,
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=493,
            candidate_head=SHA_HEAD,
        ),
        MilestoneEvent(
            issue_id=issue_id,
            timestamp=T4,
            evidence_ref=REF_E,
            milestone=MilestoneType.MERGED,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=493,
            candidate_head=SHA_HEAD,
            merge_commit_sha=SHA_MERGE,
            current_main_sha=SHA_MAIN,
        ),
        MilestoneEvent(
            issue_id=issue_id,
            timestamp=T5,
            evidence_ref=REF_F,
            milestone=MilestoneType.RECONCILED,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=493,
            candidate_head=SHA_HEAD,
            merge_commit_sha=SHA_MERGE,
            current_main_sha=SHA_MAIN,
        ),
        MilestoneEvent(
            issue_id=issue_id,
            timestamp=T6,
            evidence_ref=REF_G,
            milestone=MilestoneType.CLOSED,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=493,
            candidate_head=SHA_HEAD,
            merge_commit_sha=SHA_MERGE,
            current_main_sha=SHA_MAIN,
        ),
    ]


# ==============================================================================
# Requirement 1: Exact Output Names Matching Issue #440 / #493
# ==============================================================================


def test_projection_output_names_exact() -> None:
    events: list[TelemetryEvent] = _build_full_milestones() + [
        ObservationWindowClosureWitness(
            issue_id="nexus-493",
            timestamp=T7,
            evidence_ref=REF_W,
            closed_at=T7,
        )
    ]
    projection = project_completion_path_telemetry(events)
    dump = projection.to_dict()

    # Exact Issue #440/#493 canonical output names must exist
    assert "owner_interrupt_count" in dump
    assert "unnecessary_full_rebind_count" in dump
    assert "duplicate_verification_count" in dump
    assert "blocked_lane_global_stop_count" in dump

    # Ambiguous / shortened names must not exist
    assert "unnecessary_owner_interrupt" not in dump
    assert "unnecessary_full_rebind" not in dump
    assert "duplicate_verification" not in dump
    assert "blocked_lane_global_stop" not in dump

    assert dump["owner_interrupt_count"] == 0
    assert dump["unnecessary_full_rebind_count"] == 0
    assert dump["duplicate_verification_count"] == 0
    assert dump["blocked_lane_global_stop_count"] == 0


# ==============================================================================
# Requirement 2: Explicit Per-Counter Observability
# ==============================================================================


def test_observability_unclosed_window_zero_counts() -> None:
    # Before closure with no friction events seen -> counters NOT_OBSERVED, observability NOT_OBSERVED
    events: list[TelemetryEvent] = _build_full_milestones()
    projection = project_completion_path_telemetry(events)

    assert projection.observation_window_closed is False
    assert projection.owner_interrupt_count == NOT_OBSERVED
    assert projection.unnecessary_full_rebind_count == NOT_OBSERVED
    assert projection.duplicate_verification_count == NOT_OBSERVED
    assert projection.blocked_lane_global_stop_count == NOT_OBSERVED

    assert projection.owner_interrupt_observability == ObservabilityStatus.NOT_OBSERVED
    assert projection.unnecessary_full_rebind_observability == ObservabilityStatus.NOT_OBSERVED
    assert projection.duplicate_verification_observability == ObservabilityStatus.NOT_OBSERVED
    assert projection.blocked_lane_global_stop_observability == ObservabilityStatus.NOT_OBSERVED

    assert projection.compression_gate_evaluable is False
    assert projection.compression_gate_pass is False


def test_observability_unclosed_window_nonzero_counts() -> None:
    # Before closure with friction events seen -> counters have int, but observability is NOT_OBSERVED
    events: list[TelemetryEvent] = _build_full_milestones() + [
        UnnecessaryOwnerInterruptEvent(
            issue_id="nexus-493",
            timestamp=datetime(2026, 8, 20, 10, 1, 0, tzinfo=timezone.utc),
            evidence_ref=REF_FR,
            reason="Unprompted check-in",
        ),
        DuplicateVerificationEvent(
            issue_id="nexus-493",
            timestamp=datetime(2026, 8, 20, 10, 11, 0, tzinfo=timezone.utc),
            evidence_ref=REF_FR,
            candidate_id="cand-1",
        ),
    ]
    projection = project_completion_path_telemetry(events)

    assert projection.observation_window_closed is False
    # Seen friction events record their observed count
    assert projection.owner_interrupt_count == 1
    assert projection.duplicate_verification_count == 1
    # Unseen friction events remain NOT_OBSERVED before window close
    assert projection.unnecessary_full_rebind_count == NOT_OBSERVED
    assert projection.blocked_lane_global_stop_count == NOT_OBSERVED

    # Per-counter observability remains NOT_OBSERVED before closure regardless of zero/nonzero
    assert projection.owner_interrupt_observability == ObservabilityStatus.NOT_OBSERVED
    assert projection.unnecessary_full_rebind_observability == ObservabilityStatus.NOT_OBSERVED
    assert projection.duplicate_verification_observability == ObservabilityStatus.NOT_OBSERVED
    assert projection.blocked_lane_global_stop_observability == ObservabilityStatus.NOT_OBSERVED


def test_observability_closed_window_distinguishes_zero_and_nonzero() -> None:
    # Once closed, all counters are OBSERVED and numeric integers (0 or N)
    events: list[TelemetryEvent] = _build_full_milestones() + [
        BlockedLaneGlobalStopEvent(
            issue_id="nexus-493",
            timestamp=datetime(2026, 8, 20, 10, 2, 0, tzinfo=timezone.utc),
            evidence_ref=REF_FR,
            lane_id="lane-1",
            reason="Blocked on upstream ref",
        ),
        ObservationWindowClosureWitness(
            issue_id="nexus-493",
            timestamp=T7,
            evidence_ref=REF_W,
            closed_at=T7,
        ),
    ]
    projection = project_completion_path_telemetry(events)

    assert projection.observation_window_closed is True
    assert projection.owner_interrupt_count == 0
    assert projection.unnecessary_full_rebind_count == 0
    assert projection.duplicate_verification_count == 0
    assert projection.blocked_lane_global_stop_count == 1

    assert projection.owner_interrupt_observability == ObservabilityStatus.OBSERVED
    assert projection.unnecessary_full_rebind_observability == ObservabilityStatus.OBSERVED
    assert projection.duplicate_verification_observability == ObservabilityStatus.OBSERVED
    assert projection.blocked_lane_global_stop_observability == ObservabilityStatus.OBSERVED

    assert projection.compression_gate_evaluable is True
    assert projection.compression_gate_pass is False  # blocked_lane_global_stop == 1


# ==============================================================================
# Requirement 3: Typed Discriminator per Event
# ==============================================================================


def test_typed_discriminators_serialization_and_parsing() -> None:
    ev_m = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T0,
        evidence_ref=REF_A,
        milestone=MilestoneType.READY,
    )
    assert ev_m.event_type == "MILESTONE"
    assert ev_m.milestone == MilestoneType.READY

    ev_oi = UnnecessaryOwnerInterruptEvent(
        issue_id="nexus-493",
        timestamp=T1,
        evidence_ref=REF_B,
        reason="interrupt",
    )
    assert ev_oi.event_type == "UNNECESSARY_OWNER_INTERRUPT"

    ev_rb = UnnecessaryFullRebindEvent(
        issue_id="nexus-493",
        timestamp=T2,
        evidence_ref=REF_C,
        candidate_id="cand-1",
        reason="rebind",
    )
    assert ev_rb.event_type == "UNNECESSARY_FULL_REBIND"

    ev_dv = DuplicateVerificationEvent(
        issue_id="nexus-493",
        timestamp=T3,
        evidence_ref=REF_D,
        candidate_id="cand-1",
    )
    assert ev_dv.event_type == "DUPLICATE_VERIFICATION"

    ev_gs = BlockedLaneGlobalStopEvent(
        issue_id="nexus-493",
        timestamp=T4,
        evidence_ref=REF_E,
        lane_id="lane-1",
    )
    assert ev_gs.event_type == "BLOCKED_LANE_GLOBAL_STOP"

    ev_og = GenuineExternalOwnerGateEvent(
        issue_id="nexus-493",
        timestamp=T5,
        evidence_ref=REF_F,
        gate_type=ExternalOwnerGateType.PLATFORM,
    )
    assert ev_og.event_type == "GENUINE_EXTERNAL_OWNER_GATE"

    ev_ar = AffectedDimensionRebindEvent(
        issue_id="nexus-493",
        timestamp=T6,
        evidence_ref=REF_G,
        candidate_id="cand-1",
        dimension=RebindDimension.TEST_IMPACT,
    )
    assert ev_ar.event_type == "AFFECTED_DIMENSION_REBIND"

    ev_cl = ObservationWindowClosureWitness(
        issue_id="nexus-493",
        timestamp=T7,
        evidence_ref=REF_W,
    )
    assert ev_cl.event_type == "OBSERVATION_WINDOW_CLOSURE"

    # Test polymorphic parsing from raw serialized dicts
    all_events = [ev_m, ev_oi, ev_rb, ev_dv, ev_gs, ev_og, ev_ar, ev_cl]
    for ev in all_events:
        dumped = ev.model_dump(mode="json")
        assert "event_type" in dumped
        reparsed = parse_telemetry_event(dumped)
        assert type(reparsed) is type(ev)
        assert reparsed == ev


# ==============================================================================
# Requirement 4: ObservationWindowClosureWitness Canonical Closure Instant
# ==============================================================================


def test_window_closure_canonical_instant() -> None:
    # 1. Default closed_at matches timestamp
    w1 = ObservationWindowClosureWitness(
        issue_id="nexus-493",
        timestamp=T7,
        evidence_ref=REF_W,
    )
    assert w1.closed_at == T7

    # 2. Explicit matching closed_at is valid
    w2 = ObservationWindowClosureWitness(
        issue_id="nexus-493",
        timestamp=T7,
        evidence_ref=REF_W,
        closed_at=T7,
    )
    assert w2.closed_at == T7

    # 3. Mismatched closed_at fails closed
    with pytest.raises((ValueError, ValidationError), match="CLOSED_AT_TIMESTAMP_MISMATCH"):
        ObservationWindowClosureWitness(
            issue_id="nexus-493",
            timestamp=T7,
            evidence_ref=REF_W,
            closed_at=T6,
        )


def test_post_window_event_fails_closed() -> None:
    # Event timestamp strictly after window closure must fail closed
    events: list[TelemetryEvent] = _build_full_milestones() + [
        ObservationWindowClosureWitness(
            issue_id="nexus-493",
            timestamp=T6,
            evidence_ref=REF_W,
            closed_at=T6,
        ),
        UnnecessaryOwnerInterruptEvent(
            issue_id="nexus-493",
            timestamp=T7,  # T7 > T6
            evidence_ref=REF_FR,
        ),
    ]
    with pytest.raises(ValueError, match="POST_WINDOW_EVENT"):
        project_completion_path_telemetry(events)

    # Even if closure witness is passed after the post-window event in the list
    events_reversed: list[TelemetryEvent] = _build_full_milestones() + [
        UnnecessaryOwnerInterruptEvent(
            issue_id="nexus-493",
            timestamp=T7,
            evidence_ref=REF_FR,
        ),
        ObservationWindowClosureWitness(
            issue_id="nexus-493",
            timestamp=T6,
            evidence_ref=REF_W,
            closed_at=T6,
        ),
    ]
    with pytest.raises(ValueError, match="POST_WINDOW_EVENT"):
        project_completion_path_telemetry(events_reversed)


# ==============================================================================
# Requirement 5: Exact Idempotence & Deduplication Semantics
# ==============================================================================


def test_exact_duplicate_deduplication() -> None:
    base_milestones = _build_full_milestones()
    closure = ObservationWindowClosureWitness(
        issue_id="nexus-493",
        timestamp=T7,
        evidence_ref=REF_W,
    )
    fric = UnnecessaryOwnerInterruptEvent(
        issue_id="nexus-493",
        timestamp=datetime(2026, 8, 20, 10, 1, 0, tzinfo=timezone.utc),
        evidence_ref=REF_FR,
        reason="interrupt",
    )

    # Duplicate all events exactly
    duplicated_events = (
        base_milestones + [base_milestones[0], base_milestones[3]] + [fric, fric, closure, closure]
    )
    projection = project_completion_path_telemetry(duplicated_events)

    # Deduplication ensures exact duplicate friction event only counted once
    assert projection.owner_interrupt_count == 1
    assert projection.observation_window_closed is True
    assert projection.closed_at == T6


def test_conflicting_duplicate_milestone_fails_closed() -> None:
    base_milestones = _build_full_milestones()
    # Conflicting READY milestone with different timestamp
    conflicting_ready = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=datetime(2026, 8, 20, 10, 1, 0, tzinfo=timezone.utc),
        evidence_ref=REF_A,
        milestone=MilestoneType.READY,
    )
    with pytest.raises(
        ValueError,
        match="CONFLICTING_(DUPLICATE_MILESTONE|DUPLICATE_EVIDENCE_REF)",
    ):
        project_completion_path_telemetry(base_milestones + [conflicting_ready])


def test_conflicting_duplicate_window_closure_fails_closed() -> None:
    base_milestones = _build_full_milestones()
    w1 = ObservationWindowClosureWitness(
        issue_id="nexus-493",
        timestamp=T7,
        evidence_ref=REF_W,
    )
    w2 = ObservationWindowClosureWitness(
        issue_id="nexus-493",
        timestamp=datetime(2026, 8, 20, 10, 36, 0, tzinfo=timezone.utc),
        evidence_ref=REF_W,
    )
    with pytest.raises(
        ValueError,
        match="CONFLICTING_(WINDOW_CLOSURE|DUPLICATE_EVIDENCE_REF)",
    ):
        project_completion_path_telemetry(base_milestones + [w1, w2])


# ==============================================================================
# Hostile Matrix (#493) & Identity Invariants
# ==============================================================================


def test_empty_events_fails_closed() -> None:
    with pytest.raises(ValueError, match="NO_EVENTS_PROVIDED"):
        project_completion_path_telemetry([])


def test_issue_id_conflict_fails_closed() -> None:
    ev1 = MilestoneEvent(
        issue_id="issue-1",
        timestamp=T0,
        evidence_ref=REF_A,
        milestone=MilestoneType.READY,
    )
    ev2 = MilestoneEvent(
        issue_id="issue-2",
        timestamp=T1,
        evidence_ref=REF_B,
        milestone=MilestoneType.CANDIDATE_READY,
        candidate_id="cand-1",
    )
    with pytest.raises(ValueError, match="ISSUE_ID_CONFLICT"):
        project_completion_path_telemetry([ev1, ev2])


def test_candidate_id_conflict_fails_closed() -> None:
    ev1 = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T1,
        evidence_ref=REF_B,
        milestone=MilestoneType.CANDIDATE_READY,
        candidate_id="cand-1",
    )
    ev2 = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T2,
        evidence_ref=REF_C,
        milestone=MilestoneType.VERIFIED,
        candidate_id="cand-2",  # conflict!
    )
    with pytest.raises(ValueError, match="CANDIDATE_ID_CONFLICT"):
        project_completion_path_telemetry([ev1, ev2])


def test_repository_conflict_fails_closed() -> None:
    ev1 = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T3,
        evidence_ref=REF_D,
        milestone=MilestoneType.PR_READY,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=493,
        candidate_head=SHA_HEAD,
    )
    ev2 = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T4,
        evidence_ref=REF_E,
        milestone=MilestoneType.MERGED,
        candidate_id="cand-1",
        repository="James3014/Other-repo",  # conflict!
        pr_number=493,
        candidate_head=SHA_HEAD,
        merge_commit_sha=SHA_MERGE,
        current_main_sha=SHA_MAIN,
    )
    with pytest.raises(ValueError, match="REPOSITORY_CONFLICT"):
        project_completion_path_telemetry([ev1, ev2])


def test_pr_number_conflict_fails_closed() -> None:
    ev1 = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T3,
        evidence_ref=REF_D,
        milestone=MilestoneType.PR_READY,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=493,
        candidate_head=SHA_HEAD,
    )
    ev2 = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T4,
        evidence_ref=REF_E,
        milestone=MilestoneType.MERGED,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=494,  # conflict!
        candidate_head=SHA_HEAD,
        merge_commit_sha=SHA_MERGE,
        current_main_sha=SHA_MAIN,
    )
    with pytest.raises(ValueError, match="PR_NUMBER_CONFLICT"):
        project_completion_path_telemetry([ev1, ev2])


def test_candidate_head_conflict_fails_closed() -> None:
    ev1 = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T3,
        evidence_ref=REF_D,
        milestone=MilestoneType.PR_READY,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=493,
        candidate_head=SHA_HEAD,
    )
    ev2 = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T4,
        evidence_ref=REF_E,
        milestone=MilestoneType.MERGED,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=493,
        candidate_head="4444444444444444444444444444444444444444",  # conflict!
        merge_commit_sha=SHA_MERGE,
        current_main_sha=SHA_MAIN,
    )
    with pytest.raises(ValueError, match="CANDIDATE_HEAD_CONFLICT"):
        project_completion_path_telemetry([ev1, ev2])


def test_milestone_order_regression_fails_closed() -> None:
    # MERGED at T1 before CANDIDATE_READY at T2
    ev_ready = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T0,
        evidence_ref=REF_A,
        milestone=MilestoneType.READY,
    )
    ev_cand = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T2,
        evidence_ref=REF_B,
        milestone=MilestoneType.CANDIDATE_READY,
        candidate_id="cand-1",
    )
    ev_merged = MilestoneEvent(
        issue_id="nexus-493",
        timestamp=T1,  # T1 < T2 => regression!
        evidence_ref=REF_E,
        milestone=MilestoneType.MERGED,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=493,
        candidate_head=SHA_HEAD,
        merge_commit_sha=SHA_MERGE,
        current_main_sha=SHA_MAIN,
    )
    with pytest.raises(ValueError, match="MILESTONE_ORDER_REGRESSION"):
        project_completion_path_telemetry([ev_ready, ev_cand, ev_merged])


def test_stage_binding_validation_errors() -> None:
    # 1. CANDIDATE_READY without candidate_id
    with pytest.raises((ValueError, ValidationError)):
        MilestoneEvent(
            issue_id="nexus-493",
            timestamp=T1,
            evidence_ref=REF_B,
            milestone=MilestoneType.CANDIDATE_READY,
        )

    # 2. PR_READY without repo/pr/head
    with pytest.raises((ValueError, ValidationError)):
        MilestoneEvent(
            issue_id="nexus-493",
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
        )

    # 3. MERGED without merge_commit_sha / current_main_sha
    with pytest.raises((ValueError, ValidationError)):
        MilestoneEvent(
            issue_id="nexus-493",
            timestamp=T4,
            evidence_ref=REF_E,
            milestone=MilestoneType.MERGED,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=493,
            candidate_head=SHA_HEAD,
        )


def test_malformed_evidence_ref_and_git_sha() -> None:
    # Malformed evidence ref
    with pytest.raises((ValueError, ValidationError), match="MALFORMED_EVIDENCE_REF"):
        MilestoneEvent(
            issue_id="nexus-493",
            timestamp=T0,
            evidence_ref="invalid-ref",
            milestone=MilestoneType.READY,
        )

    # Malformed git SHA (not 40 hex chars)
    with pytest.raises((ValueError, ValidationError), match="MALFORMED_CANDIDATE_HEAD"):
        MilestoneEvent(
            issue_id="nexus-493",
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=493,
            candidate_head="short-sha",
        )


def test_non_friction_events_do_not_block_compression_gate() -> None:
    events: list[TelemetryEvent] = _build_full_milestones() + [
        GenuineExternalOwnerGateEvent(
            issue_id="nexus-493",
            timestamp=datetime(2026, 8, 20, 10, 1, 0, tzinfo=timezone.utc),
            evidence_ref=REF_FR,
            gate_type=ExternalOwnerGateType.OAUTH,
            reason="External platform authorization required",
        ),
        AffectedDimensionRebindEvent(
            issue_id="nexus-493",
            timestamp=datetime(2026, 8, 20, 10, 2, 0, tzinfo=timezone.utc),
            evidence_ref=REF_FR,
            candidate_id="cand-1",
            dimension=RebindDimension.TRANSPORT_DRIFT,
            reason="Affected transport dimension changed",
        ),
        ObservationWindowClosureWitness(
            issue_id="nexus-493",
            timestamp=T7,
            evidence_ref=REF_W,
            closed_at=T7,
        ),
    ]
    projection = project_completion_path_telemetry(events)

    assert projection.genuine_external_owner_gates_observed == 1
    assert projection.affected_dimension_rebinds_observed == 1

    assert projection.owner_interrupt_count == 0
    assert projection.unnecessary_full_rebind_count == 0
    assert projection.duplicate_verification_count == 0
    assert projection.blocked_lane_global_stop_count == 0

    assert projection.compression_gate_evaluable is True
    assert projection.compression_gate_pass is True


def test_missing_milestones_are_explicitly_not_observed() -> None:
    projection = project_completion_path_telemetry([
        MilestoneEvent(
            issue_id="nexus-493",
            timestamp=T0,
            evidence_ref=REF_A,
            milestone=MilestoneType.READY,
        )
    ])

    assert projection.ready_at == T0
    assert projection.candidate_ready_at == NOT_OBSERVED
    assert projection.verified_at == NOT_OBSERVED
    assert projection.pr_ready_at == NOT_OBSERVED
    assert projection.merged_at == NOT_OBSERVED
    assert projection.reconciled_at == NOT_OBSERVED
    assert projection.closed_at == NOT_OBSERVED
    assert projection.compression_gate_evaluable is False
    assert projection.compression_gate_pass is False


def test_external_owner_gate_is_closed_enum_not_free_text_escape_hatch() -> None:
    with pytest.raises((ValueError, ValidationError)):
        GenuineExternalOwnerGateEvent(
            issue_id="nexus-493",
            timestamp=T1,
            evidence_ref=REF_A,
            gate_type="SECURITY_REVIEW",  # type: ignore[arg-type]
        )

    with pytest.raises((ValueError, ValidationError)):
        parse_telemetry_event({
            "event_type": "OWNER_INTERRUPT",
            "issue_id": "nexus-493",
            "timestamp": T1.isoformat(),
            "evidence_ref": REF_A,
        })


def test_affected_rebind_only_accepts_proven_affected_dimensions() -> None:
    with pytest.raises((ValueError, ValidationError)):
        AffectedDimensionRebindEvent(
            issue_id="nexus-493",
            timestamp=T1,
            evidence_ref=REF_A,
            candidate_id="cand-1",
            dimension="IRRELEVANT_MAIN_MOVEMENT",  # type: ignore[arg-type]
        )
    with pytest.raises((ValueError, ValidationError)):
        AffectedDimensionRebindEvent(
            issue_id="nexus-493",
            timestamp=T1,
            evidence_ref=REF_A,
            candidate_id="cand-1",
            dimension="IMPACT_UNKNOWN",  # type: ignore[arg-type]
        )


def test_rebind_and_duplicate_verification_require_candidate_binding() -> None:
    with pytest.raises((ValueError, ValidationError)):
        UnnecessaryFullRebindEvent(
            issue_id="nexus-493",
            timestamp=T1,
            evidence_ref=REF_A,
            candidate_id="   ",
        )
    with pytest.raises((ValueError, ValidationError)):
        DuplicateVerificationEvent(
            issue_id="nexus-493",
            timestamp=T1,
            evidence_ref=REF_A,
            candidate_id="   ",
        )
    with pytest.raises((ValueError, ValidationError)):
        AffectedDimensionRebindEvent(
            issue_id="nexus-493",
            timestamp=T1,
            evidence_ref=REF_A,
            candidate_id="   ",
            dimension=RebindDimension.TEST_IMPACT,
        )


def test_same_typed_evidence_ref_with_conflicting_payload_fails_closed() -> None:
    first = UnnecessaryOwnerInterruptEvent(
        issue_id="nexus-493",
        timestamp=T1,
        evidence_ref=REF_A,
        reason="first",
    )
    conflicting = UnnecessaryOwnerInterruptEvent(
        issue_id="nexus-493",
        timestamp=T2,
        evidence_ref=REF_A,
        reason="different payload for same evidence binding",
    )
    with pytest.raises(ValueError, match="CONFLICTING_DUPLICATE_EVIDENCE_REF"):
        project_completion_path_telemetry([first, conflicting])


def test_blocked_lane_event_requires_lane_identity() -> None:
    with pytest.raises((ValueError, ValidationError), match="LANE_ID_REQUIRED"):
        BlockedLaneGlobalStopEvent(
            issue_id="nexus-493",
            timestamp=T1,
            evidence_ref=REF_A,
            lane_id="   ",
        )


def test_projection_cannot_be_directly_fabricated_as_gate_pass() -> None:
    with pytest.raises(
        (ValueError, ValidationError),
        match="COMPRESSION_GATE_(EVALUABLE|PASS)_INCONSISTENT",
    ):
        CompletionPathTelemetryProjection(
            issue_id="nexus-493",
            compression_gate_evaluable=True,
            compression_gate_pass=True,
        )


def test_closed_projection_requires_window_witness_and_observed_counters() -> None:
    with pytest.raises(
        (ValueError, ValidationError),
        match="OBSERVATION_WINDOW_WITNESS_REQUIRED",
    ):
        CompletionPathTelemetryProjection(
            issue_id="nexus-493",
            observation_window_closed=True,
        )


def test_mutation_authorized_invariant() -> None:
    # Construction with mutation_authorized=True must be forbidden
    with pytest.raises((ValueError, ValidationError), match="MUTATION_AUTHORIZATION_FORBIDDEN"):
        CompletionPathTelemetryProjection(
            issue_id="nexus-493",
            mutation_authorized=True,  # type: ignore[arg-type]
        )


def test_projection_canonical_hash_stability() -> None:
    events: list[TelemetryEvent] = _build_full_milestones() + [
        ObservationWindowClosureWitness(
            issue_id="nexus-493",
            timestamp=T7,
            evidence_ref=REF_W,
            closed_at=T7,
        )
    ]
    proj1 = project_completion_path_telemetry(events)
    proj2 = project_completion_path_telemetry(events)

    h1 = proj1.canonical_hash()
    h2 = proj2.canonical_hash()
    assert h1 == h2
    assert len(h1) == 64


# ==============================================================================
# Hostile Matrix: Source Candidate vs Integration Subject Separations (#599 Gate A)
# ==============================================================================

SHA_INT_1 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SHA_INT_2 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
SHA_BASE_1 = "cccccccccccccccccccccccccccccccccccccccc"
SHA_BASE_2 = "dddddddddddddddddddddddddddddddddddddddd"


def test_candidate_head_stable_with_distinct_integration_head_and_generation():
    events: list[TelemetryEvent] = [
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T0,
            evidence_ref=REF_A,
            milestone=MilestoneType.READY,
        ),
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T1,
            evidence_ref=REF_B,
            milestone=MilestoneType.CANDIDATE_READY,
            candidate_id="cand-1",
        ),
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T2,
            evidence_ref=REF_C,
            milestone=MilestoneType.VERIFIED,
            candidate_id="cand-1",
        ),
        # PR_READY with source candidate_head SHA_HEAD and distinct integration_head SHA_INT_1 at gen 1
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_head=SHA_INT_1,
            integration_generation=1,
            integration_base_sha=SHA_BASE_1,
        ),
        # Rebind due to test impact drift -> advances to generation 2 on SHA_INT_2
        AffectedDimensionRebindEvent(
            issue_id="nexus-599",
            timestamp=datetime(2026, 8, 20, 10, 18, 0, tzinfo=timezone.utc),
            evidence_ref=REF_FR,
            candidate_id="cand-1",
            dimension=RebindDimension.TEST_IMPACT,
            integration_head=SHA_INT_2,
            integration_generation=2,
            integration_base_sha=SHA_BASE_2,
        ),
        # MERGED with source candidate_head unchanged, latest integration_head SHA_INT_2 at gen 2
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T4,
            evidence_ref=REF_E,
            milestone=MilestoneType.MERGED,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_head=SHA_INT_2,
            integration_generation=2,
            integration_base_sha=SHA_BASE_2,
            merge_commit_sha=SHA_MERGE,
            current_main_sha=SHA_MAIN,
        ),
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T5,
            evidence_ref=REF_F,
            milestone=MilestoneType.RECONCILED,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_head=SHA_INT_2,
            integration_generation=2,
            integration_base_sha=SHA_BASE_2,
            merge_commit_sha=SHA_MERGE,
            current_main_sha=SHA_MAIN,
        ),
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T6,
            evidence_ref=REF_G,
            milestone=MilestoneType.CLOSED,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_head=SHA_INT_2,
            integration_generation=2,
            integration_base_sha=SHA_BASE_2,
            merge_commit_sha=SHA_MERGE,
            current_main_sha=SHA_MAIN,
        ),
        ObservationWindowClosureWitness(
            issue_id="nexus-599",
            timestamp=T7,
            evidence_ref=REF_W,
            closed_at=T7,
        ),
    ]
    projection = project_completion_path_telemetry(events)
    assert projection.candidate_head == SHA_HEAD
    assert projection.integration_head == SHA_INT_2
    assert projection.integration_generation == 2
    assert projection.integration_base_sha == SHA_BASE_2
    assert projection.compression_gate_evaluable is True
    assert projection.compression_gate_pass is True


def test_integration_generation_regression_fails_closed():
    # Generation 2 followed by Generation 1 must fail
    ev1 = MilestoneEvent(
        issue_id="nexus-599",
        timestamp=T3,
        evidence_ref=REF_D,
        milestone=MilestoneType.PR_READY,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=599,
        candidate_head=SHA_HEAD,
        integration_head=SHA_INT_2,
        integration_generation=2,
        integration_base_sha=SHA_BASE_2,
    )
    ev2 = MilestoneEvent(
        issue_id="nexus-599",
        timestamp=T4,
        evidence_ref=REF_E,
        milestone=MilestoneType.MERGED,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=599,
        candidate_head=SHA_HEAD,
        integration_head=SHA_INT_1,
        integration_generation=1,  # Regression!
        integration_base_sha=SHA_BASE_1,
        merge_commit_sha=SHA_MERGE,
        current_main_sha=SHA_MAIN,
    )
    with pytest.raises(ValueError, match="INTEGRATION_GENERATION_REGRESSION"):
        project_completion_path_telemetry([ev1, ev2])


def test_integration_head_changed_without_generation_increment_fails_closed():
    ev1 = MilestoneEvent(
        issue_id="nexus-599",
        timestamp=T3,
        evidence_ref=REF_D,
        milestone=MilestoneType.PR_READY,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=599,
        candidate_head=SHA_HEAD,
        integration_head=SHA_INT_1,
        integration_generation=1,
        integration_base_sha=SHA_BASE_1,
    )
    # Event 2 has changed integration head with same generation (1)
    ev2 = MilestoneEvent(
        issue_id="nexus-599",
        timestamp=T4,
        evidence_ref=REF_E,
        milestone=MilestoneType.MERGED,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=599,
        candidate_head=SHA_HEAD,
        integration_head=SHA_INT_2,  # Changed head
        integration_generation=1,  # But generation didn't increment!
        integration_base_sha=SHA_BASE_1,
        merge_commit_sha=SHA_MERGE,
        current_main_sha=SHA_MAIN,
    )
    with pytest.raises(ValueError, match="INTEGRATION_HEAD_CHANGED_WITHOUT_GENERATION_INCREMENT"):
        project_completion_path_telemetry([ev1, ev2])


def test_integration_base_changed_without_generation_increment_fails_closed():
    ev1 = MilestoneEvent(
        issue_id="nexus-599",
        timestamp=T3,
        evidence_ref=REF_D,
        milestone=MilestoneType.PR_READY,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=599,
        candidate_head=SHA_HEAD,
        integration_head=SHA_INT_1,
        integration_generation=1,
        integration_base_sha=SHA_BASE_1,
    )
    ev2 = MilestoneEvent(
        issue_id="nexus-599",
        timestamp=T4,
        evidence_ref=REF_E,
        milestone=MilestoneType.MERGED,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=599,
        candidate_head=SHA_HEAD,
        integration_head=SHA_INT_1,
        integration_generation=1,  # Same generation
        integration_base_sha=SHA_BASE_2,  # Changed base
        merge_commit_sha=SHA_MERGE,
        current_main_sha=SHA_MAIN,
    )
    with pytest.raises(ValueError, match="INTEGRATION_BASE_CHANGED_WITHOUT_GENERATION_INCREMENT"):
        project_completion_path_telemetry([ev1, ev2])


def test_partial_integration_subject_tuples_fail_closed():
    # Head without generation / base
    with pytest.raises(ValidationError, match="PARTIAL_INTEGRATION_SUBJECT_FORBIDDEN"):
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_head=SHA_INT_1,
        )

    # Generation without head / base
    with pytest.raises(ValidationError, match="PARTIAL_INTEGRATION_SUBJECT_FORBIDDEN"):
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_generation=1,
        )

    # Base without head / generation
    with pytest.raises(ValidationError, match="PARTIAL_INTEGRATION_SUBJECT_FORBIDDEN"):
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_base_sha=SHA_BASE_1,
        )

    # Partial rebind event
    with pytest.raises(ValidationError, match="PARTIAL_INTEGRATION_SUBJECT_FORBIDDEN"):
        AffectedDimensionRebindEvent(
            issue_id="nexus-599",
            timestamp=datetime(2026, 8, 20, 10, 18, 0, tzinfo=timezone.utc),
            evidence_ref=REF_FR,
            candidate_id="cand-1",
            dimension=RebindDimension.TEST_IMPACT,
            integration_generation=2,
        )


def test_substituting_integration_head_for_source_candidate_head_fails_closed():
    # Attempting to change candidate_head from SHA_HEAD to SHA_INT_1 across milestones fails closed
    ev1 = MilestoneEvent(
        issue_id="nexus-599",
        timestamp=T3,
        evidence_ref=REF_D,
        milestone=MilestoneType.PR_READY,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=599,
        candidate_head=SHA_HEAD,
    )
    ev2 = MilestoneEvent(
        issue_id="nexus-599",
        timestamp=T4,
        evidence_ref=REF_E,
        milestone=MilestoneType.MERGED,
        candidate_id="cand-1",
        repository="James3014/Nexus-new",
        pr_number=599,
        candidate_head=SHA_INT_1,  # Substituted integration head as candidate_head!
        merge_commit_sha=SHA_MERGE,
        current_main_sha=SHA_MAIN,
    )
    with pytest.raises(ValueError, match="CANDIDATE_HEAD_CONFLICT"):
        project_completion_path_telemetry([ev1, ev2])


def test_malformed_integration_shas_fail_closed_in_telemetry():
    with pytest.raises(ValidationError, match="MALFORMED_INTEGRATION_HEAD"):
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_head="not-a-sha",
            integration_generation=1,
            integration_base_sha=SHA_BASE_1,
        )
    with pytest.raises(ValidationError, match="MALFORMED_INTEGRATION_BASE_SHA"):
        MilestoneEvent(
            issue_id="nexus-599",
            timestamp=T3,
            evidence_ref=REF_D,
            milestone=MilestoneType.PR_READY,
            candidate_id="cand-1",
            repository="James3014/Nexus-new",
            pr_number=599,
            candidate_head=SHA_HEAD,
            integration_head=SHA_INT_1,
            integration_generation=1,
            integration_base_sha="short",
        )
