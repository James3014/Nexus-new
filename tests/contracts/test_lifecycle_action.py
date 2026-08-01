import pytest

from nexus.contracts.lifecycle_action import (
    ApprovalScope,
    LifecycleActionType,
    PermissionProfile,
    build_action_envelope,
    canonical_request_hash,
)


HEAD = "a" * 40
MANIFEST = "b" * 64


def test_action_envelope_round_trips_and_hashes_canonically():
    request = {"what": "bounded", "allowed_files": ["README.md"]}
    envelope = build_action_envelope(
        task_id="task-1",
        action_type=LifecycleActionType.TASK_RUN,
        request=request,
        tool_manifest_hash=MANIFEST,
        expected_head=HEAD,
        allowed_paths=["README.md"],
        mutation=True,
        permission_profile=PermissionProfile.MUTATE_BOUNDED,
        task_card_path="tasks/campaign/card.md",
        task_card_hash=MANIFEST,
    )
    assert envelope.schema == "nexus.lifecycle_action.v1"
    assert envelope.verify_request({"allowed_files": ["README.md"], "what": "bounded"})
    assert envelope.request_hash == canonical_request_hash(request)
    assert envelope.model_dump()["approval_scope"] == ApprovalScope.ALLOW_ACTION_ONCE


@pytest.mark.parametrize(
    "payload",
    [
        {"task_id": "../bad"},
        {"expected_head": "HEAD"},
        {"allowed_paths": ["../escape"]},
        {"task_card_path": "/tmp/card.md"},
    ],
)
def test_action_envelope_rejects_malformed_identity(payload):
    base = {
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "idempotency_key": "key-1",
        "action_type": LifecycleActionType.TASK_RUN,
        "tool_manifest_hash": MANIFEST,
        "request_hash": MANIFEST,
        "expected_head": HEAD,
        "allowed_paths": ("README.md",),
        "permission_profile": PermissionProfile.MUTATE_BOUNDED,
        "mutation": True,
    }
    base.update(payload)
    with pytest.raises(ValueError):
        from nexus.contracts.lifecycle_action import LifecycleActionEnvelope

        LifecycleActionEnvelope(**base)


def test_same_idempotency_key_with_different_request_hash_is_detectable():
    first = build_action_envelope(
        task_id="task-1",
        action_type=LifecycleActionType.TASK_RUN,
        request={"value": 1},
        tool_manifest_hash=MANIFEST,
        expected_head=HEAD,
        allowed_paths=["README.md"],
        mutation=True,
        idempotency_key="stable-key",
        permission_profile=PermissionProfile.MUTATE_BOUNDED,
    )
    second = build_action_envelope(
        task_id="task-1",
        action_type=LifecycleActionType.TASK_RUN,
        request={"value": 2},
        tool_manifest_hash=MANIFEST,
        expected_head=HEAD,
        allowed_paths=["README.md"],
        mutation=True,
        idempotency_key="stable-key",
        permission_profile=PermissionProfile.MUTATE_BOUNDED,
    )
    assert first.idempotency_key == second.idempotency_key
    assert first.request_hash != second.request_hash
    assert not first.verify_request({"value": 2})
