"""Regression tests for the canonical Agy quota snapshot producer."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUOTA_PATH = ROOT / "scripts" / "ops" / "nexus-agy-quota"
INSTALLER_PATH = ROOT / "scripts" / "ops" / "install_nexus_agy_quota.sh"
quota = SourceFileLoader("nexus_agy_quota_canonical", str(QUOTA_PATH)).load_module()


def test_parse_usage_preserves_model_family_and_disabled_window() -> None:
    parsed = quota.parse_usage(
        "Gemini Models\tWeekly Limit Remaining\t29%\t2026-09-30T03:02:03Z\n"
        "Gemini Models\tFive Hour Limit Remaining\t100%\t2026-09-28T06:28:21Z\n"
        "Claude and GPT models\tFive Hour Limit Remaining\tdisabled\t\n"
    )

    assert parsed["Gemini Models"]["weekly"]["remaining_pct"] == 29.0
    assert parsed["Gemini Models"]["5h"]["remaining_pct"] == 100.0
    assert parsed["Claude and GPT models"]["5h"] == {
        "status": "disabled",
        "remaining_pct": None,
        "reset_at": None,
    }


def test_partial_refresh_preserves_current_inventory_and_drops_removed_accounts(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "quota.json"
    snapshot.write_text(
        json.dumps({
            "accounts": [
                {"account": "keep", "ok": True, "groups": {}},
                {"account": "removed", "ok": True, "groups": {}},
            ]
        }),
        encoding="utf-8",
    )

    payload = quota.merge_snapshot(
        snapshot_path=snapshot,
        current_names={"keep", "new"},
        refreshed_rows=[{"account": "new", "ok": True, "groups": {}}],
        partial=True,
        checked_at="2026-09-28T00:00:00+00:00",
    )

    assert [row["account"] for row in payload["accounts"]] == ["keep", "new"]


def test_installer_deploys_exact_canonical_bytes(tmp_path: Path) -> None:
    target = tmp_path / "nexus-agy-quota"
    env = os.environ.copy()
    env.update({
        "NEXUS_AGY_REPO_ROOT": str(ROOT),
        "NEXUS_AGY_QUOTA_TARGET": str(target),
    })

    proc = subprocess.run(
        ["bash", str(INSTALLER_PATH)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert target.read_bytes() == QUOTA_PATH.read_bytes()
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH
