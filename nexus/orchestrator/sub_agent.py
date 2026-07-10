from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubAgent:
    subagent_id: str
    definition: str
    created_at: float = 0.0
    last_action: str = ""
    trace_history: list[str] = field(default_factory=list)


class SubAgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, SubAgent] = {}

    def register(self, agent: SubAgent) -> None:
        agent.created_at = agent.created_at or time.time()
        self._agents[agent.subagent_id] = agent

    def get(self, subagent_id: str) -> SubAgent | None:
        return self._agents.get(subagent_id)

    def list_ids(self) -> list[str]:
        return list(self._agents.keys())
