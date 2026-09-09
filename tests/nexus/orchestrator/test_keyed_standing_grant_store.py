from __future__ import annotations

import json
import multiprocessing
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import nexus.orchestrator.standing_grant_store as store
from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)

NOW = datetime.now(timezone.utc)


def _ctx(*, repository=None, goal_id="goal-keyed", thread_id="thread-keyed", **kw):
    values = dict(
        owner_id="owner",
        coordinator_id="coord",
        repository=repository
        or RepositoryIdentity(
            repository_id="James3014/Nexus-new",
            canonical_remote="https://github.com/James3014/Nexus-new.git",
        ),
        thread_id=thread_id,
        goal_id=goal_id,
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    values.update(kw)
    return StandingGrantContext.issue(**values)


def _receipt(**kw):
    context = _ctx(**kw)
    return store.StandingGrantReceipt.issue(grant_id="grant-keyed", context=context)


def test_key_is_canonical_and_different_scopes_coexist(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "DEFAULT_RECEIPT_PATH", tmp_path / "authority" / "standing-grant.json"
    )
    first = _receipt()
    second = _receipt(goal_id="goal-other")
    assert store.standing_grant_key(first).digest != store.standing_grant_key(second).digest
    first_path = store.write_keyed_standing_grant_receipt(first)
    second_path = store.write_keyed_standing_grant_receipt(second)
    assert first_path != second_path
    assert store.load_keyed_standing_grant_receipt(store.standing_grant_key(first)) == first
    assert store.load_keyed_standing_grant_receipt(store.standing_grant_key(second)) == second


def test_registered_scope_is_process_bound_and_stale_after_cas(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "DEFAULT_RECEIPT_PATH", tmp_path / "authority" / "standing-grant.json"
    )
    first = _receipt()
    key = store.standing_grant_key(first)
    store.write_keyed_standing_grant_receipt(first)
    scope = store.load_standing_grant_scope(
        key,
        expected_receipt_hash=first.receipt_hash,
        expected_owner_id="owner",
        expected_coordinator_id="coord",
    )
    assert scope.process_id == os.getpid()
    successor = store.StandingGrantReceipt.issue(
        grant_id="grant-keyed-2", context=first.context, supersedes_grant_hash=first.receipt_hash
    )
    store.write_keyed_standing_grant_receipt(successor, expected_receipt_hash=first.receipt_hash)
    with pytest.raises(store.StandingGrantReceiptError, match="SCOPE_STALE"):
        store.authorize_keyed_standing_grant_effect(
            scope,
            repository=first.context.repository,
            action=AutonomyActionClass.REPOSITORY_PUSH,
            effect={"id": "x"},
        )
    forged = store.LoadedStandingGrantScope(
        key, first.receipt_hash, "owner", "coord", os.getpid(), object()
    )
    with pytest.raises(store.StandingGrantReceiptError, match="SCOPE_NOT_REGISTERED"):
        store.authorize_keyed_standing_grant_effect(
            forged,
            repository=first.context.repository,
            action=AutonomyActionClass.REPOSITORY_PUSH,
            effect={},
        )


def test_migration_fences_legacy_and_is_replayable(tmp_path, monkeypatch):
    legacy = tmp_path / "authority" / "standing-grant.json"
    monkeypatch.setattr(store, "DEFAULT_RECEIPT_PATH", legacy)
    receipt = _receipt()
    store.write_standing_grant_receipt(receipt)
    target = store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)
    assert target.read_bytes().endswith(b"\n")
    with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_FENCED"):
        store.load_standing_grant_receipt()
    assert store.load_keyed_standing_grant_receipt(store.standing_grant_key(receipt)) == receipt
    assert (
        store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)
        == target
    )
    successor = store.StandingGrantReceipt.issue(
        grant_id="grant-keyed-3",
        context=receipt.context,
        supersedes_grant_hash=receipt.receipt_hash,
    )
    assert (
        store.write_keyed_standing_grant_receipt(
            successor, expected_receipt_hash=receipt.receipt_hash
        )
        == target
    )


