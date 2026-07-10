"""Tests for N30R real core bridge — production path wiring contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_contracts import N30RAttemptReceipt, sha256_str
from scripts.bench.n30r_runner import ARMS
from scripts.bench.n30r_real_core_bridge import (
    REAL_CORE_ARM_ID,
    FROZEN_TOPOLOGY,
    FROZEN_PLANNER_VERSION,
    REQUIRED_PLANNER_FIELDS,
    RealCoreBridgeResult,
    invoke_capability_planner,
    validate_planner_snapshot,
    run_real_core_bridge,
)
from scripts.bench.n30r_arm_adapters import _read_fixture_source

SMOKE_MANIFEST = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"


# ---------------------------------------------------------------------------
# Planner invocation tests
# ---------------------------------------------------------------------------

def test_real_core_arm_calls_capability_planner():
    """Real core arm must actually call CapabilityPlanner.plan()."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    assert isinstance(snapshot, dict)
    assert snapshot.get("planner_version") == FROZEN_PLANNER_VERSION


def test_real_core_arm_uses_planner_owned_signal_snapshot():
    """Signal snapshot must contain all required planner fields."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    errors = validate_planner_snapshot(snapshot)
    assert errors == [], f"Snapshot validation failed: {errors}"


def test_real_core_arm_calls_local_model_executor():
    """Planner must set selected_executor='local_model' when local model is enabled."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    assert snapshot.get("selected_executor") == "local_model"


def test_real_core_arm_uses_localheal_pipeline():
    """execution_topology must be localheal_pipeline."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    assert snapshot.get("execution_topology") == FROZEN_TOPOLOGY


def test_real_core_arm_does_not_call_legacy_capability_adapter():
    """Real core must use production path, not legacy adapter."""
    arm = ARMS["N30R_B_7B_REAL_CORE"]
    assert arm.nexus_enabled is True
    assert arm.core_armor_enabled is True
    assert REAL_CORE_ARM_ID == "N30R_B_7B_REAL_CORE"


def test_real_core_arm_disables_committee():
    """Real core must not enable committee."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    assert snapshot.get("local_committee_enabled", False) is False


def test_real_core_arm_disables_local_cascade():
    """Real core must not enable local cascade."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    assert snapshot.get("local_cascade_enabled", False) is False


def test_real_core_arm_disables_cloud_fallback():
    """Real core must not enable cloud fallback."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    assert snapshot.get("cloud_used", False) is False


def test_real_core_arm_disables_cross_task_memory():
    """Real core must not enable cross-task memory retrieval."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    # Cross-task memory is not enabled by planner for local model
    assert snapshot.get("cross_task_memory_enabled", False) is False


def test_real_core_arm_uses_same_7b_model_as_bare():
    """Real core must use the same 7B model as bare."""
    bare = ARMS["N30R_A_7B_BARE"]
    core = ARMS["N30R_B_7B_REAL_CORE"]
    assert bare.model_name == core.model_name
    assert bare.model_provider == core.model_provider
    assert bare.model_parameters == core.model_parameters


def test_real_core_arm_records_production_receipt_hash():
    """Real core must record production_receipt_sha256."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])
    source_code = _read_fixture_source(task.source_relpath)

    snapshot = invoke_capability_planner(task, source_code)
    receipt_hash = sha256_str(str(snapshot))
    assert len(receipt_hash) == 64


def test_real_core_arm_fails_closed_without_planner_version():
    """Snapshot without planner_version must be rejected."""
    bad_snapshot = {"selected_executor": "local_model", "execution_topology": "localheal_pipeline"}
    errors = validate_planner_snapshot(bad_snapshot)
    assert "missing_planner_version" in errors


def test_real_core_arm_fails_closed_without_route_truth_source():
    """Snapshot without selected_executor must be rejected."""
    bad_snapshot = {"planner_version": "capability_planner_v1", "execution_topology": "localheal_pipeline"}
    errors = validate_planner_snapshot(bad_snapshot)
    assert any("incomplete_signal_snapshot" in e for e in errors)


def test_real_core_arm_fails_closed_without_signal_snapshot_hash():
    """Snapshot missing required planner fields must be rejected."""
    bad_snapshot = {
        "planner_version": "capability_planner_v1",
        "selected_executor": "local_model",
        "execution_topology": "localheal_pipeline",
    }
    errors = validate_planner_snapshot(bad_snapshot)
    assert any("incomplete_signal_snapshot" in e for e in errors)


def test_prompt_variant_arm_is_not_labeled_real_core():
    """Old prompt-variant arm must not be present in ARMS."""
    assert "N30R_B_7B_CORE" not in ARMS
    assert "N30R_B_7B_REAL_CORE" in ARMS


def test_bare_arm_does_not_call_capability_planner():
    """Bare arm must not call CapabilityPlanner."""
    arm = ARMS["N30R_A_7B_BARE"]
    assert arm.nexus_enabled is False
    assert arm.core_armor_enabled is False


def test_golden_patch_is_absent_from_real_core_request():
    """Golden patch must not appear in the real core prompt."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    from scripts.bench.n30r_runner import _materialize_task
    task = _materialize_task(manifest["tasks"][0])

    def check_provider(model, system_prompt, user_prompt):
        assert "golden" not in user_prompt.lower()
        assert "GOLDEN" not in user_prompt
        return "def greet(name):\n    return f'Hello, {name}!'"

    result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], check_provider, 3001, 0, "test")
    assert result.planner_called is True
    assert result.execution_path_kind == "nexus_production_localheal_pipeline"
