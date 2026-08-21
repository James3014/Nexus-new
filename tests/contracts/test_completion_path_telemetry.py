from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.completion_path_telemetry import (
    NOT_OBSERVED,
    CompletionPathEvent,
    project_completion_path,
)

BASE = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
ISSUE = "493"
CANDIDATE = "candidate-493"
REPO = "James3014/Nexus-new"
HEAD = "a" * 40
MERGE = "b" * 40
MAIN = "c" * 40


def event(kind: str, offset: int, *, event_id: str | None = None, **overrides):
    payload = {
        "event_id": event_id or f"evt-{kind.lower()}-{offset}",
        "issue_id": ISSUE,
        "kind": kind,
        "occurred_at": BASE + timedelta(seconds=offset),
        "evidence_ref": f"evidence:{kind.lower()}:{offset}",
    }
    if kind in {"CANDIDATE_READY", "VERIFIED", "PR_READY", "MERGED", "RECONCILED", "CLOSED"}:
        payload["candidate_id"] = CANDIDATE
    if kind in {"PR_READY", "MERGED", "RECONCILED", "CLOSED"}:
        payload.update(repository=REPO, pr_number=493, candidate_head_sha=HEAD)
    if kind == "MERGED":
        payload.update(merge_commit_sha=MERGE, current_main_sha=MAIN)
    payload.update(overrides)
    return CompletionPathEvent.model_validate(payload)


def complete_events(*friction: CompletionPathEvent):
    events = [
        event("READY", 1),
        event("CANDIDATE_READY", 2),
        event("VERIFIED", 3),
        event("PR_READY", 4),
        event("MERGED", 5),
        event("RECONCILED", 6),
        event("CLOSED", 7),
        *friction,
        event("OBSERVATION_WINDOW_CLOSED", 20),
    ]
    return events


def test_open_window_keeps_absent_counters_not_observed():
    result = project_completion_path([event("READY", 1)])

    assert result["owner_interrupt_count"] == NOT_OBSERVED
    assert result["unnecessary_full_rebind_count"] == NOT_OBSERVED
    assert result["duplicate_verification_count"] == NOT_OBSERVED
    assert result["blocked_lane_global_stop_count"] == NOT_OBSERVED
    assert set(result["counter_observability"].values()) == {NOT_OBSERVED}
    assert result["compression_gate_evaluable"] is False
    assert result["compression_gate_pass"] is False
    assert result["mutation_authorized"] is False


def test_closed_complete_window_observes_zero_and_passes():
    result = project_completion_path(complete_events())

    assert result["owner_interrupt_count"] == 0
    assert result["unnecessary_full_rebind_count"] == 0
    assert result["duplicate_verification_count"] == 0
    assert result["blocked_lane_global_stop_count"] == 0
    assert set(result["counter_observability"].values()) == {"OBSERVED"}
    assert result["compression_gate_evaluable"] is True
    assert result["compression_gate_pass"] is True
    assert result["mutation_authorized"] is False


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("UNNECESSARY_OWNER_INTERRUPT", "owner_interrupt_count"),
        ("UNNECESSARY_FULL_REBIND", "unnecessary_full_rebind_count"),
        ("DUPLICATE_VERIFICATION", "duplicate_verification_count"),
        ("BLOCKED_LANE_GLOBAL_STOP", "blocked_lane_global_stop_count"),
    ],
)
def test_counted_friction_increments_only_its_counter(kind: str, field: str):
    result = project_completion_path(complete_events(event(kind, 10)))

    counters = {
        "owner_interrupt_count": result["owner_interrupt_count"],
        "unnecessary_full_rebind_count": result["unnecessary_full_rebind_count"],
        "duplicate_verification_count": result["duplicate_verification_count"],
        "blocked_lane_global_stop_count": result["blocked_lane_global_stop_count"],
    }
    assert counters[field] == 1
    assert all(value == 0 for key, value in counters.items() if key != field)
    assert result["compression_gate_pass"] is False


