import pytest

from nexus.core.task_continuity import ContinuityEvent, project, resume


def event(sequence, kind, previous="", **kwargs):
    return ContinuityEvent(
        task_id="task-1",
        attempt_id="attempt-1",
        sequence=sequence,
        event_type=kind,
        summary=kwargs.pop("summary", kind),
        previous_hash=previous,
        source_revision="src-a",
        contract_revision="contract-a",
        **kwargs,
    )


def test_projection_preserves_rejected_strategy_and_next_action():
    first = event(1, "PLAN_FORMED", next_action="try B", claim_ceiling="evidence only")
    second = event(
        2,
        "ATTEMPT_REJECTED",
        first.event_hash,
        summary="A failed",
        do_not_repeat=("A",),
        evidence_refs=("ev-1",),
        next_action="try B",
        claim_ceiling="evidence only",
    )
    snapshot = project([first, second])
    assert snapshot.rejected_strategies == ("A",)
    assert snapshot.evidence_refs == ("ev-1",)
    assert (
        resume(
            snapshot,
            [],
            task_id="task-1",
            attempt_id="attempt-1",
            source_revision="src-a",
            contract_revision="contract-a",
        ).next_action
        == "try B"
    )


def test_snapshot_tail_matches_projection():
    first = event(1, "PLAN_FORMED", next_action="try A", claim_ceiling="bounded")
    second = event(
        2,
        "ATTEMPT_REJECTED",
        first.event_hash,
        summary="A failed",
        do_not_repeat=("A",),
        next_action="try B",
        claim_ceiling="bounded",
    )
    third = event(
        3,
        "OBSERVATION_RECORDED",
        second.event_hash,
        observation="B observed",
        next_action="finish",
        claim_ceiling="bounded",
    )
    assert resume(
        project([first, second]),
        [third],
        task_id="task-1",
        attempt_id="attempt-1",
        source_revision="src-a",
        contract_revision="contract-a",
    ).snapshot == project([first, second, third])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"task_id": "other"},
        {"attempt_id": "other"},
    ],
)
def test_resume_fails_closed_on_identity_or_hash(kwargs):
    first = event(1, "PLAN_FORMED", next_action="try A", claim_ceiling="bounded")
    snapshot = project([first])
    with pytest.raises(ValueError):
        resume(
            snapshot,
            [],
            task_id=kwargs.get("task_id", "task-1"),
            attempt_id=kwargs.get("attempt_id", "attempt-1"),
            source_revision="src-a",
            contract_revision="contract-a",
            snapshot_hash="tampered",
        )


def test_sequence_gap_and_tamper_fail_closed():
    first = event(1, "PLAN_FORMED", next_action="try A", claim_ceiling="bounded")
    with pytest.raises(ValueError, match="sequence gap"):
        project([first, event(3, "OBSERVATION_RECORDED", first.event_hash, observation="x")])
    with pytest.raises(ValueError, match="tail"):
        resume(
            project([first]),
            [event(3, "OBSERVATION_RECORDED", first.event_hash, observation="x")],
            task_id="task-1",
            attempt_id="attempt-1",
            source_revision="src-a",
            contract_revision="contract-a",
        )
