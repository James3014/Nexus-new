from __future__ import annotations

from typing import Any


class ContextEnrichmentService:
    """SOTA anchoring + diagnose context triage extraction."""

    def __init__(self, *, sota_searcher: Any, neural_aggregator: Any):
        self.sota_searcher = sota_searcher
        self.neural_aggregator = neural_aggregator

    def run(self, *, state: Any) -> dict[str, Any]:
        task_desc = str(state.metadata.get("task_description", ""))
        domain = str(state.metadata.get("domain", "general"))
        history = state.metadata.get("history_events", [])

        sota_result = self.sota_searcher.search(task_desc, domain)
        state.metadata["sota_patterns"] = sota_result.get("data")

        condensed_context = self.neural_aggregator.triage_summarize(history)
        state.metadata["diagnose_context"] = condensed_context

        return {
            "sota_patterns": state.metadata.get("sota_patterns"),
            "diagnose_context": condensed_context,
        }
