from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.owner_lane_rebind import OwnerLaneRebind, validate_direct_merge_lane

NOW = datetime(2026, 9, 23, 1, 0, tzinfo=timezone.utc)
REPOSITORY = "James3014/Nexus-new"
TASK_ID = "issue-1023-lane-rebind"
ATTEMPT_ID = "attempt-1"
CARD_PATH = "tasks/campaign/00-card.md"
PR = 1200
HEAD = "a" * 40


def card(*, lane: str = "GOVERNED", task_id: str = TASK_ID) -> bytes:
    tick = chr(96)
    return (
        "# Task Card\n\n"
        f"task_id: {tick}{task_id}{tick}\n"
        "contract_kind: TRACKED_TASK_CARD\n"
        f"execution_lane: {lane}\n"
    ).encode()


def rebind(
    *, card_bytes: bytes | None = None, lane: str = "DIRECT_CANONICAL", **overrides
) -> OwnerLaneRebind:
    raw = {
        "repository": REPOSITORY,
        "issue_number": 1023,
        "task_id": TASK_ID,
        "attempt_id": ATTEMPT_ID,
        "task_card_path": CARD_PATH,
        "task_card_sha256": hashlib.sha256(card_bytes or card()).hexdigest(),
        "pull_request_number": PR,
        "expected_pr_head_sha": HEAD,
        "from_lane": "GOVERNED",
        "to_lane": lane,
        "owner_id": "James3014",
        "owner_confirmation": True,
        "decided_at": NOW,
    }
    raw.update(overrides)
    return OwnerLaneRebind.issue(**raw)


def check(
    *, card_bytes: bytes | None = None, lane: str = "DIRECT_CANONICAL", record=None, **overrides
):
    values = {
        "repository": REPOSITORY,
        "issue_number": 1023,
        "task_id": TASK_ID,
        "attempt_id": ATTEMPT_ID,
        "task_card_path": CARD_PATH,
        "task_card_bytes": card_bytes if card_bytes is not None else card(),
        "pull_request_number": PR,
        "current_pr_head_sha": HEAD,
        "requested_lane": lane,
        "expected_owner_id": "James3014",
        "lane_rebind": record,
        "carrier_author_id": "James3014" if record is not None else None,
        "carrier_created_at": NOW + timedelta(seconds=1) if record is not None else None,
        "merge_observed_at": NOW + timedelta(minutes=1),
    }
    values.update(overrides)
    return validate_direct_merge_lane(**values)


def test_governed_without_owner_rebind_blocks_before_direct_merge():
    result = check()
    assert result.allowed is False
    assert result.reason == "OWNER_LANE_REBIND_REQUIRED"


@pytest.mark.parametrize("lane", ["DIRECT_CANONICAL", "DIRECT_DELEGATED"])
def test_exact_owner_rebind_allows_direct_lane(lane: str):
    result = check(lane=lane, record=rebind(lane=lane))
    assert result.allowed is True
    assert result.effective_lane == lane
    assert result.reason == "OWNER_LANE_REBIND_VALID"
    assert result.lane_rebind_hash


@pytest.mark.parametrize(
    ("record_override", "check_override"),
    [
        ({"attempt_id": "foreign-attempt"}, {}),
        ({"task_card_sha256": "0" * 64}, {}),
        ({"expected_pr_head_sha": "b" * 40}, {}),
        ({"pull_request_number": PR + 1}, {}),
        ({}, {"current_pr_head_sha": "b" * 40}),
    ],
)
def test_stale_wrong_or_moved_subject_blocks(record_override, check_override):
    result = check(record=rebind(**record_override), **check_override)
    assert result.allowed is False
    assert result.reason == "OWNER_LANE_REBIND_SUBJECT_MISMATCH"


def test_changed_task_card_after_rebind_blocks():
    original = card()
    changed = original + b"\nnew authority text\n"
    result = check(card_bytes=changed, record=rebind(card_bytes=original))
    assert result.allowed is False
    assert result.reason == "OWNER_LANE_REBIND_SUBJECT_MISMATCH"


def test_owner_identity_and_durable_comment_author_must_match():
    wrong_record_owner = check(record=rebind(owner_id="other-owner"))
    assert wrong_record_owner.allowed is False
    assert wrong_record_owner.reason == "OWNER_LANE_REBIND_OWNER_MISMATCH"

    wrong_carrier_author = check(record=rebind(), carrier_author_id="automation-bot")
    assert wrong_carrier_author.allowed is False
    assert wrong_carrier_author.reason == "OWNER_LANE_REBIND_CARRIER_AUTHOR_MISMATCH"


def test_missing_durable_carrier_blocks_even_with_valid_record():
    result = check(record=rebind(), carrier_created_at=None)
    assert result.allowed is False
    assert result.reason == "DURABLE_REBIND_CARRIER_REQUIRED"


def test_post_merge_or_post_observation_rebind_is_rejected():
    record = rebind(decided_at=NOW + timedelta(minutes=2))
    result = check(
        record=record,
        carrier_created_at=NOW + timedelta(minutes=2, seconds=1),
        merge_observed_at=NOW + timedelta(minutes=1),
    )
    assert result.allowed is False
    assert result.reason == "POST_MERGE_LANE_REBIND_FORBIDDEN"


def test_backdated_record_cannot_hide_post_merge_durable_comment():
    result = check(
        record=rebind(decided_at=NOW - timedelta(minutes=1)),
        carrier_created_at=NOW + timedelta(minutes=2),
        merge_observed_at=NOW + timedelta(minutes=1),
    )
    assert result.allowed is False
    assert result.reason == "POST_MERGE_LANE_REBIND_FORBIDDEN"


def test_agent_authored_prose_cannot_substitute_for_typed_owner_record():
    result = check(record={"to_lane": "DIRECT_CANONICAL", "owner_confirmation": True})
    assert result.allowed is False
    assert result.reason == "OWNER_LANE_REBIND_INVALID"


def test_tampered_record_hash_is_rejected():
    payload = rebind().model_dump(mode="json")
    payload["expected_pr_head_sha"] = "b" * 40
    with pytest.raises(ValidationError, match="RECORD_HASH_INVALID"):
        OwnerLaneRebind.model_validate(payload)


def test_genuine_direct_attempt_without_governed_task_card_is_unchanged():
    result = validate_direct_merge_lane(
        repository=REPOSITORY,
        issue_number=1023,
        task_id="direct-task",
        attempt_id="direct-attempt",
        task_card_path=None,
        task_card_bytes=None,
        pull_request_number=PR,
        current_pr_head_sha=HEAD,
        requested_lane="DIRECT_CANONICAL",
        expected_owner_id="James3014",
        merge_observed_at=NOW,
    )
    assert result.allowed is True
    assert result.reason == "GENUINE_DIRECT_ATTEMPT"


def test_task_card_already_direct_preserves_current_direct_behavior():
    result = check(card_bytes=card(lane="DIRECT_CANONICAL"), record=None)
    assert result.allowed is True
    assert result.reason == "TASK_CARD_ALREADY_DIRECT"


def test_governed_lane_is_not_reinterpreted_as_direct_by_requested_text():
    result = check(card_bytes=card(lane="GOVERNED"), record=None, lane="DIRECT_DELEGATED")
    assert result.allowed is False
    assert result.reason == "OWNER_LANE_REBIND_REQUIRED"


def test_wrong_direct_lane_after_valid_rebind_blocks():
    result = check(lane="DIRECT_DELEGATED", record=rebind(lane="DIRECT_CANONICAL"))
    assert result.allowed is False
    assert result.reason == "OWNER_LANE_REBIND_SUBJECT_MISMATCH"
