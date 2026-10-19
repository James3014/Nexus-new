"""#2637: the dead v18-v23 swarm scripts are retired (unreachable + manifest).

Each script must refuse to run (so its default token and name-matching kill can
never execute again), carry the ARCHIVED marker, and be listed in the manifest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "ARCHIVED_2026-10-19-swarm-scripts.md"

RETIRED_SCRIPTS = (
    "scripts/node_fleet_mgr_v22.py",
    "scripts/stress_test_swarm_v18.py",
    "scripts/test_multi_region_swarm_v19.py",
    "scripts/test_swarm_v20_otel.py",
    "scripts/test_swarm_v21_nsp.py",
    "scripts/v23_scale_audit.py",
    "scripts/execute_scaling_audit_v22.py",
    "scripts/stress_test_nsp_v22.py",
    "scripts/tests/p3_swarm_stress.py",
)


@pytest.mark.parametrize("rel", RETIRED_SCRIPTS)
def test_retired_swarm_script_is_marked_and_listed(rel):
    source = (REPO / rel).read_text(encoding="utf-8")
    assert "ARCHIVED 2026-10-19 (#2637)" in source
    assert f"`{rel}`" in MANIFEST.read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", RETIRED_SCRIPTS)
def test_retired_swarm_script_refuses_to_run(rel, tmp_path):
    # Run from an empty cwd so a script that slipped past the guard could not
    # find nexus-swarm/ either; the guard must stop it before any subprocess.
    proc = subprocess.run(
        [sys.executable, str(REPO / rel)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "ARCHIVED 2026-10-19 (#2637)" in proc.stderr
    assert list(tmp_path.iterdir()) == []


def test_fleet_manager_cli_refuses_to_run(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "nexus.federation.fleet_manager", "stop"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "ARCHIVED (#2637)" in proc.stderr


def test_manifest_lists_fleet_manager_and_self_heal_fix():
    text = MANIFEST.read_text(encoding="utf-8")
    assert "`nexus/federation/fleet_manager.py`" in text
    assert "`nexus/services/self_heal_selector.py`" in text


def test_retired_shadow_audit_shell_script_refuses_to_run(tmp_path):
    rel = "scripts/shadow_audit_v24.sh"
    assert f"`{rel}`" in MANIFEST.read_text(encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(REPO / rel)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "ARCHIVED 2026-10-19 (#2637)" in proc.stderr
    # The guard stops it before the fleet starts or nodes_shadow.json is written.
    assert proc.stdout == ""
    assert list(tmp_path.iterdir()) == []
