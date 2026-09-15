"""Build the canonical runtime ContextHub from Nexus-new service injections."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, cast

from nexus_runtime import ContextHub as RuntimeContextHub
from nexus_runtime import ContextHubDependencies as RuntimeContextHubDependencies
from nexus_runtime.context_hub.ports import (
    DialoguePruner,
    MemoryReader,
    Renderer,
    WikiReader,
)

from nexus.core.context_compactor import ContextCompactor


def build_runtime_context_hub(
    *,
    project_root: str | Path = ".",
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
    policy_reader: Callable[[], Any] | None = None,
    handoff_reader: Callable[[], Any] | None = None,
    memory_reader: Callable[[str], dict[str, Any]] | None = None,
    wiki_reader: Callable[..., dict[str, Any]] | None = None,
) -> RuntimeContextHub:
    """Adapt legacy service objects into the runtime's explicit callable ports."""

    def default_memory_reader(phase: str) -> dict[str, Any]:
        if memory_service is not None and hasattr(memory_service, "cached_search"):
            return dict(memory_service.cached_search(f"memory_v9_{phase}"))
        if nexus_fs is not None and hasattr(nexus_fs, "search"):
            return {"reminders": nexus_fs.search(f"memory_v9_{phase}"), "total_sources": -1}
        return {"reminders": [], "total_sources": 0}

    def default_wiki_reader(query: str, max_results: int = 3) -> dict[str, Any]:
        if wiki_knowledge_agent is not None:
            for method in ("retrieve", "search", "query"):
                fn = getattr(wiki_knowledge_agent, method, None)
                if callable(fn):
                    return dict(cast(Mapping[str, Any], fn(query, max_results=max_results)))
        return {"context": "", "selected_sources": []}

    deps = RuntimeContextHubDependencies(
        state_reader=state_reader,
        text_reader=text_reader,
        memory_reader=cast(MemoryReader, memory_reader or default_memory_reader),
        wiki_reader=cast(WikiReader, wiki_reader or default_wiki_reader),
        renderer=cast(Renderer, renderer or (lambda _state, aggression=0.0: "")),
        dialogue_pruner=cast(DialoguePruner, dialogue_pruner or (lambda history: history)),
        compactor=compactor or _build_compactor(project_root, state_reader),
        knowledge_reader=knowledge_reader,
        learning_writer=learning_writer,
        clock=clock,
        policy_reader=policy_reader,
        handoff_reader=handoff_reader,
    )
    return RuntimeContextHub(deps=deps, strict_deps=True)


def build_legacy_learning_writer(
    project_root: str | Path, run_dir: str | Path | None = None
) -> Callable[..., Any]:
    """Adapt the historical FindingsMemoryStore lesson writer to runtime."""
    from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore

    def write(
        *,
        failure_signature: str,
        root_cause: str,
        lesson: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        metadata = dict(metadata or {})
        card = FindingsCard(
            task_id=metadata.get("task_id", failure_signature),
            kind="episodes",
            title=f"Failure: {failure_signature}",
            scope="task",
            tags=["failure-analysis", failure_signature.split(":")[0]],
            stage="unknown",
            confidence="high",
            body=f"Root Cause: {root_cause}\nLesson: {lesson}",
            evidence_paths=[str(run_dir)] if run_dir else [],
            extra=metadata,
        )
        return FindingsMemoryStore(Path(project_root)).write(card)

    return write


def _build_compactor(
    project_root: str | Path, state_reader: Callable[[], Any]
) -> Callable[..., dict[str, Any]]:
    def compact(value: dict[str, Any], confidence: float = 0.5) -> dict[str, Any]:
        return ContextCompactor(Path(project_root)).compact(value, confidence=confidence)

    return compact