def test_malformed_migration_fence_denies_keyed_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "DEFAULT_RECEIPT_PATH", tmp_path / "authority" / "standing-grant.json"
    )
    receipt = _receipt(goal_id="goal-bad-fence")
    key = store.standing_grant_key(receipt)
    store.write_keyed_standing_grant_receipt(receipt)
    store._atomic_fence(store._fence_path(key, ".migration-intent.json"), {"key": "wrong"})
    with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_FENCE_INVALID"):
        store.load_keyed_standing_grant_receipt(key)


def test_inspect_and_load_do_not_write_missing_scope(tmp_path, monkeypatch):
    root = tmp_path / "authority"
    monkeypatch.setattr(store, "DEFAULT_RECEIPT_PATH", root / "standing-grant.json")
    key = store.standing_grant_key(_receipt())
    before = list(tmp_path.rglob("*"))
    assert store.inspect_keyed_standing_grant_receipt(key)["status"] == "MISSING"
    assert store.load_keyed_standing_grant_receipt(key) is None
    assert list(tmp_path.rglob("*")) == before


def _child_write(path: str, payload: str, expected: str | None, queue):
    store.DEFAULT_RECEIPT_PATH = Path(path)
    receipt = store.StandingGrantReceipt.model_validate(json.loads(payload))
    try:
        store.write_keyed_standing_grant_receipt(receipt, expected_receipt_hash=expected)
    except Exception as exc:  # witness the physical CAS outcome
        queue.put(type(exc).__name__ + ":" + str(exc))
    else:
        queue.put("PASS")


def test_same_key_subprocess_cas_has_one_winner(tmp_path):
    legacy = tmp_path / "authority" / "standing-grant.json"
    first = _receipt()
    successor = store.StandingGrantReceipt.issue(
        grant_id="grant-keyed-2", context=first.context, supersedes_grant_hash=first.receipt_hash
    )
    queue = multiprocessing.Queue()
    args = (str(legacy), successor.model_dump_json(), first.receipt_hash, queue)
    left = multiprocessing.Process(target=_child_write, args=args)
    right = multiprocessing.Process(target=_child_write, args=args)
    store.DEFAULT_RECEIPT_PATH = legacy
    store.write_keyed_standing_grant_receipt(first)
    left.start()
    right.start()
    left.join(10)
    right.join(10)
    outcomes = [queue.get(timeout=2), queue.get(timeout=2)]
    assert outcomes.count("PASS") == 1
    assert sum("STALE_WRITER_CAS_MISMATCH" in item for item in outcomes) == 1


def test_distinct_key_subprocess_writes_coexist(tmp_path):
    legacy = tmp_path / "authority" / "standing-grant.json"
    first = _receipt(goal_id="goal-process-a")
    second = _receipt(goal_id="goal-process-b")
    queue = multiprocessing.Queue()
    children = [
        multiprocessing.Process(
            target=_child_write, args=(str(legacy), item.model_dump_json(), None, queue)
        )
        for item in (first, second)
    ]
    for child in children:
        child.start()
    for child in children:
        child.join(10)
    assert [queue.get(timeout=2), queue.get(timeout=2)] == ["PASS", "PASS"]


def _child_migrate(path: str, expected: str, queue):
    store.DEFAULT_RECEIPT_PATH = Path(path)
    try:
        queue.put(str(store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=expected)))
    except Exception as exc:
        queue.put(type(exc).__name__ + ":" + str(exc))


def test_subprocess_resumes_durable_migration_intent_prefix(tmp_path):
    legacy = tmp_path / "authority" / "standing-grant.json"
    receipt = _receipt(goal_id="goal-crash-prefix")
    store.DEFAULT_RECEIPT_PATH = legacy
    store.write_standing_grant_receipt(receipt)
    key = store.standing_grant_key(receipt)
    store._atomic_fence(
        store._fence_path(key, ".migration-intent.json"),
        {
            "schema": "nexus.standing_grant_migration_intent.v1",
            "legacy_hash": receipt.receipt_hash,
            "target_hash": receipt.receipt_hash,
            "key": key.digest,
        },
    )
    queue = multiprocessing.Queue()
    child = multiprocessing.Process(
        target=_child_migrate, args=(str(legacy), receipt.receipt_hash, queue)
    )
    child.start()
    child.join(10)
    assert queue.get(timeout=2).endswith("receipt.json")
    assert store.load_keyed_standing_grant_receipt(key) == receipt


