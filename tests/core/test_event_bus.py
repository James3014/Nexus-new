import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.core.belief_contracts import HealingArtifact
from nexus.core.event_bus import NexusEventBus
from nexus.core.healing_artifacts import HealingArtifactKeyPolicy, sign_healing_artifact
from nexus.events.contracts import build_attempt_transition_event
from nexus.events.log_store import JsonlEventLogStore


@pytest.fixture(autouse=True)
def cleanup_bus():
    """每個測試前後清理 EventBus 狀態，避免 hostile log 汙染其他 suites。"""
    NexusEventBus._subscribers = {}
    NexusEventBus._signal_queue = []
    NexusEventBus._observer_error_count = 0
    NexusEventBus._last_observer_error = None
    NexusEventBus._event_log_path = None
    NexusEventBus._log_store = JsonlEventLogStore()
    NexusEventBus._attempt_sequences = {}
    yield
    NexusEventBus._event_log_path = None
    NexusEventBus._log_store = JsonlEventLogStore()
    NexusEventBus._attempt_sequences = {}

def test_event_bus_publish_subscribe():
    """驗證基本的發布與訂閱流程。"""
    mock_handler = MagicMock()
    NexusEventBus.subscribe("test_event", mock_handler)
    
    payload = {"data": 123}
    NexusEventBus.publish("test_event", payload)
    
    mock_handler.assert_called_once()
    args = mock_handler.call_args[0][0]
    assert args["data"] == 123
    assert "_trace_id" in args


def test_observer_failure_is_fail_open_but_telemetry_is_recorded():
    def broken(_payload):
        raise RuntimeError("observer boom")

    NexusEventBus.subscribe("test_event", broken)
    NexusEventBus.publish("test_event", {"data": 123})
    telemetry = NexusEventBus.observer_telemetry()
    assert telemetry["observer_only"] is True
    assert telemetry["enforcement_authority"] == "synchronous_lifecycle_guards"
    assert telemetry["observer_error_count"] == 1
    assert telemetry["last_observer_error"]["observer"] == "subscriber"

def test_event_bus_persistence(tmp_path):
    """驗證事件是否能正確持久化到 JSONL。"""
    NexusEventBus.configure(tmp_path)
    
    NexusEventBus.publish("persist_event", {"val": "hello"})
    
    # 檢查檔案內容
    log_file = tmp_path / ".nexus" / "events" / "event_log.jsonl"
    assert log_file.exists()
    content = log_file.read_text()
    assert "persist_event" in content
    assert "hello" in content

def test_event_bus_signal_injection_and_drain(tmp_path):
    """驗證信號注入與消費 (inject/drain)。"""
    NexusEventBus.configure(tmp_path)
    
    NexusEventBus.inject_signal("STOP", {"reason": "user_abort"})
    
    assert len(NexusEventBus._signal_queue) == 1
    
    drained = NexusEventBus.drain_signals("STOP")
    assert len(drained) == 1
    assert drained[0]["payload"]["reason"] == "user_abort"
    assert len(NexusEventBus._signal_queue) == 0

def test_event_bus_configure_load(tmp_path):
    """驗證啟動時從 signal_inbox.jsonl 載入信號。"""
    log_dir = tmp_path / ".nexus" / "events"
    log_dir.mkdir(parents=True)
    inbox = log_dir / "signal_inbox.jsonl"
    inbox.write_text(json.dumps({"signal_type": "boot", "payload": {"foo": "bar"}}) + "\n")
    
    NexusEventBus.configure(tmp_path)
    
    assert len(NexusEventBus._signal_queue) == 1
    assert NexusEventBus._signal_queue[0]["signal_type"] == "boot"
    # 載入後應清空
    assert inbox.read_text() == ""


def test_event_bus_legacy_signal_queue_assignment_still_works(tmp_path):
    NexusEventBus.configure(tmp_path)
    NexusEventBus._signal_queue = []  # legacy direct reset
    NexusEventBus.inject_signal("STOP", {"reason": "legacy"})
    drained = NexusEventBus.drain_signals("STOP")
    assert len(drained) == 1
    assert drained[0]["payload"]["reason"] == "legacy"