def test_genuine_external_owner_gate_is_not_unnecessary_interrupt():
    result = project_completion_path(complete_events(event("GENUINE_EXTERNAL_OWNER_GATE", 10)))
    assert result["owner_interrupt_count"] == 0
    assert result["compression_gate_pass"] is True


def test_affected_dimension_rebind_is_not_unnecessary_full_rebind():
    result = project_completion_path(complete_events(event("AFFECTED_DIMENSION_REBIND", 10)))
    assert result["unnecessary_full_rebind_count"] == 0
    assert result["compression_gate_pass"] is True


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("candidate_id", "other-candidate", "CANDIDATE_ID_CONFLICT"),
        ("repository", "other/repo", "REPOSITORY_CONFLICT"),
        ("pr_number", 999, "PR_CONFLICT"),
        ("candidate_head_sha", "d" * 40, "CANDIDATE_HEAD_CONFLICT"),
    ],
)
def test_conflicting_identity_fails_closed(field: str, value, error: str):
    events = complete_events()
    events[-2] = event("CLOSED", 7, **{field: value})
    with pytest.raises(ValueError, match=error):
        project_completion_path(events)


def test_conflicting_current_main_identity_fails_closed():
    events = complete_events()
    events.insert(-1, event("MERGED", 5, event_id="evt-second-merge", current_main_sha="d" * 40))
    with pytest.raises(ValueError, match="CURRENT_MAIN_CONFLICT"):
        project_completion_path(events)


def test_missing_required_github_binding_fails_validation():
    with pytest.raises(ValidationError, match="GITHUB_BINDING_REQUIRED"):
        event("PR_READY", 4, repository=None)


def test_malformed_git_sha_fails_validation():
    with pytest.raises(ValidationError, match="GIT_SHA_INVALID"):
        event("MERGED", 5, candidate_head_sha="not-a-sha")


def test_naive_timestamp_fails_validation():
    with pytest.raises(ValidationError, match="TIMESTAMP_MUST_BE_TIMEZONE_AWARE"):
        event("READY", 1, occurred_at=datetime(2026, 8, 21, 12, 0))


def test_identical_duplicate_event_is_idempotent():
    duplicate = event("READY", 1)
    result = project_completion_path([duplicate, duplicate])
    assert result["ready_at"] == duplicate.occurred_at.isoformat()


def test_conflicting_duplicate_event_fails_closed():
    first = event("READY", 1, event_id="same")
    second = event("READY", 2, event_id="same")
    with pytest.raises(ValueError, match="CONFLICTING_DUPLICATE_EVENT"):
        project_completion_path([first, second])


def test_conflicting_duplicate_milestone_fails_closed():
    with pytest.raises(ValueError, match="CONFLICTING_MILESTONE"):
        project_completion_path([event("READY", 1), event("READY", 2, event_id="different")])


def test_milestone_order_regression_fails_closed():
    with pytest.raises(ValueError, match="MILESTONE_ORDER_REGRESSION"):
        project_completion_path([event("READY", 5), event("CANDIDATE_READY", 2)])


def test_event_after_window_closure_fails_closed():
    with pytest.raises(ValueError, match="EVENT_AFTER_WINDOW_CLOSED"):
        project_completion_path(
            [
                event("READY", 1),
                event("OBSERVATION_WINDOW_CLOSED", 5),
                event("UNNECESSARY_OWNER_INTERRUPT", 6),
            ]
        )


def test_closed_window_does_not_fabricate_missing_milestones():
    result = project_completion_path(
        [event("READY", 1), event("OBSERVATION_WINDOW_CLOSED", 2)]
    )
    assert result["ready_at"] != NOT_OBSERVED
    assert result["candidate_ready_at"] == NOT_OBSERVED
    assert result["owner_interrupt_count"] == 0
    assert result["compression_gate_evaluable"] is False
    assert result["compression_gate_pass"] is False


def test_projection_exposes_no_mutation_authority():
    result = project_completion_path(complete_events())
    forbidden = {"approve", "approval", "merge_authorized", "close_authorized", "dispatch_authorized"}
    assert forbidden.isdisjoint(result)
    assert result["mutation_authorized"] is False
