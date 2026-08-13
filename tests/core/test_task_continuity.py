import pytest

from nexus.core.task_continuity import ContinuityEvent, project, resume


def event(sequence, kind, previous="", **kwargs):
    source_revision = kwargs.pop("source_revision", "src-a")
    contract_revision = kwargs.pop("contract_revision", "contract-a")
    return ContinuityEvent(
        task_id="task-1",
        attempt_id="attempt-1",
        sequence=sequence,
        event_type=kind,
        summary=kwargs.pop("summary", kind),
        previous_hash=previous,
        source_revision=source_revision,
        contract_revision=contract_revision,
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
        unresolved_risks=("risk-1",),
        unknowns=("unknown-1",),
        next_action="try B",
        claim_ceiling="evidence only",
    )
    snapshot = project([first, second])
    assert snapshot.rejected_strategies == ("A",)
    assert snapshot.evidence_refs == ("ev-1",)
    assert snapshot.unresolved_risks == ("risk-1",)
    assert snapshot.unknowns == ("unknown-1",)
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


def test_snapshot_tail_preserves_and_deduplicates_risks():
    first = event(
        1,
        "PLAN_FORMED",
        unresolved_risks=("risk-1",),
        next_action="try A",
        claim_ceiling="bounded",
    )
    second = event(
        2,
        "OBSERVATION_RECORDED",
        first.event_hash,
        unresolved_risks=("risk-1", "risk-2"),
        next_action="finish",
        claim_ceiling="bounded",
    )
    resumed = resume(
        project([first]),
        [second],
        task_id="task-1",
        attempt_id="attempt-1",
        source_revision="src-a",
        contract_revision="contract-a",
    )
    assert resumed.unresolved_risks == ("risk-1", "risk-2")


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


def test_empty_revision_is_rejected():
    with pytest.raises(ValueError):
        event(1, "PLAN_FORMED", source_revision="")


def test_forged_snapshot_is_rejected_without_optional_hash():
    first = event(1, "PLAN_FORMED", next_action="try A", claim_ceiling="bounded")
    snapshot = project([first])
    object.__setattr__(snapshot, "claim_ceiling", "forged")
    with pytest.raises(ValueError, match="snapshot tampered"):
        resume(
            snapshot,
            [],
            task_id="task-1",
            attempt_id="attempt-1",
            source_revision="src-a",
            contract_revision="contract-a",
        )
