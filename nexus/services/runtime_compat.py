"""Compatibility forwarding surface for the independently installed runtime.

The runtime package is the implementation owner for execution coordination and
state symbols exposed here. Nexus-new remains the current Planner route/
capability authority; the planner-domain modules under ``nexus.*`` are aliases
of the runtime copies, so only the explicit shared-playbook root is injected. Resolution is eager so a missing dependency fails at startup instead
of silently selecting a legacy implementation.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from nexus_runtime import build_runtime_exports

from nexus.contracts.hybrid_route import hybrid_route_decision_from_payload
from nexus.core.repo_root import REPO_ROOT
from nexus.services.capability_registry import (
    build_real_executor_invoker,
    clear_executor_resolution_errors_for_key,
    record_executor_resolution_error_for_key,
)
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
    """Build Runtime with the packaged planner family plus host-owned inputs.

    The planner-domain modules under ``nexus.*`` are aliases of the runtime
    modules (D2), so no planner factory needs injecting; the host supplies the
    explicit shared-playbook root, policy path and capability adapters.
    """
    return build_runtime_exports(
        online_context_projection=False,
        shared_playbook_root=REPO_ROOT,
        policy_path=Path(__file__).resolve().parents[1] / "config" / "model_workforce.yaml",
        advisory_route_from_local_response=advisory_route_from_local_response,
        hybrid_route_decision_from_payload=hybrid_route_decision_from_payload,
        memory_retrieval_builder=_build_default_memory_retrieval_adapter,
        default_capability_invokers=(
            {"memory": _MEMORY_INVOKER} if _MEMORY_INVOKER is not None else {}
        ),
    )


_EXECUTOR_BINDING_MODULE = "nexus_runtime.support.services.executor_binding"
RUNTIME_SEAM_RESOLVER_ORIGIN = (
    "nexus.services.runtime_compat._resolve_physical_executor"
    " via nexus_runtime.support.services.executor_binding"
)


def _resolve_physical_executor(key: str) -> Any | None:
    # Lazy: the executor registry imports most of the host, so import on first call.
    try:
        from nexus.core.capability_executor_registry import get_executor

        executor = get_executor(key)
    except Exception as exc:
        # The runtime's ``_has_physical_executor`` turns a raise into False, and its
        # invoker build lets it abort the run.  Record the reason first (under the
        # capability names, not only the registry key) so it is observable, then keep
        # the runtime's contract (re-raise).
        record_executor_resolution_error_for_key(key, exc, origin=RUNTIME_SEAM_RESOLVER_ORIGIN)
        raise
    clear_executor_resolution_errors_for_key(key)
    return executor


def register_executor_resolver_if_available() -> bool:
    """Register the host executor registry with the runtime's executor seam.

    A no-op returning False when the installed runtime predates the seam.
    """
    try:
        binding = importlib.import_module(_EXECUTOR_BINDING_MODULE)
    except ImportError:
        return False
    binding.register_executor_resolver(_resolve_physical_executor)
    return True


register_executor_resolver_if_available()


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


if __name__ == "__main__":
    import sys

    # ``python -m nexus.services.runtime_compat --check-executors``: reuse this
    # already-bootstrapped module instead of importing (and building) it twice.
    sys.modules.setdefault("nexus.services.runtime_compat", sys.modules[__name__])
    if "--check-executors" not in sys.argv[1:]:
        sys.exit("usage: python -m nexus.services.runtime_compat --check-executors [--json]")
    from nexus.services.executor_self_check import main as _check_executors

    sys.exit(_check_executors(sys.argv[1:]))
