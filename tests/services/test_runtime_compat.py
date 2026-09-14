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
    assert runtime_compat._RUNTIME.CapabilityPlanner is CapabilityPlanner
    assert runtime_compat._RUNTIME.CanonicalPlanningBundle is CanonicalPlanningBundle
    assert runtime_compat._RUNTIME.CanonicalTaskContext is CanonicalTaskContext
    assert runtime_compat._RUNTIME.ExecutionReplanAuthorization is ExecutionReplanAuthorization
    assert runtime_compat._RUNTIME.plan_canonical_task_bundle is plan_canonical_task_bundle
    assert runtime_compat._RUNTIME.replan_canonical_task_bundle is replan_canonical_task_bundle


def test_mainchain_entry_uses_runtime_forwarder_source():
    from pathlib import Path

    source = Path("nexus/services/mainchain_entry.py").read_text(encoding="utf-8")
    assert "from nexus.services.runtime_compat import" in source
    assert "from nexus.services.unified_runtime import" not in source