def _child_migrate_fault(path: str, expected: str, mode: str, queue):
    store.DEFAULT_RECEIPT_PATH = Path(path)
    original_fence = store._atomic_fence
    original_write = store._write_bytes
    state = {"fence": 0}

    def fence(path, payload):
        state["fence"] += 1
        if mode == "before-intent" and state["fence"] == 1:
            raise RuntimeError("crash-before-intent")
        if mode == "after-target" and path.name == ".migration-complete.json":
            raise RuntimeError("crash-after-target")
        return original_fence(path, payload)

    def write(*args, **kwargs):
        if mode == "after-intent":
            raise RuntimeError("crash-after-intent")
        return original_write(*args, **kwargs)

    store._atomic_fence = fence
    store._write_bytes = write
    try:
        store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=expected)
    except RuntimeError as exc:
        queue.put(str(exc))
    except Exception as exc:
        queue.put(type(exc).__name__ + ":" + str(exc))
    else:
        queue.put("UNEXPECTED_PASS")


@pytest.mark.parametrize("mode", ["before-intent", "after-intent", "after-target"])
def test_subprocess_fault_prefixes_resume_without_fallback(tmp_path, mode):
    legacy = tmp_path / "authority" / "standing-grant.json"
    receipt = _receipt(goal_id="goal-fault-" + mode)
    store.DEFAULT_RECEIPT_PATH = legacy
    store.write_standing_grant_receipt(receipt)
    queue = multiprocessing.Queue()
    child = multiprocessing.Process(
        target=_child_migrate_fault, args=(str(legacy), receipt.receipt_hash, mode, queue)
    )
    child.start()
    child.join(10)
    assert queue.get(timeout=2).startswith("crash-")
    target = store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)
    assert target.exists()
    assert store.load_keyed_standing_grant_receipt(store.standing_grant_key(receipt)) == receipt
    with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_FENCED"):
        store.load_standing_grant_receipt()


def _child_migrate_exit(path: str, expected: str, mode: str):
    store.DEFAULT_RECEIPT_PATH = Path(path)
    original_fence = store._atomic_fence
    original_write = store._write_bytes
    state = {"fence": 0}

    def fence(path, payload):
        state["fence"] += 1
        if mode == "before-intent" and state["fence"] == 1:
            os._exit(71)
        if mode == "after-target" and path.name == ".migration-complete.json":
            os._exit(71)
        return original_fence(path, payload)

    def write(*args, **kwargs):
        if mode == "after-intent":
            os._exit(71)
        return original_write(*args, **kwargs)

    store._atomic_fence = fence
    store._write_bytes = write
    store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=expected)


@pytest.mark.parametrize("mode", ["before-intent", "after-intent", "after-target"])
def test_true_subprocess_exit_prefix_is_denied_then_recovers(tmp_path, mode):
    legacy = tmp_path / "authority" / "standing-grant.json"
    receipt = _receipt(goal_id="goal-exit-" + mode)
    store.DEFAULT_RECEIPT_PATH = legacy
    store.write_standing_grant_receipt(receipt)
    queue = multiprocessing.Process(
        target=_child_migrate_exit, args=(str(legacy), receipt.receipt_hash, mode)
    )
    queue.start()
    queue.join(10)
    assert queue.exitcode == 71
    key = store.standing_grant_key(receipt)
    if mode != "before-intent":
        with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_INCOMPLETE"):
            store.load_keyed_standing_grant_receipt(key)
    target = store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)
    assert target.exists()
    assert store.load_keyed_standing_grant_receipt(key) == receipt


