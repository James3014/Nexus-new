import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import logging
import time
import uuid

from nexus.events.log_store import JsonlEventLogStore
from nexus.events.signal_queue_service import SignalQueueService

logger = logging.getLogger(__name__)


class NexusEventBus:
    """Persistent pub/sub with bidirectional signal injection."""

    _subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
    _event_log_path: Optional[Path] = None
    _signal_queue: List[Dict[str, Any]] = []
    _remote_broadcaster: Optional[Callable[[str, Dict[str, Any]], None]] = None
    _sequence_lock = threading.RLock()
    _subs_lock = threading.Lock()
    _global_seq = 0
    _log_store = JsonlEventLogStore()
    _signal_queue_svc = SignalQueueService()

    @classmethod
    def set_remote_broadcaster(cls, broadcaster: Callable[[str, Dict[str, Any]], None]) -> None:
        cls._remote_broadcaster = broadcaster

    @classmethod
    def configure(cls, project_root: Path) -> None:
        """初始化持久化路徑"""
        log_dir, event_log_path = cls._log_store.configure(project_root)
        cls._event_log_path = event_log_path
        signal_file = log_dir / "signal_inbox.jsonl"
        cls._signal_queue = cls._signal_queue_svc.load_from_inbox(signal_file)

    @classmethod
    def _sync_signal_queue_from_legacy(cls) -> None:
        """Keep legacy direct writes to _signal_queue compatible with service state."""
        if cls._signal_queue is not cls._signal_queue_svc.queue:
            cls._signal_queue = cls._signal_queue_svc.reset(cls._signal_queue)

    @classmethod
    def subscribe(cls, event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        with cls._subs_lock:
            cls._subscribers.setdefault(event_type, []).append(handler)

    @classmethod
    def publish(cls, event_type: str, payload: Dict[str, Any]) -> None:
        """發布事件（v23 終極原子修復版）"""
        with cls._sequence_lock:
            cls._global_seq += 1
            local_payload = payload.copy()
            local_payload["_seq"] = cls._global_seq
            local_payload["internal_ts"] = time.time()
            local_payload.setdefault("_trace_id", str(uuid.uuid4()))

            record = {
                "event_type": event_type,
                "timestamp": local_payload["internal_ts"],
                "seq": local_payload["_seq"],
                "payload": local_payload,
            }

            if cls._event_log_path:
                if cls._log_store.event_log_path != cls._event_log_path:
                    cls._log_store.event_log_path = cls._event_log_path
                cls._log_store.append_record(record)

        # 廣播（在鎖外執行以避免死鎖，但順序已由文件保證）
        with cls._subs_lock:
            handlers = cls._subscribers.get(event_type, [])[:]  # 複製清單以防在遍歷時被修改

        for handler in handlers:
            try:
                handler(local_payload)
            except Exception:
                pass

        # 遠端廣播
        if cls._remote_broadcaster:
            try:
                cls._remote_broadcaster(event_type, local_payload)
            except Exception as e:
                logger.error("Remote broadcast error for %s: %s", event_type, e)

    @classmethod
    def emit_audit_failure(cls, *, task_id: str, reason: str, evidence_id: str = "") -> None:
        cls.publish(
            "audit_failed",
            {"task_id": task_id, "reason": reason, "evidence_id": evidence_id},
        )

    @classmethod
    def emit_learning_decision(cls, *, task_id: str, action: str, reasons: List[str] | None = None) -> None:
        cls.publish(
            "learning_decision",
            {"task_id": task_id, "action": action, "reasons": list(reasons or [])},
        )

    @classmethod
    def emit_evidence_accepted(cls, *, task_id: str, evidence_id: str, evidence_type: str = "") -> None:
        cls.publish(
            "evidence_accepted",
            {"task_id": task_id, "evidence_id": evidence_id, "evidence_type": evidence_type},
        )

    @classmethod
    def inject_signal(cls, signal_type: str, payload: Dict[str, Any]) -> None:
        """外部注入信號（由 bot/人工/Pilot Friend 呼叫）"""
        cls._sync_signal_queue_from_legacy()
        cls._signal_queue = cls._signal_queue_svc.inject(signal_type, payload)
        cls.publish("external_signal_injected", {"signal_type": signal_type})

    @classmethod
    def drain_signals(cls, signal_type: str = "") -> List[Dict[str, Any]]:
        """消費信號佇列（Pipeline 在每個 phase 開頭輪詢）"""
        cls._sync_signal_queue_from_legacy()
        drained = cls._signal_queue_svc.drain(signal_type)
        cls._signal_queue = cls._signal_queue_svc.queue
        return drained

    @classmethod
    def get_recent_events(cls, event_type: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """讀取最近的持久化事件（供 dashboard / 觀測）"""
        try:
            if cls._event_log_path and cls._log_store.event_log_path != cls._event_log_path:
                cls._log_store.event_log_path = cls._event_log_path
            return cls._log_store.read_recent(event_type=event_type, limit=limit)
        except Exception:
            return []
