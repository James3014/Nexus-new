import json
from pathlib import Path

from nexus.events.signal_queue_service import SignalQueueService


def test_signal_queue_service_load_from_inbox(tmp_path: Path):
    inbox = tmp_path / "signal_inbox.jsonl"
    inbox.write_text(json.dumps({"signal_type": "boot", "payload": {"ok": True}}) + "\n", encoding="utf-8")
    svc = SignalQueueService()
    queue = svc.load_from_inbox(inbox)
    assert len(queue) == 1
    assert queue[0]["signal_type"] == "boot"
    assert inbox.read_text(encoding="utf-8") == ""


def test_signal_queue_service_inject_and_drain():
    svc = SignalQueueService()
    svc.inject("STOP", {"reason": "manual"})
    svc.inject("REPLAN", {"reason": "force"})
    drained = svc.drain("STOP")
    assert len(drained) == 1
    assert drained[0]["payload"]["reason"] == "manual"
    remaining = svc.queue
    assert len(remaining) == 1
    assert remaining[0]["signal_type"] == "REPLAN"
