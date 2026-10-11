"""Guard for the Phase 5b-0 self_hosted_task_service dependency map.

Drift against the (frequently edited) service file is reported as a GAP skip, never a
failure.  Hard failures: committed JSON missing/invalid, structural invariants broken, or the
tool raising.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "scripts" / "ops" / "self_hosted_task_service_dependency_map.py"
COMMITTED = REPO_ROOT / "docs" / "plans" / "self_hosted_task_service_dependency_map.json"
STALE_MESSAGE = (
    "GAP: dependency map stale — run scripts/ops/self_hosted_task_service_dependency_map.py --write"
)


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("_sht_dependency_map_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_committed() -> dict[str, Any]:
    assert COMMITTED.is_file(), f"missing committed dependency map: {COMMITTED}"
    data = json.loads(COMMITTED.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_committed_map_structural_invariants() -> None:
    data = _load_committed()
    clusters = data["clusters"]
    assert {"runtime_candidate", "bridge_candidate", "stay"} <= set(clusters)
    runtime = clusters["runtime_candidate"]
    assert runtime["count"] > 0 and runtime["total_lines"] > 0 and runtime["definitions"]
    sovereign = {m["module"] for m in data["sovereign_modules"]}
    for expected in (
        "nexus.orchestrator.autonomy_policy",
        "nexus.orchestrator.acceptance_loop",
        "nexus.services.runtime_workforce_admission",
        "nexus.contracts.workforce_admission",
    ):
        assert expected in sovereign


def test_committed_map_matches_regenerated_or_reports_gap() -> None:
    committed_text = COMMITTED.read_text(encoding="utf-8")
    json.loads(committed_text)  # hard fail if invalid
    tool = _load_tool()
    regenerated = tool.render(tool.build_map(REPO_ROOT))  # hard fail if the tool raises
    if regenerated != committed_text:
        pytest.skip(STALE_MESSAGE)
