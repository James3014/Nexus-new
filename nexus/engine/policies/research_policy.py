from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchDecision:
    should_research: bool
    mode: str  # "skip" | "external" | "experimental"
    reason: str
    rounds: int
    stable_wins: int


class ResearchPolicy:
    def __init__(self, fast_mode: bool = False):
        self.fast_mode = fast_mode
        self.trigger_keywords = ["SDK", "WEBSOCKET", "API", "CLOUD", "AWS"]
        self.experimental_keywords = ["PERF", "LATENCY", "OPTIMIZE", "FLAKY", "RACE", "THROUGHPUT"]

    def route(
        self,
        decision: Dict[str, Any],
        task_desc: str,
        *,
        task_type: str = "bug",
        prediction: Dict[str, Any] | None = None,
        context: Dict[str, Any] | None = None,
    ) -> ResearchDecision:
        ctx = context or {}
        pred = prediction or {}
        task_upper = (task_desc or "").upper()

        if bool(ctx.get("benchmark_force_research")):
            return ResearchDecision(
                should_research=True,
                mode="experimental" if bool(ctx.get("research_workspace")) else "external",
                reason="benchmark_force_research",
                rounds=int(ctx.get("research_rounds", 5) or 5),
                stable_wins=int(ctx.get("research_stable_wins", 3) or 3),
            )

        if self.fast_mode:
            return ResearchDecision(False, "skip", "fast_mode", 0, 0)

        if bool(ctx.get("research_force")):
            return ResearchDecision(
                True,
                "experimental" if bool(ctx.get("research_workspace")) else "external",
                "context_research_force",
                int(ctx.get("research_rounds", 5) or 5),
                int(ctx.get("research_stable_wins", 3) or 3),
            )

        if bool(decision.get("external_needed")):
            return ResearchDecision(True, "external", "external_needed", 5, 1)

        if any(kw in task_upper for kw in self.experimental_keywords):
            mode = "experimental" if bool(ctx.get("research_workspace")) else "external"
            return ResearchDecision(True, mode, "performance_or_flaky_task", 5, 3)

        if any(kw in task_upper for kw in self.trigger_keywords):
            return ResearchDecision(True, "external", "keyword_trigger", 5, 1)

        candidate_count = int(pred.get("candidate_count", 1) or 1)
        root_cause_confidence = float(pred.get("root_cause_confidence", 1.0) or 1.0)
        if candidate_count > 1 or root_cause_confidence < 0.75:
            mode = "experimental" if bool(ctx.get("research_workspace")) else "external"
            return ResearchDecision(True, mode, "multi_candidate_or_low_confidence", 5, 3)

        if task_type == "feature":
            return ResearchDecision(True, "external", "feature_default_research", 3, 1)

        return ResearchDecision(False, "skip", "clear_root_cause", 0, 0)

    def should_research(self, decision: Dict[str, Any], task_desc: str) -> bool:
        """Backward-compatible boolean check for older call sites."""
        return self.route(decision, task_desc).should_research
