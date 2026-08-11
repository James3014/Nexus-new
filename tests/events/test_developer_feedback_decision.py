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


def _subprocess_append(root: str, decision_id: str, queue) -> None:
    store = DeveloperFeedbackDecisionStore(Path(root))
    queue.put(store.append(decision(decision_id))["sequence"])


def test_subprocess_same_and_different_task_contention(tmp_path: Path):
    queue = multiprocessing.Queue()
    processes = [
        multiprocessing.Process(target=_subprocess_append, args=(str(tmp_path), f"d{i}", queue))
        for i in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=5)
    assert sorted(queue.get(timeout=1) for _ in processes) == [1, 2]


def test_observer_failure_is_post_commit(tmp_path: Path):
    NexusEventBus.configure(tmp_path)
    NexusEventBus.subscribe(
        "developer_feedback_decision", lambda _: (_ for _ in ()).throw(RuntimeError("observer"))
    )
    NexusEventBus.set_remote_broadcaster(lambda *_: (_ for _ in ()).throw(RuntimeError("remote")))
    record = NexusEventBus.emit_developer_feedback_decision(decision("observer"))
    assert DeveloperFeedbackDecisionStore(tmp_path).read_recent() == [record]


def test_record_ceiling_fails_closed(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.MAX_RECORDS = 1
    store.append(decision())
    with pytest.raises(ValueError, match="ceiling"):
        store.append(decision("d2"))