def test_completed_migration_cannot_resurrect_deleted_target(tmp_path):
    legacy = tmp_path / "authority" / "standing-grant.json"
    receipt = _receipt(goal_id="goal-deleted-target")
    store.DEFAULT_RECEIPT_PATH = legacy
    store.write_standing_grant_receipt(receipt)
    target = store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)
    target.unlink()
    key = store.standing_grant_key(receipt)
    assert store.load_keyed_standing_grant_receipt(key) is None
    with pytest.raises(
        store.StandingGrantReceiptError, match="MIGRATION_TARGET_MISSING_AFTER_COMPLETION"
    ):
        store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)


def test_revoked_deleted_keyed_receipt_cannot_replay_or_resurrect(tmp_path):
    legacy = tmp_path / "authority" / "standing-grant.json"
    revoked = _receipt(
        goal_id="goal-revoked-delete", revoked_at=NOW, revocation_reason="owner-revoked"
    )
    store.DEFAULT_RECEIPT_PATH = legacy
    store.write_standing_grant_receipt(revoked)
    target = store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=revoked.receipt_hash)
    target.unlink()
    with pytest.raises(
        store.StandingGrantReceiptError, match="MIGRATION_TARGET_MISSING_AFTER_COMPLETION"
    ):
        store.write_keyed_standing_grant_receipt(revoked)
    with pytest.raises(
        store.StandingGrantReceiptError, match="MIGRATION_TARGET_MISSING_AFTER_COMPLETION"
    ):
        store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=revoked.receipt_hash)


def test_orphan_completion_fence_denies_legacy_replay(tmp_path):
    legacy = tmp_path / "authority" / "standing-grant.json"
    receipt = _receipt(goal_id="goal-orphan-fence")
    store.DEFAULT_RECEIPT_PATH = legacy
    store.write_standing_grant_receipt(receipt)
    store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)
    key = store.standing_grant_key(receipt)
    store._fence_path(key, ".migration-intent.json").unlink()
    with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_FENCE_INVALID"):
        store.load_standing_grant_receipt()
    with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_FENCE_INVALID"):
        store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)


def test_malformed_resume_intent_denies_without_mutation(tmp_path):
    legacy = tmp_path / "authority" / "standing-grant.json"
    receipt = _receipt(goal_id="goal-malformed-resume")
    store.DEFAULT_RECEIPT_PATH = legacy
    store.write_standing_grant_receipt(receipt)
    key = store.standing_grant_key(receipt)
    store._atomic_fence(
        store._fence_path(key, ".migration-intent.json"),
        {
            "schema": "wrong",
            "legacy_hash": receipt.receipt_hash,
            "target_hash": receipt.receipt_hash,
            "key": key.digest,
        },
    )
    before = legacy.read_bytes()
    with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_FENCE_INVALID"):
        store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=receipt.receipt_hash)
    assert legacy.read_bytes() == before
    assert not store._keyed_receipt_path(key).exists()


@pytest.mark.parametrize("operation", ["switch", "restore"])
@pytest.mark.parametrize("completed", [False, True])
def test_legacy_transitions_deny_migrated_current_scope(
    tmp_path, monkeypatch, operation, completed
):
    legacy = tmp_path / "authority" / "standing-grant.json"
    monkeypatch.setattr(store, "DEFAULT_RECEIPT_PATH", legacy)
    receipt = _receipt()
    store.write_standing_grant_receipt(receipt)
    switch_args = dict(
        attempt_key="switch-migration",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id=receipt.context.goal_id,
        successor_goal_id="goal-temporary",
        successor_thread_id="thread-temporary",
        ttl_minutes=10,
        owner_confirmation=True,
        now=NOW,
    )
    if operation == "restore":
        switched = store.switch_task_card_authority(**switch_args)
        current = store.load_standing_grant_receipt(now=NOW)
        invoke = lambda: store.restore_task_card_authority(
            attempt_key="restore-migration",
            switch_operation_id=switched["switch_operation_id"],
            expected_temporary_receipt_hash=current.receipt_hash,
            owner_confirmation=True,
            now=NOW,
        )
    else:
        current = receipt
        invoke = lambda: store.switch_task_card_authority(**switch_args)
    if completed:
        store.migrate_legacy_standing_grant_receipt(expected_receipt_hash=current.receipt_hash)
    else:
        original = store._write_bytes

        def crash_copy(*args, **kwargs):
            raise RuntimeError("MIGRATION_COPY_INTERRUPTED")

        monkeypatch.setattr(store, "_write_bytes", crash_copy)
        with pytest.raises(RuntimeError, match="MIGRATION_COPY_INTERRUPTED"):
            store.migrate_legacy_standing_grant_receipt(
                expected_receipt_hash=current.receipt_hash
            )
        monkeypatch.setattr(store, "_write_bytes", original)
    before = {str(p): p.read_bytes() for p in legacy.parent.rglob("*") if p.is_file()}
    with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_FENCED"):
        invoke()
    after = {str(p): p.read_bytes() for p in legacy.parent.rglob("*") if p.is_file()}
    assert after == before


