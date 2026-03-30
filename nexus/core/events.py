#!/usr/bin/env python3
import time
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

@dataclass(frozen=True)
class NexusEvent:
    """不可變的系統事件"""
    event_id: str
    task_id: str
    phase: str
    event_type: str  # e.g., "state_change", "decision", "error", "phase_start"
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class EventStore:
    """
    Append-only 事件存儲。
    負責記錄系統所有變遷，並支援狀態投影 (Projection)。
    """
    def __init__(self):
        self._events: List[NexusEvent] = []
        self._start_time = time.time()

    def append(self, event: NexusEvent):
        self._events.append(event)
        
    def get_events(self, task_id: Optional[str] = None) -> List[NexusEvent]:
        if task_id:
            return [e for e in self._events if e.task_id == task_id]
        return list(self._events)

    def project_metadata(self, task_id: str) -> Dict[str, Any]:
        """
        將事件流投影回 metadata 字典。
        這是為了兼容現有的 NexusState.metadata。
        """
        projection: Dict[str, Any] = {}
        relevant_events = sorted(self.get_events(task_id), key=lambda x: x.timestamp)
        
        for event in relevant_events:
            if event.event_type == "state_change":
                projection.update(event.payload)
            elif event.event_type == "decision":
                decisions = projection.get("phase_decisions", {})
                decisions[event.phase] = event.payload.get("decision_id")
                projection["phase_decisions"] = decisions
                
                skills = projection.get("phase_skills", {})
                skills[event.phase] = event.payload.get("skill_id")
                projection["phase_skills"] = skills
                
        return projection

    def save_to_file(self, path: str):
        """將事件序列化為 JSONL"""
        with open(path, "w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.to_dict()) + "\n")
