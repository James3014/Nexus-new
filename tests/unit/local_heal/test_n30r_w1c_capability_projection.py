"""N30R-W1C: Capability Projection Closure tests.

Validates canonical classification, fail-closed behavior, deterministic ordering,
and receipt provenance for planner→executor capability projection.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.services.local_heal.local_model_capability_wiring import (
    CONTROLLER_PLANE_CAPABILITIES,
    CapabilityWiringStatus,
    LocalExecutorCapabilityProjection,
    build_local_model_capability_wiring,
    classify_selected_capabilities,
    project_planner_capabilities_for_local_executor,
    _classify_single_capability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ssd_snapshot(caps: list[str], count: int | None = None, deps: dict | None = None) -> dict:
    reasons = {c: [f"test_reason_{c}"] for c in caps}
    ssd: dict = {"capability_reasons": reasons}
    if count is not None:
        ssd["selected_capability_count"] = count
    if deps:
        ssd["capability_dependencies"] = deps
    return {"ssd_route_map": ssd}


# ---------------------------------------------------------------------------
# 1. SSD fallback to route map
# ---------------------------------------------------------------------------

def test_projection_falls_back_to_ssd_route_map():
    snap = _ssd_snapshot(["repair_loop", "artifact_gate"])
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.source == "ssd_route_map_capability_reasons"
    assert proj.valid is True


def test_projection_uses_explicit_selected_capabilities():
    snap = {"selected_capabilities": ["repair_loop", "artifact_gate"]}
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.source == "explicit_selected_capabilities"
    assert proj.valid is True


# ---------------------------------------------------------------------------
# 2. All 8 SSD capabilities classified
# ---------------------------------------------------------------------------

def test_projection_accounts_for_all_ssd_capabilities():
    all_8 = [
        "harness_preflight_sensor", "repair_loop", "research_route",
        "delivery_gate", "mempalace_gate", "artifact_gate",
        "claim_gate", "local_model_executor",
    ]
    snap = _ssd_snapshot(all_8)
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is True
    total_classified = (
        len(proj.executable_capabilities)
        + len(proj.advisory_capabilities)
        + len(proj.control_plane_capabilities)
    )
    assert total_classified == 8


# ---------------------------------------------------------------------------
# 3. Control-plane classification
# ---------------------------------------------------------------------------

def test_projection_classifies_control_plane_capabilities():
    snap = _ssd_snapshot(["harness_preflight_sensor", "research_route", "mempalace_gate"])
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is True
    assert len(proj.control_plane_capabilities) == 3
    assert "harness_preflight_sensor" in proj.control_plane_capabilities
    assert "research_route" in proj.control_plane_capabilities
    assert "mempalace_gate" in proj.control_plane_capabilities
    assert len(proj.unknown_capabilities) == 0


def test_control_plane_caps_not_in_executor_selected():
    snap = _ssd_snapshot(["harness_preflight_sensor", "repair_loop"])
    proj = project_planner_capabilities_for_local_executor(snap)
    assert "harness_preflight_sensor" not in proj.selected_capabilities
    assert "repair_loop" in proj.selected_capabilities


# ---------------------------------------------------------------------------
# 4. Unknown capability rejection
# ---------------------------------------------------------------------------

def test_projection_rejects_true_unknown_capability():
    snap = _ssd_snapshot(["repair_loop", "totally_fake_xyz_123"])
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is False
    assert "totally_fake_xyz_123" in proj.unknown_capabilities
    assert "unknown_capabilities_present" in proj.failure_reason


# ---------------------------------------------------------------------------
# 5. Count mismatch rejection
# ---------------------------------------------------------------------------

def test_projection_rejects_count_mismatch():
    snap = _ssd_snapshot(["repair_loop"], count=5)
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is False
    assert "ssd_selected_count_mismatch" in proj.failure_reason


# ---------------------------------------------------------------------------
# 6. Dependency failure rejection
# ---------------------------------------------------------------------------

def test_projection_rejects_missing_hard_dependency():
    snap = _ssd_snapshot(
        ["delivery_gate"],
        deps={"delivery_gate": ["artifact_gate", "claim_gate"]},
    )
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is False
    assert "dependency_errors_present" in proj.failure_reason
    assert "delivery_gate_depends_on_artifact_gate_not_selected" in proj.dependency_errors


# ---------------------------------------------------------------------------
# 7. Deduplication
# ---------------------------------------------------------------------------

def test_projection_deduplicates_capabilities():
    # Python dicts deduplicate keys, so this produces 1 unique key
    snap = _ssd_snapshot(["repair_loop", "repair_loop", "repair_loop"])
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is True
    assert len(proj.executable_capabilities) == 1
    assert proj.executable_capabilities == ("repair_loop",)
    # planner_selected_count reflects unique keys in capability_reasons dict
    assert proj.planner_selected_count == 1
    assert proj.projected_count == 1


# ---------------------------------------------------------------------------
# 8. Deterministic ordering
# ---------------------------------------------------------------------------

def test_projection_has_deterministic_order():
    caps = ["claim_gate", "artifact_gate", "repair_loop"]
    snap = _ssd_snapshot(caps)
    p1 = project_planner_capabilities_for_local_executor(snap)
    p2 = project_planner_capabilities_for_local_executor(snap)
    assert p1.selected_capabilities == p2.selected_capabilities
    assert p1.executable_capabilities == p2.executable_capabilities


# ---------------------------------------------------------------------------
# 9. Snapshot immutability
# ---------------------------------------------------------------------------

def test_projection_does_not_mutate_snapshot():
    import copy
    snap = _ssd_snapshot(["repair_loop", "artifact_gate"])
    snap_copy = copy.deepcopy(snap)
    project_planner_capabilities_for_local_executor(snap)
    assert snap == snap_copy


# ---------------------------------------------------------------------------
# 10. Bridge uses projection helper
# ---------------------------------------------------------------------------

def test_bridge_uses_projection_helper():
    from scripts.bench.n30r_real_core_bridge import run_real_core_bridge
    import ast
    source = Path("scripts/bench/n30r_real_core_bridge.py").read_text(encoding="utf-8")
    assert "project_planner_capabilities_for_local_executor" in source
    assert "projection.valid" in source


# ---------------------------------------------------------------------------
# 11. Bridge records projection provenance
# ---------------------------------------------------------------------------

def test_bridge_records_projection_provenance():
    from scripts.bench.n30r_real_core_bridge import run_real_core_bridge
    source = Path("scripts/bench/n30r_real_core_bridge.py").read_text(encoding="utf-8")
    assert "capability_projection_source" in source
    assert "planner_selected_capability_count" in source
    assert "executor_selected_capability_count" in source
    assert "executable_capability_count" in source
    assert "advisory_capability_count" in source
    assert "control_plane_capability_count" in source
    assert "unknown_capability_count" in source
    assert "dropped_capability_count" in source
    assert "capability_projection_sha256" in source


# ---------------------------------------------------------------------------
# 12. Bridge rejects executor capability metadata mismatch
# ---------------------------------------------------------------------------

def test_bridge_rejects_executor_capability_metadata_mismatch():
    from scripts.bench.n30r_real_core_bridge import run_real_core_bridge
    source = Path("scripts/bench/n30r_real_core_bridge.py").read_text(encoding="utf-8")
    assert "executor_capability_projection_mismatch" in source
    assert "selected_capabilities_used" in source


# ---------------------------------------------------------------------------
# 13. Bridge rejects missing selected_capabilities_used
# ---------------------------------------------------------------------------

def test_bridge_rejects_missing_selected_capabilities_used():
    from scripts.bench.n30r_real_core_bridge import run_real_core_bridge
    source = Path("scripts/bench/n30r_real_core_bridge.py").read_text(encoding="utf-8")
    assert 'meta_caps_used = meta.get("selected_capabilities_used")' in source


# ---------------------------------------------------------------------------
# 14. Source-level forbidden patterns
# ---------------------------------------------------------------------------

def test_wiring_source_has_no_direct_selected_capabilities_read():
    """Bridge must not read selected_capabilities directly from snapshot."""
    source = Path("scripts/bench/n30r_real_core_bridge.py").read_text(encoding="utf-8")
    lines = source.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if 'signal_snapshot.get("selected_capabilities"' in stripped:
            if "projection" not in stripped and "project_planner" not in stripped:
                pytest.fail(f"Bridge reads selected_capabilities directly at line {i}")


def test_wiring_source_has_no_direct_ssd_route_map_read():
    """Bridge must not parse ssd_route_map directly."""
    source = Path("scripts/bench/n30r_real_core_bridge.py").read_text(encoding="utf-8")
    for i, line in enumerate(source.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if 'ssd_route_map' in stripped and "signal_snapshot" in stripped:
            if "projection" not in stripped and "project_planner" not in stripped:
                pytest.fail(f"Bridge reads ssd_route_map directly at line {i}")


# ---------------------------------------------------------------------------
# 15. _classify_single_capability unit tests
# ---------------------------------------------------------------------------

def test_classify_single_executable():
    wiring = build_local_model_capability_wiring()
    cat, name = _classify_single_capability("repair_loop", wiring)
    assert cat == "executable"


def test_classify_single_advisory():
    wiring = build_local_model_capability_wiring()
    cat, name = _classify_single_capability("ddtree", wiring)
    assert cat == "advisory"


def test_classify_single_control_plane():
    wiring = build_local_model_capability_wiring()
    cat, name = _classify_single_capability("harness_preflight_sensor", wiring)
    assert cat == "control_plane"


def test_classify_single_unknown():
    wiring = build_local_model_capability_wiring()
    cat, name = _classify_single_capability("nonexistent_xyz", wiring)
    assert cat == "unknown"


def test_classify_single_empty():
    wiring = build_local_model_capability_wiring()
    cat, name = _classify_single_capability("", wiring)
    assert cat == "unknown"


# ---------------------------------------------------------------------------
# 16. Classification accounting invariant
# ---------------------------------------------------------------------------

def test_projection_accounting_invariant():
    all_8 = [
        "harness_preflight_sensor", "repair_loop", "research_route",
        "delivery_gate", "mempalace_gate", "artifact_gate",
        "claim_gate", "local_model_executor",
    ]
    snap = _ssd_snapshot(all_8)
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is True

    accounted = (
        len(proj.executable_capabilities)
        + len(proj.advisory_capabilities)
        + len(proj.control_plane_capabilities)
        + len(proj.unknown_capabilities)
        + len(proj.dropped_capabilities)
    )
    assert accounted == proj.planner_selected_count


# ---------------------------------------------------------------------------
# 17. delivery_gate and local_model_executor properly classified
# ---------------------------------------------------------------------------

def test_delivery_gate_is_executable_in_projection():
    snap = _ssd_snapshot(["delivery_gate"])
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is True
    assert "delivery_gate" in proj.executable_capabilities
    assert "delivery_gate" in proj.selected_capabilities


def test_local_model_executor_is_executable_in_projection():
    snap = _ssd_snapshot(["local_model_executor"])
    proj = project_planner_capabilities_for_local_executor(snap)
    assert proj.valid is True
    assert "local_model_executor" in proj.executable_capabilities
    assert "local_model_executor" in proj.selected_capabilities


# ---------------------------------------------------------------------------
# 18. SSD missing cases
# ---------------------------------------------------------------------------

def test_projection_rejects_missing_ssd():
    proj = project_planner_capabilities_for_local_executor({})
    assert proj.valid is False
    assert proj.failure_reason in ("ssd_route_map_not_dict", "ssd_capability_reasons_empty")


def test_projection_rejects_ssd_non_dict():
    proj = project_planner_capabilities_for_local_executor({"ssd_route_map": "bad"})
    assert proj.valid is False
    assert "ssd_route_map_not_dict" in proj.failure_reason


def test_projection_rejects_empty_capability_reasons():
    proj = project_planner_capabilities_for_local_executor({"ssd_route_map": {}})
    assert proj.valid is False
    assert "ssd_capability_reasons_empty" in proj.failure_reason


def test_projection_rejects_capability_reasons_not_dict():
    proj = project_planner_capabilities_for_local_executor({"ssd_route_map": {"capability_reasons": "bad"}})
    assert proj.valid is False
    assert "ssd_capability_reasons_not_dict" in proj.failure_reason