def test_unmigrated_public_switch_restore_preserves_predecessor_context(tmp_path, monkeypatch):
    legacy = tmp_path / "authority" / "standing-grant.json"
    monkeypatch.setattr(store, "DEFAULT_RECEIPT_PATH", legacy)
    receipt = _receipt()
    store.write_standing_grant_receipt(receipt)
    switched = store.switch_task_card_authority(
        attempt_key="switch-unmigrated",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id=receipt.context.goal_id,
        successor_goal_id="goal-temporary",
        successor_thread_id="thread-temporary",
        ttl_minutes=10,
        owner_confirmation=True,
        now=NOW,
    )
    temporary = store.load_standing_grant_receipt(now=NOW)
    assert temporary.context.allowed_actions == (
        AutonomyActionClass.TASK_CARD_COMMIT, AutonomyActionClass.TASK_CARD_CREATE
    )
    assert temporary.context.expires_at <= receipt.context.expires_at
    restored = store.restore_task_card_authority(
        attempt_key="restore-unmigrated",
        switch_operation_id=switched["switch_operation_id"],
        expected_temporary_receipt_hash=temporary.receipt_hash,
        owner_confirmation=True,
        now=NOW,
    )
    actual = store.load_standing_grant_receipt(now=NOW)
    assert actual.receipt_hash == restored["restored_receipt_hash"]
    assert actual.context == receipt.context
    assert actual.supersedes_grant_hash == temporary.receipt_hash


def test_switch_cannot_enter_previously_migrated_successor_scope(tmp_path, monkeypatch):
    authority = tmp_path / "authority"
    monkeypatch.setattr(store, "DEFAULT_RECEIPT_PATH", authority / "old-legacy.json")
    migrated = _receipt(goal_id="goal-migrated", thread_id="thread-migrated")
    store.write_standing_grant_receipt(migrated)
    target = store.migrate_legacy_standing_grant_receipt(
        expected_receipt_hash=migrated.receipt_hash
    )
    # A different legacy slot in the same authority directory may carry a
    # different unmigrated scope; it cannot re-enter the fenced keyed scope.
    legacy = authority / "standing-grant.json"
    monkeypatch.setattr(store, "DEFAULT_RECEIPT_PATH", legacy)
    current = _receipt()
    store.write_standing_grant_receipt(current)
    before = legacy.read_bytes(), target.read_bytes()
    with pytest.raises(store.StandingGrantReceiptError, match="MIGRATION_FENCED"):
        store.switch_task_card_authority(
            attempt_key="switch-into-migrated",
            expected_current_receipt_hash=current.receipt_hash,
            expected_current_goal_id=current.context.goal_id,
            successor_goal_id=migrated.context.goal_id,
            successor_thread_id=migrated.context.thread_id,
            ttl_minutes=10,
            owner_confirmation=True,
            now=NOW,
        )
    assert (legacy.read_bytes(), target.read_bytes()) == before
    assert store.load_standing_grant_receipt(now=NOW) == current