def test_event_bus_typed_domain_emitters_preserve_publish_contract(tmp_path):
    NexusEventBus.configure(tmp_path)
    audit_handler = MagicMock()
    learning_handler = MagicMock()
    evidence_handler = MagicMock()
    NexusEventBus.subscribe("audit_failed", audit_handler)
    NexusEventBus.subscribe("learning_decision", learning_handler)
    NexusEventBus.subscribe("evidence_accepted", evidence_handler)

    NexusEventBus.emit_audit_failure(task_id="task-1", reason="missing evidence", evidence_id="EV-1")
    NexusEventBus.emit_learning_decision(task_id="task-1", action="FREEZE", reasons=["sir_veto"])
    NexusEventBus.emit_evidence_accepted(task_id="task-1", evidence_id="EV-2", evidence_type="git_diff")

    audit_handler.assert_called_once()
    learning_handler.assert_called_once()
    evidence_handler.assert_called_once()
    assert audit_handler.call_args[0][0]["_trace_id"]
    assert audit_handler.call_args[0][0]["reason"] == "missing evidence"
    assert learning_handler.call_args[0][0]["action"] == "FREEZE"
    assert learning_handler.call_args[0][0]["reasons"] == ["sir_veto"]
    assert evidence_handler.call_args[0][0]["evidence_type"] == "git_diff"
    content = (tmp_path / ".nexus" / "events" / "event_log.jsonl").read_text()
    assert "audit_failed" in content
    assert "learning_decision" in content
    assert "evidence_accepted" in content


def test_event_bus_emits_healing_artifact_only_after_policy_passes(tmp_path):
    NexusEventBus.configure(tmp_path)
    handler = MagicMock()
    NexusEventBus.subscribe("healing_artifact_announced", handler)
    signed = sign_healing_artifact(
        HealingArtifact(
            task_id="task-1",
            artifact_id="heal-1",
            artifact_type="repair_plan",
            created_at="2026-05-05T00:00:00Z",
            evidence_id="EV-1",
            summary="Use scoped storage",
        ),
        key="secret",
        key_id="node-a",
    )

    receipt = NexusEventBus.emit_healing_artifact_announced(
        artifact=signed,
        policy=HealingArtifactKeyPolicy(allowed_key_ids=frozenset({"node-a"}), verification_keys={"node-a": "secret"}),
    )

    assert receipt["passed"] is True
    handler.assert_called_once()
    payload = handler.call_args[0][0]
    assert payload["artifact_id"] == "heal-1"
    assert payload["packet"]["production_writes_allowed"] is False


def test_event_bus_does_not_emit_healing_artifact_when_policy_fails(tmp_path):
    NexusEventBus.configure(tmp_path)
    handler = MagicMock()
    NexusEventBus.subscribe("healing_artifact_announced", handler)
    unsigned = HealingArtifact(
        task_id="task-1",
        artifact_id="heal-1",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Use scoped storage",
    )

    receipt = NexusEventBus.emit_healing_artifact_announced(
        artifact=unsigned,
        policy=HealingArtifactKeyPolicy(allowed_key_ids=frozenset({"node-a"}), verification_keys={"node-a": "secret"}),
    )

    assert receipt["passed"] is False
    handler.assert_not_called()


def test_event_bus_audits_raw_and_semantic_transition_events(tmp_path):
    NexusEventBus.configure(tmp_path)

    NexusEventBus.emit_audit_failure(task_id="task-1", reason="missing evidence", evidence_id="EV-1")
    NexusEventBus.publish("phase_start", {"task_id": "task-1", "phase": "P"})

    audit = NexusEventBus.audit_event_contracts()

    assert audit["schema_version"] == "nexus_event_contract_audit.v1"
    assert audit["semantic_event_count"] == 1
    assert audit["raw_event_count"] == 1
    assert audit["unknown_event_count"] == 0
    assert audit["transition_status"] == "raw_events_present"
    assert audit["passed"] is True


def test_event_bus_audit_flags_unknown_event_types(tmp_path):
    NexusEventBus.configure(tmp_path)

    NexusEventBus.publish("legacy_custom_blob", {"task_id": "task-1"})

    audit = NexusEventBus.audit_event_contracts()

    assert audit["passed"] is False
    assert audit["unknown_event_types"] == ["legacy_custom_blob"]


def test_event_bus_audit_can_fail_on_raw_transition_events(tmp_path):
    NexusEventBus.configure(tmp_path)

    NexusEventBus.emit_audit_failure(task_id="task-1", reason="missing evidence", evidence_id="EV-1")
    NexusEventBus.publish("phase_start", {"task_id": "task-1", "phase": "P"})

    audit = NexusEventBus.audit_event_contracts(fail_on_raw=True)

    assert audit["passed"] is False
    assert audit["strict_raw_mode"] is True
    assert audit["failure_reasons"] == ["raw_event_types_present"]
    assert audit["raw_event_types"] == ["phase_start"]


