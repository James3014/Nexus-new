import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from nexus.contracts.lifecycle_action import LifecycleActionType, PermissionProfile, build_action_envelope
from nexus.orchestrator.lifecycle_guards import LifecycleGuardError, post_action_receipt_formatter, pre_action_guard, validate_architecture_approval, validate_consumed_architecture_approval


HEAD = "a" * 40
MANIFEST = "b" * 64


def test_architecture_approval_requires_exact_binding_and_accepts_valid_ack():
    now = datetime.now(timezone.utc)
    approval = {
        "schema": "nexus.architecture_approval.v1",
        "approval_id": "arch-1",
        "approved_by": "owner",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "bound_task_id": "task",
        "bound_attempt_id": "attempt",
        "candidate_commit_sha": "c" * 40,
        "candidate_tree_sha": "d" * 40,
        "authority_findings_sha256": "e" * 64,
        "approval_scope": "ALLOW_ACTION_ONCE",
    }
    assert validate_architecture_approval(approval, required=True, task_id="task", attempt_id="attempt", candidate_commit_sha="c" * 40, candidate_tree_sha="d" * 40, authority_findings_sha256="e" * 64)
    with pytest.raises(LifecycleGuardError, match="ARCHITECTURE_APPROVAL_BINDING_MISMATCH"):
            validate_architecture_approval({**approval, "candidate_tree_sha": "f" * 40}, required=True, task_id="task", attempt_id="attempt", candidate_commit_sha="c" * 40, candidate_tree_sha="d" * 40, authority_findings_sha256="e" * 64)


@pytest.mark.parametrize("mutate,code", [
    (lambda a: a.pop("bound_task_id"), "ARCHITECTURE_APPROVAL_BINDING_INCOMPLETE"),
    (lambda a: a.update({"unknown": 1}), "ARCHITECTURE_APPROVAL_UNKNOWN_FIELDS"),
    (lambda a: a.update({"candidate_commit_sha": "x"}), "ARCHITECTURE_APPROVAL_BINDING_MISMATCH"),
    (lambda a: a.update({"bound_attempt_id": "other"}), "ARCHITECTURE_APPROVAL_BINDING_MISMATCH"),
])
def test_architecture_approval_negative_controls(mutate, code):
    now = datetime.now(timezone.utc)
    approval = {"schema":"nexus.architecture_approval.v1","approval_id":"a","approved_by":"o","issued_at":now.isoformat(),"expires_at":(now+timedelta(minutes=5)).isoformat(),"approval_scope":"ALLOW_ACTION_ONCE","bound_task_id":"task","bound_attempt_id":"attempt","candidate_commit_sha":"c"*40,"candidate_tree_sha":"d"*40,"authority_findings_sha256":"e"*64}
    mutate(approval)
    with pytest.raises(LifecycleGuardError, match=code):
        validate_architecture_approval(approval, required=True, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)


def test_architecture_approval_unexpected_when_not_required():
    with pytest.raises(LifecycleGuardError, match="ARCHITECTURE_APPROVAL_UNEXPECTED"):
        validate_architecture_approval({"schema":"nexus.architecture_approval.v1"}, required=False, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)


def test_consumed_architecture_approval_requires_valid_consume_window():
    now = datetime.now(timezone.utc)
    base = {"schema":"nexus.architecture_approval.v1","approval_id":"a","approved_by":"o","issued_at":(now-timedelta(minutes=2)).isoformat(),"expires_at":(now+timedelta(minutes=5)).isoformat(),"approval_scope":"ALLOW_ACTION_ONCE","bound_task_id":"task","bound_attempt_id":"attempt","candidate_commit_sha":"c"*40,"candidate_tree_sha":"d"*40,"authority_findings_sha256":"e"*64}
    with pytest.raises(LifecycleGuardError, match="ARCHITECTURE_APPROVAL_NOT_CONSUMED"):
        validate_consumed_architecture_approval(base, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)
    valid = {**base, "consumed_at": now.isoformat()}
    assert validate_consumed_architecture_approval(valid, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)["consumed_at"]
    with pytest.raises(LifecycleGuardError, match="ARCHITECTURE_APPROVAL_CONSUMED_AT_INVALID"):
        validate_consumed_architecture_approval({**base, "consumed_at": (now-timedelta(minutes=3)).isoformat()}, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)
    expired_now = {**base, "expires_at": (now - timedelta(minutes=1)).isoformat(), "consumed_at": (now - timedelta(minutes=2)).isoformat()}
    assert validate_consumed_architecture_approval(expired_now, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)["consumed_at"]
    with pytest.raises(LifecycleGuardError, match="ARCHITECTURE_APPROVAL_NOT_CONSUMED"):
        validate_consumed_architecture_approval({key: value for key, value in expired_now.items() if key != "consumed_at"}, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)
    with pytest.raises(LifecycleGuardError, match="ARCHITECTURE_APPROVAL_CONSUMED_AT_INVALID"):
        validate_consumed_architecture_approval({**base, "consumed_at": (now + timedelta(minutes=1)).isoformat()}, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)


def test_architecture_approval_expired_and_future_issued_fail_closed():
    now = datetime.now(timezone.utc)
    base = {"schema":"nexus.architecture_approval.v1","approval_id":"a","approved_by":"o","approval_scope":"ALLOW_ACTION_ONCE","bound_task_id":"task","bound_attempt_id":"attempt","candidate_commit_sha":"c"*40,"candidate_tree_sha":"d"*40,"authority_findings_sha256":"e"*64}
    expired = {**base, "issued_at": (now - timedelta(minutes=10)).isoformat(), "expires_at": (now - timedelta(minutes=1)).isoformat()}
    with pytest.raises(LifecycleGuardError, match="ARCHITECTURE_APPROVAL_EXPIRED"):
        validate_architecture_approval(expired, required=True, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)
    future = {**base, "issued_at": (now + timedelta(minutes=1)).isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat()}
    with pytest.raises(LifecycleGuardError, match="ARCHITECTURE_APPROVAL_EXPIRY_INVALID"):
        validate_architecture_approval(future, required=True, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)


@pytest.mark.parametrize("field,value", [
    ("bound_task_id", "other-task"),
    ("bound_attempt_id", "other-attempt"),
    ("candidate_commit_sha", "f" * 40),
    ("candidate_tree_sha", "f" * 40),
    ("authority_findings_sha256", "f" * 64),
])
def test_consumed_architecture_approval_tampering_fails_closed(field, value):
    now = datetime.now(timezone.utc)
    approval = {"schema":"nexus.architecture_approval.v1","approval_id":"a","approved_by":"o","issued_at":(now-timedelta(minutes=2)).isoformat(),"expires_at":(now+timedelta(minutes=5)).isoformat(),"approval_scope":"ALLOW_ACTION_ONCE","bound_task_id":"task","bound_attempt_id":"attempt","candidate_commit_sha":"c"*40,"candidate_tree_sha":"d"*40,"authority_findings_sha256":"e"*64,"consumed_at":now.isoformat()}
    approval[field] = value
    with pytest.raises(LifecycleGuardError):
        validate_consumed_architecture_approval(approval, task_id="task", attempt_id="attempt", candidate_commit_sha="c"*40, candidate_tree_sha="d"*40, authority_findings_sha256="e"*64)


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
