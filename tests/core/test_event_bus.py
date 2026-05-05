from pathlib import Path
import time
import json
import pytest
from unittest.mock import MagicMock, patch
from nexus.core.event_bus import NexusEventBus

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
    handler = MagicMock()
    NexusEventBus.subscribe("audit_failed", handler)

    NexusEventBus.emit_audit_failure(task_id="task-1", reason="missing evidence", evidence_id="EV-1")

    handler.assert_called_once()
    payload = handler.call_args[0][0]
    assert payload["task_id"] == "task-1"
    assert payload["reason"] == "missing evidence"
    assert payload["evidence_id"] == "EV-1"
