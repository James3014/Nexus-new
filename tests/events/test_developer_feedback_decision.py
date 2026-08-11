import fcntl
import hashlib
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
    return DeveloperFeedbackDecision(task_id="task-1", decision_id=i, decision=FeedbackDecision.KEEP, **kwargs)


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


def test_corruption_and_tamper_fail_closed(tmp_path: Path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.append(decision())
    path = store.path
    path.write_text(path.read_text().replace('"decision":"KEEP"', '"decision":"REVISE"'), encoding="utf-8")
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
    with open(store.lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            with pytest.raises(TimeoutError, match="lock timeout"):
                store.append(decision(), lock_timeout=0.02)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


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
    assert DeveloperFeedbackDecision.from_directive(
        task_id="task-1", decision_id="d2", directive=FeedbackDirective([], [], False)
    ).decision is FeedbackDecision.KEEP
    assert DeveloperFeedbackDecision.from_directive(
        task_id="task-1", decision_id="d3",
        directive=FeedbackDirective([FailurePattern("P_FAIL", "ignored", 0.95)], [], False),
    ).decision is FeedbackDecision.REJECT
