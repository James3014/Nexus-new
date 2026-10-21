"""Modules with no production caller warn on import; production paths do not (#1740)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

LAB_ONLY = [
    "nexus.core.planner_auditor",
    "nexus.memory",
    "nexus.core.capability_gate",
    "nexus.engine.replay_runner",
    "nexus.benchmark.benchmark_runner",
    "nexus.services.aos_oracle",
    "nexus.federation.fleet_manager",
]

# Lab-only, then physically deleted 2026-10-17 (#2475, dead-code batch B4,
# ARCHIVED_2026-10-17_deadcode_b4.md). The case keeps its test id and asserts the
# module can no longer be imported.
# nexus.core.planner_auditor followed on 2026-10-21 (#2584, Phase-2 batch B,
# ARCHIVED_2026-10-21_phase2_batch_B.md).
DELETED = frozenset({"nexus.services.aos_oracle", "nexus.core.planner_auditor"})


def _import_warnings(module: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-W", "always::DeprecationWarning", "-c", f"import {module}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stderr


@pytest.mark.parametrize("module", LAB_ONLY)
def test_lab_only_module_warns_on_import(module):
    if module in DELETED:
        assert importlib.util.find_spec(module) is None, f"{module} was deleted (#2475/#2584)"
        return
    assert "#1740" in _import_warnings(module)


def test_production_entry_points_do_not_import_lab_only_modules():
    stderr = _import_warnings("scripts.engine.nexus_cli")
    stderr += _import_warnings("nexus.governance.capability_gate")
    assert "#1740" not in stderr
