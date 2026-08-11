import fcntl
import hashlib
import multiprocessing
import os
import threading
from pathlib import Path

import pytest

from nexus.events.log_store import DeveloperFeedbackDecisionStore
from nexus.events.transport import NexusEventBus
from nexus.feedback.contracts import (
    DeveloperFeedbackDecision,
    FailurePattern,
    FeedbackDecision,
    FeedbackDirective,
)


def decision(i="d1", **kwargs):
    return DeveloperFeedbackDecision(
        task_id="task-1", decision_id=i, decision=FeedbackDecision.KEEP, **kwargs
    )


def _hold_decision_lock(path: str, acquired, release) -> None:
    with open(path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        acquired.set()
        release.wait(timeout=5)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def test_append_chain_and_idempotent_replay(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    first = store.append(decision())
    assert first["sequence"] == 1
    assert store.append(decision()) == first
    with pytest.raises(ValueError, match="idempotency"):
        store.append(decision(reason_codes=("OTHER",)))
    assert len(store.read_recent()) == 1


def test_validation_rejects_free_text_paths_and_authority():
    with pytest.raises(ValueError):
        decision(reason_codes=("free text",))
    with pytest.raises(ValueError):
        decision(evidence_refs=("/tmp/private",))
    with pytest.raises(ValueError):
        decision(authority_flags=(("approval", True),))


def test_constructor_rejects_nonsemantic_field_types():
    with pytest.raises(ValueError):
        decision(reason_codes=True)
    with pytest.raises(ValueError):
        decision(evidence_refs=1)
    with pytest.raises(ValueError):
        decision(request_digest=True)


def test_corruption_and_tamper_fail_closed(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.append(decision())
    path = store.path
    path.write_text(
        path.read_text().replace('"decision":"KEEP"', '"decision":"REVISE"'), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        store.read_recent()


@pytest.mark.parametrize("payload", [b"\n", b"null\n", b'{"schema":"x"\n'])
def test_blank_non_object_and_partial_final_corruption_fail_closed(tmp_path: Path, payload: bytes):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.configure(tmp_path)
    store.path.write_bytes(payload)
    with pytest.raises(ValueError):
        store.read_recent()


def test_duplicate_key_and_middle_corruption_fail_closed(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.append(decision())
    store.append(decision("d2"))
    lines = store.path.read_bytes().splitlines()
    duplicate = lines[0].replace(
        b'"schema":', b'"schema":"nexus.developer_feedback_decision.v1","schema":', 1
    )
    store.path.write_bytes(duplicate + b"\n" + lines[1] + b"\n")
    with pytest.raises(ValueError):
        store.read_recent()


def test_sequence_and_parent_digest_tamper_fail_closed(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    first = store.append(decision())
    second = store.append(decision("d2"))
    second["sequence"] = 99
    unsigned = dict(second)
    unsigned.pop("record_digest")
    second["record_digest"] = hashlib.sha256(store._canonical(unsigned)).hexdigest()
    store.path.write_bytes(store._canonical(first) + b"\n" + store._canonical(second) + b"\n")
    with pytest.raises(ValueError, match="broken|tampered"):
        store.read_recent()


def test_forged_valid_digest_malformed_token_fails_closed(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    record = store.append(decision())
    record["task_id"] = "/private/path"
    unsigned = dict(record)
    unsigned.pop("record_digest")
    record["record_digest"] = hashlib.sha256(store._canonical(unsigned)).hexdigest()
    store.path.write_bytes(store._canonical(record) + b"\n")
    with pytest.raises(ValueError, match="token grammar"):
        store.read_recent()


def test_stale_tail_and_concurrent_append(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.append(decision())
    with pytest.raises(ValueError, match="stale"):
        store.append(decision("d2"), expected_tail="0" * 64)
    results = []

    def run(i):
        results.append(store.append(decision(f"d{i}"))["sequence"])

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2, 6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [2, 3, 4, 5]


def test_lock_timeout_under_contention(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    acquired = multiprocessing.Event()
    release = multiprocessing.Event()

    holder = multiprocessing.Process(
        target=_hold_decision_lock,
        args=(str(store.lock_path), acquired, release),
    )
    holder.start()
    try:
        assert acquired.wait(timeout=5)
        with pytest.raises(TimeoutError, match="lock timeout"):
            store.append(decision(), lock_timeout=0.02)
    finally:
        release.set()
        holder.join(timeout=5)
        if holder.is_alive():
            holder.terminate()
            holder.join()
    assert holder.exitcode == 0


def test_typed_emitter_notifies_after_commit_and_generic_is_reserved(tmp_path: Path):
    NexusEventBus.configure(tmp_path)
    seen = []
    NexusEventBus.subscribe("developer_feedback_decision", lambda payload: seen.append(payload))
    with pytest.raises(ValueError):
        NexusEventBus.publish("developer_feedback_decision", {})
    record = NexusEventBus.emit_developer_feedback_decision(decision())
    assert seen == [record]
    assert (tmp_path / ".nexus/events/developer_feedback_decision.v1.jsonl").exists()


def test_replay_does_not_notify_and_replay_stale_tail_is_checked(tmp_path: Path):
    NexusEventBus.configure(tmp_path)
    old_subscribers = NexusEventBus._subscribers
    seen = []
    try:
        NexusEventBus._subscribers = {}
        NexusEventBus.subscribe("developer_feedback_decision", seen.append)
        first = NexusEventBus.emit_developer_feedback_decision(decision("replay"))
        assert seen == [first]
        replay = NexusEventBus.emit_developer_feedback_decision(decision("replay"))
        assert replay == first
        assert seen == [first]
        with pytest.raises(ValueError, match="stale"):
            NexusEventBus.emit_developer_feedback_decision(
                decision("replay"), expected_tail="0" * 64
            )
    finally:
        NexusEventBus._subscribers = old_subscribers


def test_max_bytes_rejects_append_and_read(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.MAX_BYTES = 1
    with pytest.raises(ValueError, match="ceiling"):
        store.append(decision())
    store.path.write_bytes(b"{}\n")
    with pytest.raises(ValueError):
        store.read_recent()


def test_deterministic_directive_mapping():
    assert (
        DeveloperFeedbackDecision.from_directive(
            task_id="task-1", decision_id="d2", directive=FeedbackDirective([], [], False)
        ).decision
        is FeedbackDecision.KEEP
    )
    assert (
        DeveloperFeedbackDecision.from_directive(
            task_id="task-1",
            decision_id="d3",
            directive=FeedbackDirective([FailurePattern("P_FAIL", "ignored", 0.95)], [], False),
        ).decision
        is FeedbackDecision.REJECT
    )


@pytest.mark.parametrize(
    ("directive", "expected"),
    [
        (FeedbackDirective([], [], False), FeedbackDecision.KEEP),
        (FeedbackDirective([], [], True), FeedbackDecision.REVISE),
        (
            FeedbackDirective([FailurePattern("P_FAIL", "ignored", 0.95)], [], False),
            FeedbackDecision.REJECT,
        ),
        (
            FeedbackDirective([FailurePattern("P_WARN", "ignored", 0.2)], [], False),
            FeedbackDecision.INVESTIGATE,
        ),
        (
            FeedbackDirective([FailurePattern("P_WARN", "ignored", 0.2)], [], True),
            FeedbackDecision.REVISE,
        ),
        (
            FeedbackDirective([FailurePattern("P_FAIL", "ignored", 0.99)], [], False),
            FeedbackDecision.REJECT,
        ),
    ],
)
def test_all_six_directive_mapping_cases(directive, expected):
    assert (
        DeveloperFeedbackDecision.from_directive(
            task_id="task-1", decision_id="mapping", directive=directive
        ).decision
        is expected
    )


def test_invalid_combinations_and_schema_fail_closed():
    with pytest.raises(ValueError):
        DeveloperFeedbackDecision(task_id="task-1", decision_id="d", decision="KEEP", schema="v2")
    with pytest.raises(ValueError):
        decision(
            authority_flags=(
                ("approval", False),
                ("approval", False),
                ("route", False),
                ("production", False),
            )
        )


def test_unsupported_fcntl_fails_closed(tmp_path: Path, monkeypatch):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    monkeypatch.setattr(fcntl, "flock", lambda *args: (_ for _ in ()).throw(OSError("unsupported")))
    with pytest.raises(OSError, match="unsupported"):
        store.append(decision())


def test_fsync_uncertainty_does_not_claim_success(tmp_path: Path, monkeypatch):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    monkeypatch.setattr(os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("fsync")))
    with pytest.raises(OSError, match="fsync"):
        store.append(decision())


def _subprocess_append(root: str, decision_id: str, task_id: str, queue) -> None:
    store = DeveloperFeedbackDecisionStore(Path(root))
    value = DeveloperFeedbackDecision(
        task_id=task_id, decision_id=decision_id, decision=FeedbackDecision.KEEP
    )
    queue.put(store.append(value)["sequence"])


def test_subprocess_same_and_different_task_contention(tmp_path: Path):
    queue = multiprocessing.Queue()
    processes = [
        multiprocessing.Process(
            target=_subprocess_append,
            args=(str(tmp_path), f"d{i}", "task-1" if i == 0 else "task-2", queue),
        )
        for i in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=5)
    assert sorted(queue.get(timeout=1) for _ in processes) == [1, 1]


def test_subprocess_same_task_same_decision_is_idempotent(tmp_path: Path):
    queue = multiprocessing.Queue()
    processes = [
        multiprocessing.Process(
            target=_subprocess_append, args=(str(tmp_path), "same", "task-1", queue)
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=5)
    assert [queue.get(timeout=1) for _ in processes] == [1, 1]
    assert len(DeveloperFeedbackDecisionStore(tmp_path).read_recent()) == 1


def test_subprocess_same_task_different_decisions_are_sequenced(tmp_path: Path):
    queue = multiprocessing.Queue()
    processes = [
        multiprocessing.Process(
            target=_subprocess_append, args=(str(tmp_path), f"d{i}", "task-1", queue)
        )
        for i in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=5)
    assert sorted(queue.get(timeout=1) for _ in processes) == [1, 2]


def test_observer_failure_is_post_commit(tmp_path: Path):
    old_subscribers = NexusEventBus._subscribers
    old_broadcaster = NexusEventBus._remote_broadcaster
    try:
        NexusEventBus.configure(tmp_path)
        NexusEventBus._subscribers = {}
        NexusEventBus.subscribe(
            "developer_feedback_decision",
            lambda _: (_ for _ in ()).throw(RuntimeError("observer")),
        )
        NexusEventBus.set_remote_broadcaster(
            lambda *_: (_ for _ in ()).throw(RuntimeError("remote"))
        )
        record = NexusEventBus.emit_developer_feedback_decision(decision("observer"))
        assert DeveloperFeedbackDecisionStore(tmp_path).read_recent() == [record]
    finally:
        NexusEventBus._subscribers = old_subscribers
        NexusEventBus._remote_broadcaster = old_broadcaster


def test_record_ceiling_fails_closed(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.MAX_RECORDS = 1
    store.append(decision())
    with pytest.raises(ValueError, match="ceiling"):
        store.append(decision("d2"))
