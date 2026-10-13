from __future__ import annotations


def test_runtime_compatibility_requires_installed_runtime():
    import importlib.util

    assert importlib.util.find_spec("nexus_runtime") is not None
    from nexus.services import runtime_compat

    assert runtime_compat.UnifiedRuntime is runtime_compat._RUNTIME.UnifiedRuntime
    assert runtime_compat.UnifiedRuntimeRequest is runtime_compat._RUNTIME.UnifiedRuntimeRequest


def test_runtime_compatibility_binds_complete_nexus_planner_family():
    from nexus.contracts.canonical_execution import CanonicalPlanningBundle, CanonicalTaskContext
    from nexus.engine.canonical_execution import (
        plan_canonical_task_bundle,
        replan_canonical_task_bundle,
    )
    from nexus.engine.capability_contracts import ExecutionReplanAuthorization
    from nexus.engine.capability_planner import CapabilityPlanner
    from nexus.services import runtime_compat

    assert runtime_compat.PLANNER_AUTHORITY_OWNER == "James3014/Nexus-new"
    assert len(runtime_compat.PLANNER_BINDING_SURFACES) == 6
    # Runtime wraps the (aliased) packaged planner so it carries the explicit shared_playbook root.
    bound = runtime_compat._RUNTIME.CapabilityPlanner
    assert issubclass(bound, CapabilityPlanner)
    assert bound.__qualname__ == CapabilityPlanner.__qualname__
    assert bound()._shared_playbook_root == runtime_compat.REPO_ROOT
    assert runtime_compat._RUNTIME.CanonicalPlanningBundle is CanonicalPlanningBundle
    assert runtime_compat._RUNTIME.CanonicalTaskContext is CanonicalTaskContext
    assert runtime_compat._RUNTIME.ExecutionReplanAuthorization is ExecutionReplanAuthorization
    # The exports bind the repository root, so the seam functions are root-bound wrappers.
    for exported, seam in (
        (runtime_compat._RUNTIME.plan_canonical_task_bundle, plan_canonical_task_bundle),
        (runtime_compat._RUNTIME.replan_canonical_task_bundle, replan_canonical_task_bundle),
    ):
        assert exported.__wrapped__ is seam


def test_mainchain_entry_uses_runtime_forwarder_source():
    from pathlib import Path

    source = Path("nexus/services/mainchain_entry.py").read_text(encoding="utf-8")
    assert "from nexus.services.runtime_compat import" in source
    assert "from nexus.services.unified_runtime import" not in source


def test_executor_resolver_registered_when_runtime_has_binding_seam(monkeypatch):
    import sys
    import types

    from nexus.core import capability_executor_registry
    from nexus.services import runtime_compat

    registered = []
    fake = types.ModuleType(runtime_compat._EXECUTOR_BINDING_MODULE)
    fake.register_executor_resolver = registered.append
    monkeypatch.setitem(sys.modules, runtime_compat._EXECUTOR_BINDING_MODULE, fake)

    assert runtime_compat.register_executor_resolver_if_available() is True
    assert registered == [runtime_compat._resolve_physical_executor]

    sentinel = object()
    seen = []
    monkeypatch.setattr(
        capability_executor_registry,
        "get_executor",
        lambda key: seen.append(key) or sentinel,
    )
    assert registered[0]("hyper_sprint") is sentinel
    assert seen == ["hyper_sprint"]


def test_executor_resolver_registration_is_silent_noop_without_binding_seam(monkeypatch):
    import sys

    from nexus.services import runtime_compat

    # A None entry makes the import raise ImportError, as with an older runtime pin.
    monkeypatch.setitem(sys.modules, runtime_compat._EXECUTOR_BINDING_MODULE, None)

    assert runtime_compat.register_executor_resolver_if_available() is False
