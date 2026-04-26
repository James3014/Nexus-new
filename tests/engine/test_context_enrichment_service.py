from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.context_enrichment_service import ContextEnrichmentService


def test_context_enrichment_service_writes_sota_and_diagnose_context():
    sota = MagicMock()
    aggregator = MagicMock()
    sota.search.return_value = {"data": ["pattern-a", "pattern-b"]}
    aggregator.triage_summarize.return_value = "condensed-context"

    svc = ContextEnrichmentService(sota_searcher=sota, neural_aggregator=aggregator)
    state = NexusState(task_id="ctx-1")
    state.metadata["task_description"] = "fix flaky test"
    state.metadata["domain"] = "python"
    state.metadata["history_events"] = [{"type": "fail"}]

    out = svc.run(state=state)

    assert out["sota_patterns"] == ["pattern-a", "pattern-b"]
    assert out["diagnose_context"] == "condensed-context"
    assert state.metadata["sota_patterns"] == ["pattern-a", "pattern-b"]
    assert state.metadata["diagnose_context"] == "condensed-context"
    sota.search.assert_called_once_with("fix flaky test", "python")
    aggregator.triage_summarize.assert_called_once_with([{"type": "fail"}])
