from __future__ import annotations

import plistlib
from pathlib import Path

from scripts.ops.hybrid_replication_live_install import (
    LIVE_BUNDLE_FILES,
    render_launchd_plist,
)


def test_live_bundle_contains_only_research_runtime_files() -> None:
    assert "nexus/research/hybrid_replication_pipeline.py" in LIVE_BUNDLE_FILES
    assert "scripts/ops/hybrid_replication_daemon.py" in LIVE_BUNDLE_FILES
    assert "scripts/ops/hybrid_replication_live_stack.py" in LIVE_BUNDLE_FILES
    assert "scripts/ops/hybrid_replication_ground_truth.py" in LIVE_BUNDLE_FILES


def test_launchd_plist_binds_exact_bundle_and_t_auto(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    plist_bytes = render_launchd_plist(
        python="/opt/homebrew/bin/python3",
        bundle_root=bundle,
        experiment_root=tmp_path / "experiment",
        d0_root=tmp_path / "d0",
        repo_map=tmp_path / "repo-map.json",
        t_auto="2026-10-01T03:00:00Z",
        frozen_policy_sha256="a" * 64,
    )
    payload = plistlib.loads(plist_bytes)

    assert payload["Label"] == "com.nexus.hybrid-replication"
    args = payload["ProgramArguments"]
    assert str(bundle / "scripts/ops/hybrid_replication_daemon.py") in args
    assert "2026-10-01T03:00:00Z" in args
    assert payload["EnvironmentVariables"]["PYTHONPATH"] == str(bundle)
    assert payload["StartInterval"] == 60
