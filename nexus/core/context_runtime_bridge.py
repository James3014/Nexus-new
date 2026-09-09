"""Build the canonical runtime ContextHub from Nexus-new service injections."""

from __future__ import annotations

from typing import Any, Callable

from nexus_runtime import ContextHub as RuntimeContextHub
from nexus_runtime import ContextHubDependencies as RuntimeContextHubDependencies


def build_runtime_context_hub(
    *,
    state_reader: Callable[[], Any],
    text_reader: Callable[..., str],
    memory_service: Any = None,
    nexus_fs: Any = None,
    wiki_knowledge_agent: Any = None,
    knowledge_reader: Any = None,
    renderer: Callable[..., str] | None = None,
    dialogue_pruner: Callable[[Any], Any] | None = None,
    compactor: Callable[..., dict[str, Any]] | None = None,
    learning_writer: Callable[..., Any] | None = None,
    clock: Callable[[], Any] | None = None,
) -> RuntimeContextHub:
    """Adapt legacy service objects into the runtime's explicit callable ports."""

    def memory_reader(phase: str) -> dict[str, Any]:
        if memory_service is not None and hasattr(memory_service, "cached_search"):
            return dict(memory_service.cached_search(f"memory_v9_{phase}"))
        if nexus_fs is not None and hasattr(nexus_fs, "search"):
            return {"reminders": nexus_fs.search(f"memory_v9_{phase}"), "total_sources": -1}
        return {"reminders": [], "total_sources": 0}

    def wiki_reader(query: str, max_results: int = 3) -> dict[str, Any]:
        if wiki_knowledge_agent is not None:
            for method in ("retrieve", "search", "query"):
                fn = getattr(wiki_knowledge_agent, method, None)
                if callable(fn):
                    return dict(fn(query, max_results=max_results))
        return {"context": "", "selected_sources": []}

    deps = RuntimeContextHubDependencies(
        state_reader=state_reader,
        text_reader=text_reader,
        memory_reader=memory_reader,
        wiki_reader=wiki_reader,
        renderer=renderer or (lambda _state, aggression=0.0: ""),
        dialogue_pruner=dialogue_pruner or (lambda history: history),
        compactor=compactor or (lambda value, confidence=0.5: dict(value)),
        knowledge_reader=knowledge_reader,
        learning_writer=learning_writer,
        clock=clock,
    )
    return RuntimeContextHub(deps=deps, strict_deps=True)
