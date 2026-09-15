"""Compatibility forwarding surface for the independently installed runtime.

The runtime package is the implementation owner for execution coordination and
state symbols exposed here. Nexus-new remains the current Planner route/
capability authority and therefore injects the complete planner-domain family
explicitly. Resolution is eager so a missing dependency fails at startup instead
of silently selecting a legacy implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus_runtime import build_runtime_exports

from nexus.contracts.hybrid_route import hybrid_route_decision_from_payload
from nexus.services.capability_registry import build_real_executor_invoker
from nexus.services.local_heal.capability_adapter import advisory_route_from_local_response
from nexus.services.local_heal.memory_retrieval_adapter import (
    FindingsMemoryLessonStore,
    LocalJsonlLessonStore,
    MemoryRepositoryLessonStore,
    MemoryRetrievalAdapter,
    NexusCompositeLessonStore,
)

PLANNER_AUTHORITY_OWNER = "James3014/Nexus-new"
PLANNER_BINDING_SURFACES = (
    "nexus.engine.capability_planner.CapabilityPlanner",
    "nexus.contracts.canonical_execution.CanonicalPlanningBundle",
    "nexus.contracts.canonical_execution.CanonicalTaskContext",
    "nexus.engine.capability_contracts.ExecutionReplanAuthorization",
    "nexus.engine.canonical_execution.plan_canonical_task_bundle",
    "nexus.engine.canonical_execution.replan_canonical_task_bundle",
)

# ProjectMemoryManager remains a host capability. Supply its existing physical
# executor explicitly; the independent runtime never imports this host module.


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
    """Build Runtime with one complete Nexus-new-owned planner-domain binding.

    The six planner-domain symbols are intentionally injected as one family.
    Runtime executes the resulting plan but does not become a second route/
    capability authority merely because it hosts execution coordination.
    """
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


__all__ = [
    "build_runtime_exports",
    "PLANNER_AUTHORITY_OWNER",
    "PLANNER_BINDING_SURFACES",
    *_RUNTIME.names(),
]