def test_event_bus_audit_warns_on_raw_transition_events_before_strict_cutover(tmp_path):
    NexusEventBus.configure(tmp_path)

    NexusEventBus.emit_audit_failure(task_id="task-1", reason="missing evidence", evidence_id="EV-1")
    NexusEventBus.publish("phase_start", {"task_id": "task-1", "phase": "P"})

    audit = NexusEventBus.audit_event_contracts(raw_policy="warn")

    assert audit["passed"] is True
    assert audit["raw_policy"] == "warn"
    assert audit["warning_reasons"] == ["raw_event_types_present"]
    assert audit["failure_reasons"] == []


def test_event_bus_persists_same_timestamp_and_monotonic_sequence_seen_by_handlers(tmp_path):
    NexusEventBus.configure(tmp_path)
    seen = []
    NexusEventBus.subscribe("evidence_accepted", lambda payload: seen.append(payload))

    NexusEventBus.emit_evidence_accepted(task_id="task-1", evidence_id="EV-1", evidence_type="git_diff")
    NexusEventBus.emit_evidence_accepted(task_id="task-1", evidence_id="EV-2", evidence_type="pytest")

    rows = [row for row in NexusEventBus.get_recent_events(event_type="evidence_accepted", limit=10) if row["payload"].get("task_id") == "task-1"]
    assert [row["seq"] for row in rows] == sorted(row["seq"] for row in rows)
    assert len(rows) == 2
    for row in rows:
        assert row["timestamp"] == row["payload"]["internal_ts"]
    assert [item["_seq"] for item in seen] == [row["seq"] for row in rows]


def test_attempt_transition_events_are_contiguous_and_replayable(tmp_path):
    NexusEventBus.configure(tmp_path)
    first = build_attempt_transition_event(task_id="t1", attempt_id="a1", sequence=1, state="VERIFY")
    second = build_attempt_transition_event(task_id="t1", attempt_id="a1", sequence=2, state="ACCEPT")
    NexusEventBus.emit_attempt_transition(first)
    NexusEventBus.emit_attempt_transition(second)
    rows = NexusEventBus.get_recent_events(event_type="attempt_transition", limit=5)
    assert [row["payload"]["sequence"] for row in rows] == [1, 2]


def test_attempt_transition_sequence_recovers_after_restart(tmp_path):
    NexusEventBus.configure(tmp_path)
    NexusEventBus.emit_attempt_transition(
        build_attempt_transition_event(task_id="restart-task", attempt_id="a1", sequence=1, state="VERIFY")
    )

    # Simulate a fresh process: only the persisted append log may establish
    # the next sequence.
    NexusEventBus._attempt_sequences = {}
    NexusEventBus.configure(tmp_path)
    NexusEventBus.emit_attempt_transition(
        build_attempt_transition_event(task_id="restart-task", attempt_id="a1", sequence=2, state="ACCEPT")
    )
    rows = NexusEventBus.get_recent_events(event_type="attempt_transition", limit=5)
    assert [row["payload"]["sequence"] for row in rows] == [1, 2]


@pytest.mark.parametrize("sequence", [2, 3])
def test_attempt_transition_rejects_first_sequence_above_one(tmp_path, sequence):
    NexusEventBus.configure(tmp_path)
    with pytest.raises(ValueError, match="contiguous"):
        NexusEventBus.emit_attempt_transition(
            build_attempt_transition_event(task_id="first-seq", attempt_id="a1", sequence=sequence, state="VERIFY")
        )


def test_attempt_transition_rejects_duplicate_and_gap(tmp_path):
    NexusEventBus.configure(tmp_path)
    first = build_attempt_transition_event(task_id="ordered", attempt_id="a1", sequence=1, state="VERIFY")
    NexusEventBus.emit_attempt_transition(first)
    with pytest.raises(ValueError, match="contiguous"):
        NexusEventBus.emit_attempt_transition(first)
    with pytest.raises(ValueError, match="contiguous"):
        NexusEventBus.emit_attempt_transition(
            build_attempt_transition_event(task_id="ordered", attempt_id="a1", sequence=3, state="ACCEPT")
        )


