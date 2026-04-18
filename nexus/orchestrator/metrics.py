from typing import Dict, Any, List
from datetime import datetime
from nexus.orchestrator.event_logger import EventLogger

class MetricsAggregator:
    def __init__(self, logger: EventLogger):
        self.logger = logger

    def compute_metrics(self) -> Dict[str, Any]:
        events = self.logger.get_events()
        if not events:
            return {}

        task_starts = {}
        task_ends = {}
        conflicts = 0
        gate_failures = 0
        success_count = 0
        total_tasks = set()

        for event in events:
            etype = event["event_type"]
            data = event["data"]
            tid = data.get("task_id")
            if not tid: continue
            
            total_tasks.add(tid)
            
            if etype == "TASK_START":
                task_starts[tid] = datetime.fromisoformat(event["timestamp"])
            elif etype == "TASK_CLOSE":
                task_ends[tid] = datetime.fromisoformat(event["timestamp"])
                success_count += 1
            elif etype == "TASK_CONFLICT":
                conflicts += 1
            elif etype == "GATE_FAILURE":
                gate_failures += 1

        # Calculate durations
        durations = []
        for tid, start_time in task_starts.items():
            if tid in task_ends:
                durations.append((task_ends[tid] - start_time).total_seconds())

        avg_lead_time = sum(durations) / len(durations) if durations else 0

        return {
            "total_tasks": len(total_tasks),
            "success_rate": success_count / len(total_tasks) if total_tasks else 0,
            "conflict_rate": conflicts / len(total_tasks) if total_tasks else 0,
            "gate_failure_rate": gate_failures / len(total_tasks) if total_tasks else 0,
            "avg_lead_time_sec": round(avg_lead_time, 2)
        }
# integrity-seal: 1776512137
