from __future__ import annotations

from types import SimpleNamespace

from nexus.contracts.context_budget import ContextBudgetSource
from nexus.core.context_budget_sources import build_context_budget_sources, estimate_context_tokens


def test_context_budget_sources_preserve_l0_l1_and_recent_history_order() -> None:
    state = SimpleNamespace(metadata={"chat_history": ["a", "b", "c", "d", "e", "f"]})

    sources = build_context_budget_sources(
        state=state,
        l0_rules="root rules",
        l1_index="task index",
        extra_sources=[{"source_id": "research:x", "kind": "research", "estimated_tokens": 9, "priority": 10}],
    )

    assert [source.source_id if isinstance(source, ContextBudgetSource) else source["source_id"] for source in sources] == [
        "L0:rules",
        "L1:index",
        "history:recent",
        "research:x",
    ]
    assert sources[0] == ContextBudgetSource(
        "L0:rules",
        "L0",
        estimate_context_tokens("root rules"),
        priority=0,
        required=True,
    )
    assert sources[1] == ContextBudgetSource(
        "L1:index",
        "L1",
        estimate_context_tokens("task index"),
        priority=1,
        required=True,
    )
    assert isinstance(sources[2], ContextBudgetSource)
    assert sources[2].kind == "history"
    assert sources[2].estimated_tokens == estimate_context_tokens(str(["b", "c", "d", "e", "f"]))


def test_context_budget_sources_use_injected_token_estimator() -> None:
    sources = build_context_budget_sources(
        state=SimpleNamespace(metadata={}),
        l0_rules="root rules",
        l1_index="task index",
        token_estimator=lambda value: len(str(value)) + 100,
    )

    assert [source.estimated_tokens for source in sources] == [110, 110]