def test_attempt_transition_rejects_tampered_persisted_record(tmp_path):
    NexusEventBus.configure(tmp_path)
    NexusEventBus.emit_attempt_transition(
        build_attempt_transition_event(task_id="tamper", attempt_id="a1", sequence=1, state="VERIFY")
    )
    log_file = tmp_path / ".nexus" / "events" / "event_log.jsonl"
    row = json.loads(log_file.read_text().splitlines()[0])
    row["payload"]["state"] = "ACCEPT"
    log_file.write_text(json.dumps(row) + "\n")

    NexusEventBus._attempt_sequences = {}
    with pytest.raises(ValueError, match="tampered"):
        NexusEventBus.configure(tmp_path)


def _attempt_record(store: JsonlEventLogStore, *, task_id="t1", attempt_id="a1", sequence=1):
    record = {
        "event_type": "attempt_transition",
        "timestamp": 1.0,
        "seq": sequence,
        "payload": {
            "task_id": task_id,
            "attempt_id": attempt_id,
            "sequence": sequence,
            "state": "VERIFY",
        },
    }
    store.append_record(record)
    return record


@pytest.mark.parametrize("field", ["payload", "_attempt_parent_digest", "_attempt_record_digest"])
def test_attempt_log_rejects_payload_parent_and_self_digest_tamper(tmp_path, field):
    store = JsonlEventLogStore()
    _, path = store.configure(tmp_path)
    _attempt_record(store)
    row = json.loads(path.read_text().splitlines()[0])
    if field == "payload":
        row["payload"]["state"] = "ACCEPT"
    else:
        row[field] = "f" * 64
    path.write_text(json.dumps(row) + "\n")

    with pytest.raises(ValueError, match="tampered"):
        JsonlEventLogStore().configure(tmp_path)


def test_attempt_log_rejects_malformed_json_and_legacy_digestless_record(tmp_path):
    store = JsonlEventLogStore()
    _, path = store.configure(tmp_path)
    _attempt_record(store)
    row = json.loads(path.read_text().splitlines()[0])
    row.pop("_attempt_parent_digest")
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="legacy attempt transition"):
        JsonlEventLogStore().configure(tmp_path)

    path.write_text("{not-json}\n")
    with pytest.raises(json.JSONDecodeError):
        JsonlEventLogStore().configure(tmp_path)


def test_attempt_log_ignores_non_attempt_interleaving_and_isolates_attempt_tails(tmp_path):
    store = JsonlEventLogStore()
    _, path = store.configure(tmp_path)
    _attempt_record(store, task_id="t1", attempt_id="a1", sequence=1)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event_type": "phase_start", "payload": {"task_id": "t1"}}) + "\n")
    _attempt_record(store, task_id="t2", attempt_id="a2", sequence=1)
    _attempt_record(store, task_id="t1", attempt_id="a1", sequence=2)

    assert store.attempt_tail("t1", "a1") == 2
    assert store.attempt_tail("t2", "a2") == 1


def test_attempt_log_rolls_back_tail_when_append_fails_before_write(tmp_path):
    store = JsonlEventLogStore()
    _, path = store.configure(tmp_path)
    real_open = open

    def fail_event_append(target, mode="r", *args, **kwargs):
        if Path(target) == path and "a" in mode:
            raise OSError("injected append failure")
        return real_open(target, mode, *args, **kwargs)

    record = {
        "event_type": "attempt_transition",
        "timestamp": 1.0,
        "seq": 1,
        "payload": {"task_id": "rollback", "attempt_id": "a1", "sequence": 1, "state": "VERIFY"},
    }
    with patch("nexus.events.log_store.open", side_effect=fail_event_append):
        with pytest.raises(OSError, match="injected append failure"):
            store.append_record(record)

    assert store.attempt_tail("rollback", "a1") == 0
    assert not path.exists() or path.read_text() == ""


def test_attempt_log_cross_process_duplicate_writer_allows_one_append(tmp_path):
    script = """
import sys
from pathlib import Path
from nexus.events.log_store import JsonlEventLogStore
store = JsonlEventLogStore()
store.configure(Path(sys.argv[1]))
store.append_record({
    'event_type': 'attempt_transition', 'timestamp': 1.0, 'seq': 1,
    'payload': {'task_id': 'shared', 'attempt_id': 'attempt', 'sequence': 1, 'state': 'VERIFY'},
})
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(tmp_path)], env=env)
        for _ in range(2)
    ]
    returncodes = sorted(process.wait(timeout=10) for process in processes)

    assert returncodes == [0, 1]
    store = JsonlEventLogStore()
    store.configure(tmp_path)
    assert store.attempt_tail("shared", "attempt") == 1
