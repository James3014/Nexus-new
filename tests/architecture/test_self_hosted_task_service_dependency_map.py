"""Drift guard for the Phase 5b-0 self_hosted_task_service dependency map."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "scripts" / "ops" / "self_hosted_task_service_dependency_map.py"
COMMITTED = REPO_ROOT / "docs" / "plans" / "self_hosted_task_service_dependency_map.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("_sht_dependency_map_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_dependency_map_matches_regenerated() -> None:
    tool = _load_tool()
    regenerated = tool.render(tool.build_map(REPO_ROOT))
    assert COMMITTED.read_text(encoding="utf-8") == regenerated, (
        "docs/plans/self_hosted_task_service_dependency_map.json drifted; regenerate with "
        "`python scripts/ops/self_hosted_task_service_dependency_map.py`"
    )


def test_runtime_candidate_cluster_is_non_empty() -> None:
    data = json.loads(COMMITTED.read_text(encoding="utf-8"))
    runtime = data["clusters"]["runtime_candidate"]
    assert runtime["count"] > 0
    assert runtime["total_lines"] > 0
    assert runtime["definitions"]
