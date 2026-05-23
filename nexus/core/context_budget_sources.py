from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from nexus.contracts.context_budget import ContextBudgetSource


def estimate_context_tokens(value: Any) -> int:
    return max(1, int(len(str(value)) / 3.8))


def build_context_budget_sources(
    *,
    state: Any,
    l0_rules: str,
    l1_index: str,
    extra_sources: Sequence[ContextBudgetSource | Mapping[str, Any]] | None = None,
    token_estimator: Callable[[Any], int] = estimate_context_tokens,
) -> list[ContextBudgetSource | Mapping[str, Any]]:
    history = getattr(state, "metadata", {}).get("chat_history", []) if state is not None else []
    sources: list[ContextBudgetSource | Mapping[str, Any]] = [
        ContextBudgetSource("L0:rules", "L0", token_estimator(l0_rules), priority=0, required=True),
        ContextBudgetSource("L1:index", "L1", token_estimator(l1_index), priority=1, required=True),
    ]
    if history:
        sources.append(
            ContextBudgetSource(
                "history:recent",
                "history",
                token_estimator(str(history[-5:])),
                priority=20,
            )
        )
    sources.extend(extra_sources or [])
    return sources
