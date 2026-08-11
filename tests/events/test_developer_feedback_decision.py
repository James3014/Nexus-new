from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

import nexus.events.log_store as log_store_module
from nexus.events.log_store import (
    DeveloperFeedbackConflict,
    DeveloperFeedbackDecisionStore,
    DeveloperFeedbackStale,
    DeveloperFeedbackStoreError,
)
from nexus.events.transport import NexusEventBus
from nexus.feedback.contracts import DeveloperFeedbackDecisionRequest, decision_mapping


def request(tmp_path: Path | None = None, **overrides) -> DeveloperFeedbackDecisionRequest:
    values = dict(
        decision_id="decision-1",
        task_id="task-1",
        attempt_id="attempt-1",
        action="review",
        evidence_refs=("EV-1",),
        source_revision="a" * 64,
        source_tree="b" * 64,
        evidence_hash="c" * 64,
        decision="KEEP",
        rationale_codes=("verified",),
        approver_ref="d" * 64,
        repository_ref="e" * 64,
        approved_at="2026-08-11T00:00:00Z",
        idempotency_key="idem-1",
    )
    values.update(overrides)
    return DeveloperFeedbackDecisionRequest(**values)


@pytest.mark.parametrize(
    ("decision", "delta", "expected"),
    [
        ("KEEP", None, "NO_FOLLOW_UP"),
        ("REVISE", "SPEC", "SPEC_DELTA_REQUESTED"),
        ("REVISE", "EVAL", "EVAL_DELTA_REQUESTED"),
        ("REVISE", "PRODUCT_ASSUMPTION", "PRODUCT_ASSUMPTION_DELTA_REQUESTED"),
        ("REJECT", None, "CANDIDATE_REJECTION_RECORDED"),
        ("INVESTIGATE", None, "INVESTIGATION_REQUESTED"),
    ],
)
def test_six_deterministic_mappings(decision, delta, expected):
    item = request(
        decision=decision,
        delta_type=delta,
        candidate_ref="cand-1" if decision == "REJECT" else None,
        candidate_digest="f" * 64 if decision == "REJECT" else None,
    )
    assert decision_mapping(item) == expected


def test_privacy_and_invalid_combinations_fail_closed():
    with pytest.raises(ValueError):
        request(action="raw prompt")
    with pytest.raises(ValueError):
        request(decision="KEEP", delta_type="SPEC")
    with pytest.raises(ValueError):
        request(decision="REVISE")
    with pytest.raises(ValueError):
        request(evidence_refs=("http://x",))
    with pytest.raises(ValueError):
        request(evidence_refs=("bad?query",))
    with pytest.raises(ValueError):
        request(rationale_codes=("\u202ehidden",))
    with pytest.raises(ValueError):
        request(decision="REJECT")


def test_genesis_restart_chain_and_replay_no_append(tmp_path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    first = store.append(request(tmp_path))
    assert first["status"] == "RECORDED"
    assert store.append(request(tmp_path))["status"] == "IDEMPOTENT_REPLAY"
    second = store.append(
        request(
            tmp_path,
            decision_id="decision-2",
            idempotency_key="idem-2",
            expected_task_seq=1,
            expected_parent_digest=first["record"]["record_digest"],
        )
    )
    assert second["record"]["task_seq"] == 2
    assert len(store.read()) == 2


def test_conflict_and_stale_tail(tmp_path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.append(request(tmp_path))
    with pytest.raises(DeveloperFeedbackConflict):
        store.append(request(tmp_path, action="different"))
    with pytest.raises(DeveloperFeedbackStale):
        store.append(
            request(
                tmp_path, decision_id="decision-2", idempotency_key="idem-2", expected_task_seq=0
            )
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.write_text("\n"),
        lambda p: p.write_text('{"schema":"wrong"}\n'),
        lambda p: p.write_bytes(b"{"),
        lambda p: p.write_text('{"schema":"nexus.developer_feedback_decision.v1","task_id":"x"}\n'),
    ],
)
def test_corruption_fails_closed_without_repair(tmp_path, mutation):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.append(request(tmp_path))
    mutation(store.path)
    with pytest.raises(DeveloperFeedbackStoreError):
        store.read()


def test_reserved_generic_publish_has_zero_side_effects(tmp_path):
    NexusEventBus.configure(tmp_path)
    NexusEventBus._global_seq = 41
    with pytest.raises(ValueError):
        NexusEventBus.publish("developer_feedback_decision", {"secret": "x"})
    assert NexusEventBus._global_seq == 41
    assert not (tmp_path / ".nexus" / "events" / "event_log.jsonl").exists()


def test_typed_emitter_notifies_after_commit_and_replay_is_silent(tmp_path):
    seen = []
    NexusEventBus._subscribers = {
        "developer_feedback_decision": [lambda payload: seen.append(payload)]
    }
    first = NexusEventBus.emit_developer_feedback_decision(request(tmp_path), project_root=tmp_path)
    replay = NexusEventBus.emit_developer_feedback_decision(
        request(tmp_path), project_root=tmp_path
    )
    assert first["status"] == "RECORDED" and replay["status"] == "IDEMPOTENT_REPLAY"
    assert len(seen) == 1
    assert (
        json.loads((tmp_path / ".nexus/events/developer_feedback_decision.v1.jsonl").read_text())[
            "next_gate"
        ]
        == "NO_FOLLOW_UP"
    )


def test_callback_runs_after_storage_lock_is_released(tmp_path):
    observed = []
    NexusEventBus._subscribers = {
        "developer_feedback_decision": [
            lambda _payload: observed.append(DeveloperFeedbackDecisionStore(tmp_path).read())
        ]
    }
    NexusEventBus.emit_developer_feedback_decision(request(tmp_path), project_root=tmp_path)
    assert len(observed) == 1 and observed[0][0]["task_seq"] == 1


def test_unsupported_flock_and_fsync_uncertainty_fail_closed(tmp_path, monkeypatch):
    original_flock = log_store_module.fcntl.flock
    monkeypatch.delattr(log_store_module.fcntl, "flock", raising=False)
    with pytest.raises(DeveloperFeedbackStoreError, match="unsupported_posix_flock"):
        DeveloperFeedbackDecisionStore(tmp_path).append(request(tmp_path))
    monkeypatch.setattr(log_store_module.fcntl, "flock", original_flock, raising=False)
    monkeypatch.setattr(
        log_store_module.os,
        "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("uncertain")),
    )
    with pytest.raises(OSError, match="uncertain"):
        DeveloperFeedbackDecisionStore(tmp_path).append(request(tmp_path))


def test_record_ceiling_fails_before_append(tmp_path):
    store = DeveloperFeedbackDecisionStore(tmp_path)
    store.MAX_RECORD_BYTES = 1
    with pytest.raises(DeveloperFeedbackStoreError, match="record_ceiling"):
        store.append(request(tmp_path))


def _append_worker(root: str, suffix: str) -> None:
    DeveloperFeedbackDecisionStore(Path(root)).append(
        request(Path(root), decision_id=f"decision-{suffix}", idempotency_key=f"idem-{suffix}")
    )


def test_subprocess_contention_keeps_a_valid_chain(tmp_path):
    processes = [
        multiprocessing.get_context("spawn").Process(
            target=_append_worker, args=(str(tmp_path), str(i))
        )
        for i in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
    assert all(process.exitcode == 0 for process in processes)
    assert [row["task_seq"] for row in DeveloperFeedbackDecisionStore(tmp_path).read()] == [1, 2]
