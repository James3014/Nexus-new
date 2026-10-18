"""Route-signal calibration after the BM25 findings search (#2640 review F1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
from nexus.research.flow.signal_collector import MAX_FINDINGS_HINT_CARDS, collect_route_signals


@pytest.fixture(autouse=True)
def _no_vector_sync(monkeypatch):
    monkeypatch.setenv("NEXUS_FINDINGS_LANCEDB_SYNC", "0")


def _signals(root: Path, task: str, store_cls=FindingsMemoryStore):
    return collect_route_signals(
        repo_root=root,
        task_desc=task,
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.9,
        findings_query=None,
        findings_memory_store_cls=store_cls,
    )


def test_generic_task_does_not_lower_confidence_through_unrelated_cards(tmp_path):
    store = FindingsMemoryStore(tmp_path)
    for index in range(11):
        store.write(
            FindingsCard(
                id=f"c{index}",
                kind="episodes",
                title=f"LocalHeal lesson: case-{index}",
                body="Local-heal outcome: correct_abstain Summary: MODEL_EMPTY_RESPONSE Memory trace status: missing",
                retrieval_hints=[f"case-{index}"],
            )
        )
    signals = _signals(tmp_path, "Fix the failing test in nexus/services/memory.py")
    assert signals["findings_hits"] == 0
    assert signals["adjusted_root_cause_confidence"] == pytest.approx(0.9)
    assert signals["historical_hints"] == []


def test_findings_hints_are_capped_to_top_cards(tmp_path):
    class _ManyHits:
        def __init__(self, _root):
            pass

        def search(self, _query):
            return [FindingsCard(id=f"h{i}", retrieval_hints=[f"hint-{i}"]) for i in range(8)]

    signals = _signals(tmp_path, "websocket timeout race", store_cls=_ManyHits)
    assert signals["findings_hits"] == 8
    assert signals["historical_hints"][:MAX_FINDINGS_HINT_CARDS] == ["hint-0", "hint-1", "hint-2"]
    assert not any(h in signals["historical_hints"] for h in ("hint-3", "hint-7"))
    assert signals["adjusted_root_cause_confidence"] == pytest.approx(0.75)
