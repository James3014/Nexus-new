from typing import Dict, Any, List, Optional
from datetime import datetime
from nexus.orchestrator.event_logger import EventLogger

class MetricsAggregator:
    """Aggregate multi-agent orchestrator events (events.jsonl) into task-level metrics.

    Every rate is a per-task ratio in [0, 1] over ``total_tasks`` (distinct task ids
    seen in events). When there are no tasks the rates are ``None`` (rendered "N/A"),
    never 0 or 1.

    Event producers (nexus/orchestrator/orchestrator.py): TASK_CREATE, TASK_START,
    TASK_CONFLICT, GATE_PASS / GATE_FAILURE (verify_task) and TASK_CLOSE (close_task).

    Definitions:
    - success: a task whose final gate outcome is GATE_PASS (its last GATE_* event)
      and that was then closed (TASK_CLOSE). TASK_CLOSE alone is NOT success: close_task
      also runs for failed/abandoned tasks, so a close after gate failures with no
      passing verify is a failure.
    - gate_failure_rate: tasks with >= 1 GATE_FAILURE / tasks (not events / tasks).
      The raw event count is reported separately as ``gate_failure_events``.
    - conflict_rate: tasks with >= 1 TASK_CONFLICT / tasks (raw count: ``conflict_events``).
    """

    def __init__(self, logger: EventLogger):
        self.logger = logger

    def compute_metrics(self) -> Dict[str, Any]:
        events = self.logger.get_events()

        task_starts: Dict[str, datetime] = {}
        task_ends: Dict[str, datetime] = {}
        last_gate: Dict[str, str] = {}
        conflict_tasks: set = set()
        gate_failure_tasks: set = set()
        conflict_events = 0
        gate_failure_events = 0
        total_tasks: set = set()

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
            elif etype == "TASK_CONFLICT":
                conflict_events += 1
                conflict_tasks.add(tid)
            elif etype == "GATE_FAILURE":
                gate_failure_events += 1
                gate_failure_tasks.add(tid)
                last_gate[tid] = etype
            elif etype == "GATE_PASS":
                last_gate[tid] = etype

        success_tasks = {
            tid for tid in task_ends if last_gate.get(tid) == "GATE_PASS"
        }

        # Calculate durations
        durations = []
        for tid, start_time in task_starts.items():
            if tid in task_ends:
                durations.append((task_ends[tid] - start_time).total_seconds())

        avg_lead_time = sum(durations) / len(durations) if durations else 0

        n = len(total_tasks)

        def _rate(count: int) -> Optional[float]:
            return count / n if n else None

        return {
            "total_tasks": n,
            "success_rate": _rate(len(success_tasks)),
            "conflict_rate": _rate(len(conflict_tasks)),
            "gate_failure_rate": _rate(len(gate_failure_tasks)),
            "successful_tasks": len(success_tasks),
            "gate_failure_events": gate_failure_events,
            "conflict_events": conflict_events,
            "avg_lead_time_sec": round(avg_lead_time, 2)
        }
# integrity-seal: 1776512137
