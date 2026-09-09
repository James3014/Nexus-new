from __future__ import annotations

from nexus.core.context_hub import ContextDependencies, ContextHub


def test_context_hub_binds_policy_handoff_and_snapshot_compactor(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    deps = hub.runtime_hub.deps
    assert callable(deps.policy_reader)
    assert callable(deps.handoff_reader)
    snapshot = {"task_id": "task-1", "tasks": {}}
    compacted = deps.compactor(snapshot, confidence=0.5)
    assert isinstance(compacted, dict)


def test_context_hub_context_uses_public_runtime_entry(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    result = hub.assemble_context("task-1", [0, 1], budget=4000)
    assert isinstance(result, str)
