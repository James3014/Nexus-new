from typing import Dict, List, Callable, Any, Optional
import logging
import json
import time
from pathlib import Path

logger = logging.getLogger(__name__)

class NexusEventBus:
    """Persistent pub/sub with bidirectional signal injection."""
    _subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
    _event_log_path: Optional[Path] = None
    _signal_queue: List[Dict[str, Any]] = []
    _remote_broadcaster: Optional[Callable[[str, Dict[str, Any]], None]] = None

    @classmethod
    def set_remote_broadcaster(cls, broadcaster: Callable[[str, Dict[str, Any]], None]) -> None:
        cls._remote_broadcaster = broadcaster

    @classmethod
    def configure(cls, project_root: Path) -> None:
        """初始化持久化路徑"""
        log_dir = project_root / ".nexus" / "events"
        log_dir.mkdir(parents=True, exist_ok=True)
        cls._event_log_path = log_dir / "event_log.jsonl"
        
        # 載入外部信號佇列
        signal_file = log_dir / "signal_inbox.jsonl"
        if signal_file.exists():
            try:
                cls._signal_queue = [
                    json.loads(line)
                    for line in signal_file.read_text(encoding="utf-8").strip().split("\n")
                    if line.strip()
                ]
                signal_file.write_text("", encoding="utf-8")  # 消費後清空
            except Exception as e:
                logger.debug("signal_inbox load failed: %s", e)

    @classmethod
    def subscribe(cls, event_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        cls._subscribers.setdefault(event_type, []).append(handler)

    @classmethod
    def publish(cls, event_type: str, payload: Dict[str, Any]) -> None:
        """發布事件 + 持久化到 JSONL"""
        # 🆕 P2: 自動注入當前 trace context
        try:
            from nexus.telemetry.tracer import NexusTracer
            payload.setdefault("_trace_id", NexusTracer.current_trace_id())
            payload.setdefault("_span_id", NexusTracer.current_span_id())
        except Exception as e:
            logger.debug("OTel context injection skipped: %s", e)

        record = {
            "event_type": event_type,
            "timestamp": time.time(),
            "payload": payload,
        }
        
        # 持久化
        if cls._event_log_path:
            try:
                with open(cls._event_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, default=str) + "\n")
            except Exception as e:
                logger.debug("event_persist_failed: %s", e)
        
        # 廣播
        for handler in cls._subscribers.get(event_type, []):
            try:
                handler(payload)
            except Exception as e:
                logger.error("Event handler error for %s: %s", event_type, e)

        # 遠端廣播
        if cls._remote_broadcaster:
            try:
                cls._remote_broadcaster(event_type, payload)
            except Exception as e:
                logger.error("Remote broadcast error for %s: %s", event_type, e)

    @classmethod
    def inject_signal(cls, signal_type: str, payload: Dict[str, Any]) -> None:
        """外部注入信號（由 bot/人工/Pilot Friend 呼叫）"""
        cls._signal_queue.append({
            "signal_type": signal_type,
            "payload": payload,
            "injected_at": time.time(),
        })
        cls.publish("external_signal_injected", {"signal_type": signal_type})

    @classmethod
    def drain_signals(cls, signal_type: str = "") -> List[Dict[str, Any]]:
        """消費信號佇列（Pipeline 在每個 phase 開頭輪詢）"""
        if not signal_type:
            drained = cls._signal_queue[:]
            cls._signal_queue.clear()
            return drained
        
        matched = [s for s in cls._signal_queue if s["signal_type"] == signal_type]
        cls._signal_queue = [s for s in cls._signal_queue if s["signal_type"] != signal_type]
        return matched

    @classmethod
    def get_recent_events(cls, event_type: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """讀取最近的持久化事件（供 dashboard / 觀測）"""
        if not cls._event_log_path or not cls._event_log_path.exists():
            return []
        try:
            lines = cls._event_log_path.read_text(encoding="utf-8").strip().split("\n")
            events = [json.loads(l) for l in lines[-limit:] if l.strip()]
            if event_type:
                events = [e for e in events if e.get("event_type") == event_type]
            return events
        except Exception:
            return []
