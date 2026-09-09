"""Real host SQLite search through the installed runtime's compatibility facade."""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from nexus.core.memory_manager import ProjectMemoryManager
from nexus.services import runtime_compat
from nexus.services.unified_runtime import UnifiedRuntime
from tests.services.test_unified_runtime import _Planner, _request


def run_memory(root=None, *, query="needle", overrides=None):
    request = _request(local_enabled=False, online_enabled=False)
    route = dict(request.route)
    if root is not None:
        route["workspace_root"] = str(root)
    request = replace(request, task_statement=query, route=route)
    receipt = UnifiedRuntime(planner=_Planner()).run(request, capability_invokers=overrides)
    return receipt["capability_results"]["memory"]


def test_real_sqlite_memory_search_reads_persisted_insights_and_caps_hits(tmp_path):
    manager = ProjectMemoryManager(tmp_path)
    for i in range(7):
        manager.add_insight(f"topic-{i}", f"needle-{i}", "RCA")
    assert len(ProjectMemoryManager(tmp_path).search("needle")) == 7
    stage = run_memory(tmp_path, overrides={})
    assert stage["status"] == "SUCCEEDED" and stage["invoked"] is True
    assert stage["physical_callable"] == "capability_executor_registry:memory"
    outcome = stage["response"]["response"]["outcome"]
    assert outcome["semantic_status"] == "SUCCEEDED"
    assert outcome["search_performed"] is True
    assert outcome["hit_count"] == 5
    assert outcome["result"] == {"hit_count": 5, "root": str(tmp_path.resolve())}
    assert outcome["physical_callable"] == "nexus.core.memory_manager.ProjectMemoryManager.search"
    assert stage["telemetry"]["wall_time_ms"] >= 0


def test_missing_root_is_invoked_failed_memory_not_a_skip():
    stage = run_memory()
    assert stage["status"] == "FAILED" and stage["invoked"] is True
    assert stage["skipped"] is False
    outcome = stage["response"]["response"]["outcome"]
    assert outcome["semantic_status"] == "BLOCKED"
    assert outcome["error"] == "PROJECT_MEMORY_CONTEXT_REQUIRED"
    assert outcome["search_performed"] is False


def test_missing_query_denies_before_creating_project_database(tmp_path):
    result = runtime_compat._MEMORY_INVOKER(
        {"task_id": "empty-query", "workspace_root": str(tmp_path), "task_statement": ""}
    )
    assert result["invoked"] is True and result["gate_passed"] is False
    assert result["response"]["outcome"]["error"] == "PROJECT_MEMORY_CONTEXT_REQUIRED"
    assert not (tmp_path / ".nexus").exists()


def test_real_memory_search_exception_is_not_invoked_success(tmp_path, monkeypatch):
    def failure(self, query):
        raise RuntimeError("sqlite read fault")

    monkeypatch.setattr(ProjectMemoryManager, "search", failure)
    stage = run_memory(tmp_path)
    assert stage["status"] == "FAILED" and stage["invoked"] is False
    assert stage["gate_passed"] is False
    assert "sqlite read fault" in str(stage["response"])


def test_per_run_memory_override_wins_without_mutating_mapping(tmp_path):
    seen = []

    def custom(context):
        seen.append(context["task_id"])
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": False,
            "evidence_refs": ["override:denial"],
        }

    mapping = {"memory": custom}
    stage = run_memory(tmp_path, overrides=mapping)
    assert seen and stage["status"] == "FAILED"
    assert mapping == {"memory": custom}
    assert not (tmp_path / ".nexus").exists()


@pytest.mark.parametrize(
    "first,second",
    [
        ("nexus.services.runtime_compat", "nexus.services.unified_runtime"),
        ("nexus.services.unified_runtime", "nexus.services.runtime_compat"),
    ],
)
def test_compatibility_import_order_binds_real_memory_without_cycle(first, second):
    code = f"import {first}; import {second}; from nexus.services.runtime_compat import _RUNTIME, _MEMORY_INVOKER; assert callable(_MEMORY_INVOKER); assert _RUNTIME.UnifiedRuntime.__module__.startswith('nexus_runtime')"
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
