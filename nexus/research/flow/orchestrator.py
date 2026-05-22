from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchFlowOrchestratorPolicy:
    max_recursion_depth: int = 1
    max_handoff_count: int = 1
    runtime_default_change_allowed: bool = False

    def to_receipt(self) -> dict[str, int | bool | str]:
        return {
            "schema": "nexus.research_flow_orchestrator_policy.v1",
            "max_recursion_depth": self.max_recursion_depth,
            "max_handoff_count": self.max_handoff_count,
            "runtime_default_change_allowed": self.runtime_default_change_allowed,
        }
