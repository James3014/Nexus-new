"""Regression tests for the canonical Agy dispatch wrapper."""

from __future__ import annotations

import os
import stat
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
INSTALLER_PATH = ROOT / "scripts" / "ops" / "install_nexus_agy_dispatch.sh"

os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_canonical", str(DISPATCH_PATH)).load_module()


def _window(remaining: float, *, reset_at: str | None = None) -> dict:
    return {
        "status": "known",
        "remaining_pct": remaining,
        "reset_at": reset_at,
    }


def test_weekly_only_quota_is_usable_fallback() -> None:
    groups = {"Gemini Models": {"weekly": _window(86.0)}}
    assert dispatch._usable_quota_window(groups, "Gemini Models") == (
        True,
        "weekly",
    )


def test_explicit_disabled_five_hour_stays_fail_closed() -> None:
    groups = {
        "Gemini Models": {
            "5h": {
                "status": "disabled",
                "remaining_pct": None,
                "reset_at": None,
            },
            "weekly": _window(86.0),
        }
    }
    assert dispatch._usable_quota_window(groups, "Gemini Models") == (
        False,
        "5h",
    )


def test_explicit_five_hour_takes_precedence_over_weekly() -> None:
    groups = {
        "Gemini Models": {
            "5h": _window(25.0),
            "weekly": _window(0.0, reset_at="2999-01-01T00:00:00Z"),
        }
    }
    assert dispatch._usable_quota_window(groups, "Gemini Models") == (
        True,
        "5h",
    )


def test_weekly_only_dual_family_account_enters_reserve() -> None:
    snapshot = {
        "accounts": [
            {
                "account": "gemini-only",
                "ok": True,
                "groups": {
                    "Gemini Models": {"weekly": _window(70.0)},
                    "Claude and GPT models": {
                        "weekly": _window(
                            0.0,
                            reset_at="2999-01-01T00:00:00Z",
                        )
                    },
                },
            },
            {
                "account": "google-10",
                "ok": True,
                "groups": {
                    "Gemini Models": {"weekly": _window(86.0)},
                    "Claude and GPT models": {"weekly": _window(100.0)},
                },
            },
            {
                "account": "disabled-5h",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": {
                            "status": "disabled",
                            "remaining_pct": None,
                            "reset_at": None,
                        },
                        "weekly": _window(90.0),
                    },
                    "Claude and GPT models": {
                        "weekly": _window(
                            0.0,
                            reset_at="2999-01-01T00:00:00Z",
                        )
                    },
                },
            },
        ]
    }

    preferred, reserve = dispatch._dynamic_preference_tiers(
        "gemini-3.8-flash-medium",
        snapshot,
    )

    assert preferred == ["gemini-only"]
    assert reserve == ["google-10"]


def test_installer_deploys_exact_canonical_bytes(tmp_path: Path) -> None:
    target = tmp_path / "nexus-agy-dispatch"
    env = os.environ.copy()
    env.update(
        {
            "NEXUS_AGY_REPO_ROOT": str(ROOT),
            "NEXUS_AGY_SNAPSHOT": str(ROOT),
            "NEXUS_AGY_DISPATCH_TARGET": str(target),
        }
    )

    proc = subprocess.run(
        ["bash", str(INSTALLER_PATH)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert target.read_bytes() == DISPATCH_PATH.read_bytes()
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_default_snapshot_prefers_host_runtime_generation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    current = tmp_path / ".local/share/nexus-host-runtime/current/snapshot"
    current.mkdir(parents=True)

    assert dispatch._default_snapshot() == current


def test_default_snapshot_falls_back_to_legacy_before_host_sync(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert dispatch._default_snapshot() == (tmp_path / ".local/share/nexus-agy-direct/Nexus-new")
