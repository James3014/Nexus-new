from pathlib import Path
import time
import json
import pytest
from unittest.mock import MagicMock, patch
from nexus.core.belief_contracts import HealingArtifact
from nexus.core.event_bus import NexusEventBus
from nexus.core.healing_artifacts import HealingArtifactKeyPolicy, sign_healing_artifact

@pytest.fixture(autouse=True)
def cleanup_bus():
    """每個測試後清理 EventBus 狀態。"""
    NexusEventBus._subscribers = {}
    NexusEventBus._signal_queue = []

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
