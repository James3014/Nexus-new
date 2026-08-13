import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from nexus.events.log_store import DeveloperFeedbackDecisionStore, JsonlEventLogStore
from nexus.events.contracts import AttemptTransitionEvent
from nexus.events.signal_queue_service import SignalQueueService
from nexus.feedback.contracts import DeveloperFeedbackDecision

logger = logging.getLogger(__name__)

SEMANTIC_EVENT_TYPES = frozenset(
    {
        "audit_failed",
        "learning_decision",
        "evidence_accepted",
        "healing_artifact_announced",
        "lifecycle_hook",
        "phase_transition",
        "spec_bind",
        "attempt_transition",
    }
)
RAW_EVENT_TYPES = frozenset(
    {
        "phase_start",
        "phase_end",
        "lifecycle_pre",
        "external_signal_injected",
        "persist_event",
        "test_event",
    }
)


class NexusEventBus:
    """Persistent pub/sub with bidirectional signal injection."""

    _subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
    _event_log_path: Optional[Path] = None
    _signal_queue: List[Dict[str, Any]] = []
    _remote_broadcaster: Optional[Callable[[str, Dict[str, Any]], None]] = None
    _sequence_lock = threading.RLock()
    _subs_lock = threading.Lock()
    _observer_lock = threading.RLock()
    _global_seq = 0
    _log_store = JsonlEventLogStore()
    _developer_feedback_store = DeveloperFeedbackDecisionStore()
    _signal_queue_svc = SignalQueueService()
    _observer_error_count = 0
    _last_observer_error: Optional[Dict[str, Any]] = None
    _attempt_sequences: Dict[tuple[str, str], int] = {}

    @classmethod
    def set_remote_broadcaster(cls, broadcaster: Callable[[str, Dict[str, Any]], None]) -> None:
        cls._remote_broadcaster = broadcaster

    @classmethod
    def configure(cls, project_root: Path) -> None:
        """初始化持久化路徑"""
        log_dir, event_log_path = cls._log_store.configure(project_root)
        cls._event_log_path = event_log_path
        cls._developer_feedback_store.configure(project_root)
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
        if event_type == "developer_feedback_decision":
            raise ValueError("developer feedback decisions require the typed emitter")
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
            except Exception as exc:
                cls._record_observer_error(event_type, "subscriber", exc)

        # 遠端廣播
        if cls._remote_broadcaster:
            try:
                cls._remote_broadcaster(event_type, local_payload)
            except Exception as e:
                cls._record_observer_error(event_type, "remote_broadcaster", e)

    @classmethod
    def emit_attempt_transition(cls, event: AttemptTransitionEvent) -> Dict[str, Any]:
        """Append one ordered semantic attempt event without hidden payloads."""
        key = (event.task_id, event.attempt_id)
        with cls._sequence_lock:
            previous = cls._attempt_sequences.get(key, 0)
            if previous and event.sequence != previous + 1:
                raise ValueError("attempt transition sequence must be contiguous")
            cls._attempt_sequences[key] = event.sequence
        payload = event.to_dict()
        cls.publish("attempt_transition", payload)
        return payload

    @classmethod
    def emit_developer_feedback_decision(
        cls, decision: DeveloperFeedbackDecision, *, expected_tail: Optional[str] = None
    ) -> Dict[str, Any]:
        """Persist a typed recommendation, then notify observers after commit."""
        record = cls._developer_feedback_store.append(decision, expected_tail=expected_tail)
        if getattr(record, "replayed", False):
            return record
        payload = dict(record)
        with cls._subs_lock:
            handlers = cls._subscribers.get("developer_feedback_decision", [])[:]
        for handler in handlers:
            try:
                handler(payload)
            except Exception as exc:
                cls._record_observer_error("developer_feedback_decision", "subscriber", exc)
        if cls._remote_broadcaster:
            try:
                cls._remote_broadcaster("developer_feedback_decision", payload)
            except Exception as exc:
                cls._record_observer_error("developer_feedback_decision", "remote_broadcaster", exc)
        return record

    emit_feedback_decision = emit_developer_feedback_decision

    @classmethod
    def _record_observer_error(cls, event_type: str, observer: str, error: Exception) -> None:
        """Record observer failures without changing route or enforcement state."""
        with cls._observer_lock:
            cls._observer_error_count += 1
            cls._last_observer_error = {
                "event_type": event_type,
                "observer": observer,
                "error_type": type(error).__name__,
                "error": str(error),
                "observer_only": True,
            }
        logger.exception("Observer error for %s (%s)", event_type, observer)

    @classmethod
    def observer_telemetry(cls) -> Dict[str, Any]:
        with cls._observer_lock:
            return {
                "schema": "nexus.event_observer_telemetry.v1",
                "observer_error_count": cls._observer_error_count,
                "last_observer_error": dict(cls._last_observer_error or {}),
                "enforcement_authority": "synchronous_lifecycle_guards",
                "observer_only": True,
            }

    @classmethod
    def emit_audit_failure(cls, *, task_id: str, reason: str, evidence_id: str = "") -> None:
        cls.publish(
            "audit_failed",
            {"task_id": task_id, "reason": reason, "evidence_id": evidence_id},
        )

    @classmethod
    def emit_learning_decision(
        cls, *, task_id: str, action: str, reasons: List[str] | None = None
    ) -> None:
        cls.publish(
            "learning_decision",
            {"task_id": task_id, "action": action, "reasons": list(reasons or [])},
        )

    @classmethod
    def emit_evidence_accepted(
        cls, *, task_id: str, evidence_id: str, evidence_type: str = ""
    ) -> None:
        cls.publish(
            "evidence_accepted",
            {"task_id": task_id, "evidence_id": evidence_id, "evidence_type": evidence_type},
        )

    @classmethod
    def emit_healing_artifact_announced(cls, *, artifact: Any, policy: Any) -> Dict[str, Any]:
        """Publish portable healing advice only after signature/key policy passes."""
        from nexus.core.healing_artifacts import artifact_to_packet, artifact_transport_receipt

        receipt = artifact_transport_receipt(artifact, policy)
        if not receipt.get("passed"):
            return receipt
        cls.publish(
            "healing_artifact_announced",
            {
                "task_id": artifact.task_id,
                "artifact_id": artifact.artifact_id,
                "receipt": receipt,
                "packet": artifact_to_packet(artifact),
            },
        )
        return receipt

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

    @classmethod
    def audit_event_contracts(
        cls, limit: int = 100, *, fail_on_raw: bool = False, raw_policy: str | None = None
    ) -> Dict[str, Any]:
        """Report raw-vs-semantic event usage during the migration window."""
        if raw_policy is None:
            raw_policy = "block" if fail_on_raw else "warn"
        if raw_policy not in {"allow", "warn", "block", "strict"}:
            raise ValueError(f"unsupported raw event policy: {raw_policy}")
        events = cls.get_recent_events(limit=limit)
        semantic = []
        raw = []
        unknown = []
        for event in events:
            event_type = str(event.get("event_type") or "")
            if event_type in SEMANTIC_EVENT_TYPES:
                semantic.append(event_type)
            elif event_type in RAW_EVENT_TYPES:
                raw.append(event_type)
            else:
                unknown.append(event_type)
        fail_raw = raw_policy in {"block", "strict"}
        passed = not unknown and not (fail_raw and raw)
        failure_reasons = []
        warning_reasons = []
        if unknown:
            failure_reasons.append("unknown_event_types_present")
        if fail_raw and raw:
            failure_reasons.append("raw_event_types_present")
        elif raw_policy == "warn" and raw:
            warning_reasons.append("raw_event_types_present")
        return {
            "schema_version": "nexus_event_contract_audit.v1",
            "events_scanned": len(events),
            "semantic_event_count": len(semantic),
            "raw_event_count": len(raw),
            "unknown_event_count": len(unknown),
            "semantic_event_types": sorted(set(semantic)),
            "raw_event_types": sorted(set(raw)),
            "unknown_event_types": sorted(set(unknown)),
            "transition_status": "raw_events_present" if raw else "semantic_only",
            "strict_raw_mode": bool(fail_raw),
            "raw_policy": raw_policy,
            "warning_reasons": warning_reasons,
            "failure_reasons": failure_reasons,
            "passed": passed,
        }
