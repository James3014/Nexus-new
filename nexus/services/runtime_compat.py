"""Compatibility forwarding surface for the independently installed runtime.

The runtime package is the sole implementation owner for these execution
symbols.  Resolution is intentionally eager so a missing dependency fails at
startup instead of silently selecting the legacy implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus_runtime import build_runtime_exports

from nexus.contracts.hybrid_route import hybrid_route_decision_from_payload

# ProjectMemoryManager remains a host capability. Supply its existing physical
# executor explicitly; the independent runtime never imports this host module.
from nexus.services.capability_registry import build_real_executor_invoker
from nexus.services.local_heal.capability_adapter import advisory_route_from_local_response
from nexus.services.local_heal.memory_retrieval_adapter import (
    FindingsMemoryLessonStore,
    LocalJsonlLessonStore,
    MemoryRepositoryLessonStore,
    MemoryRetrievalAdapter,
    NexusCompositeLessonStore,
)


def _build_default_memory_retrieval_adapter(project_root: str | Path) -> Any:
    root = Path(project_root).expanduser().resolve()
    return MemoryRetrievalAdapter(
        store=NexusCompositeLessonStore([
            LocalJsonlLessonStore(
                path=root / ".nexus" / "reports" / "learn" / "learning_closure.jsonl"
            ),
            FindingsMemoryLessonStore(project_root=root),
            MemoryRepositoryLessonStore(project_root=root),
        ])
    )


_MEMORY_INVOKER = build_real_executor_invoker("memory")


def build_host_runtime_exports():
    """Build the consumer runtime with all existing host capability bindings."""
    from nexus.contracts.canonical_execution import CanonicalPlanningBundle, CanonicalTaskContext
    from nexus.engine.canonical_execution import (
        plan_canonical_task_bundle,
        replan_canonical_task_bundle,
    )
    from nexus.engine.capability_contracts import ExecutionReplanAuthorization
    from nexus.engine.capability_planner import CapabilityPlanner

    return build_runtime_exports(
        online_context_projection=False,
        planner_factory=CapabilityPlanner,
        canonical_planning_bundle_factory=CanonicalPlanningBundle,
        canonical_task_context_factory=CanonicalTaskContext,
        execution_replan_authorization_factory=ExecutionReplanAuthorization,
        plan_canonical_task_bundle_factory=plan_canonical_task_bundle,
        replan_canonical_task_bundle_factory=replan_canonical_task_bundle,
        policy_path=Path(__file__).resolve().parents[1] / "config" / "model_workforce.yaml",
        advisory_route_from_local_response=advisory_route_from_local_response,
        hybrid_route_decision_from_payload=hybrid_route_decision_from_payload,
        memory_retrieval_builder=_build_default_memory_retrieval_adapter,
        default_capability_invokers=(
            {"memory": _MEMORY_INVOKER} if _MEMORY_INVOKER is not None else {}
        ),
    )


_RUNTIME = build_host_runtime_exports()


def __getattr__(name: str):
    try:
        return getattr(_RUNTIME, name)
    except AttributeError as exc:
        raise AttributeError(f"runtime compatibility symbol unavailable: {name}") from exc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_RUNTIME.names()))


__all__ = ["build_runtime_exports", *_RUNTIME.names()]
