import hashlib

import pytest

from nexus.contracts.lifecycle_action import LifecycleActionType, PermissionProfile, build_action_envelope
from nexus.orchestrator.lifecycle_guards import LifecycleGuardError, post_action_receipt_formatter, pre_action_guard


HEAD = "a" * 40
MANIFEST = "b" * 64


def _action(**kwargs):
    request = {"task_id": "guard-task", "allowed_files": ["README.md"], "what": "bounded"}
    request.update(kwargs.pop("request", {}))
    return build_action_envelope(
        task_id="guard-task",
        action_type=kwargs.pop("action_type", LifecycleActionType.TASK_RUN),
        request=request,
        tool_manifest_hash=MANIFEST,
        expected_head=kwargs.pop("expected_head", HEAD),
        allowed_paths=kwargs.pop("allowed_paths", ["README.md"]),
        mutation=kwargs.pop("mutation", True),
        permission_profile=kwargs.pop("permission_profile", PermissionProfile.MUTATE_BOUNDED),
        **kwargs,
    )


def test_pre_action_guard_returns_bounded_receipt_for_valid_identity():
    receipt = pre_action_guard(_action(), request={"allowed_files": ["README.md"]}, current_head=HEAD, tool_manifest_hash=MANIFEST)
    assert receipt["passed"] is True
    assert receipt["mutation_permitted"] is True
    assert receipt["permission_profile"] == "MUTATE_BOUNDED"


@pytest.mark.parametrize(
    ("kwargs", "req", "current_head", "manifest", "code"),
    [
        ({}, {"allowed_files": ["README.md"]}, "c" * 40, MANIFEST, "EXPECTED_HEAD_MISMATCH"),
        ({}, {"allowed_files": ["other.py"]}, HEAD, MANIFEST, "ALLOWED_PATH_MISMATCH"),
        ({}, {"allowed_files": ["README.md"]}, HEAD, "c" * 64, "TOOL_MANIFEST_NAME_DRIFT"),
    ],
)
def test_pre_action_guard_fail_closed_codes(kwargs, req, current_head, manifest, code):
    with pytest.raises(LifecycleGuardError) as caught:
        pre_action_guard(_action(**kwargs), request=req, current_head=current_head, tool_manifest_hash=manifest)
    assert caught.value.code == code
    assert caught.value.as_dict()["mutation_permitted"] is False


def test_task_card_sha256_is_bound_and_drift_is_rejected(tmp_path):
    card = tmp_path / "card.md"
    card.write_text("task card\n", encoding="utf-8")
    card_hash = hashlib.sha256(card.read_bytes()).hexdigest()
    action = _action(task_card_path="card.md", task_card_hash=card_hash)
    receipt = pre_action_guard(action, request={"allowed_files": ["README.md"]}, canonical_root=tmp_path, current_head=HEAD, tool_manifest_hash=MANIFEST)
    assert receipt["passed"] is True
    card.write_text("drift\n", encoding="utf-8")
    with pytest.raises(LifecycleGuardError) as caught:
        pre_action_guard(action, request={"allowed_files": ["README.md"]}, canonical_root=tmp_path, current_head=HEAD, tool_manifest_hash=MANIFEST)
    assert caught.value.code == "TASK_CARD_HASH_MISMATCH"


def test_post_action_requires_verifier_for_terminal_mutation():
    receipt = post_action_receipt_formatter(
        action=_action(),
        status="COMMITTED",
        commit_sha=HEAD,
        receipt={"commit_sha": HEAD, "receipt_hash": MANIFEST, "verifier_evidence": [{"command": "pass"}]},
    )
    assert receipt["passed"] is True
    assert receipt["evidence_complete"] is True
