from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActionTrace:
    subagent_id: str
    step: int
    action: str
    result: str
    timestamp: float


@dataclass(frozen=True)
class ForkReceipt:
    subagent_id: str
    old_definition: str
    new_definition: str
    fork_id: str
    timestamp: float


class ShepherdSupervisor:
    def __init__(self, max_forks: int = 3) -> None:
        self._max_forks = max_forks
        self._fork_log: list[ForkReceipt] = []
        self._traces: dict[str, list[ActionTrace]] = {}

    def fork(self, subagent_id: str, new_definition: str) -> ForkReceipt:
        old_definition = ""
        receipt = ForkReceipt(
            subagent_id=subagent_id,
            old_definition=old_definition,
            new_definition=new_definition,
            fork_id=str(uuid.uuid4()),
            timestamp=time.time(),
        )
        self._fork_log.append(receipt)
        return receipt

    def observe(self, subagent_id: str) -> ActionTrace | None:
        traces = self._traces.get(subagent_id)
        if not traces:
            return None
        return traces[-1]

    def replay_to(self, subagent_id: str, step: int) -> list[ActionTrace]:
        traces = self._traces.get(subagent_id, [])
        return [t for t in traces if t.step <= step]

    def record_trace(self, trace: ActionTrace) -> None:
        self._traces.setdefault(trace.subagent_id, []).append(trace)
