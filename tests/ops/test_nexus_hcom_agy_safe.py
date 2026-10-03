"""Focused tests for the canonical hcom/Agy collaborative launcher."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "ops" / "nexus-hcom-agy-safe"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_launcher_uses_full_active_account_home_and_cleans_ephemeral_copy(tmp_path: Path) -> None:
    original_home = tmp_path / "owner-home"
    manager_root = original_home / ".nexus" / "agy-account-pool" / "runtime"
    profile = manager_root / "accounts" / "google-active"
    (profile / ".gemini").mkdir(parents=True)
    (profile / "Library" / "Keychains").mkdir(parents=True)
    (profile / ".gemini" / "auth.json").write_text("active-auth", encoding="utf-8")
    (profile / "Library" / "Keychains" / "agy.keychain-db").write_text(
        "keychain-sentinel", encoding="utf-8"
    )
    (profile / "profile-marker.txt").write_text("active-profile", encoding="utf-8")

    # Negative identity control: the owner HOME contains a conflicting .gemini
    # identity. The launcher must still copy the canonical account snapshot HOME.
    (original_home / ".gemini").mkdir(parents=True, exist_ok=True)
    (original_home / ".gemini" / "auth.json").write_text("stale-owner-auth", encoding="utf-8")

    stale = manager_root.parent / "live-home"
    (stale / ".gemini").mkdir(parents=True)
    (stale / "profile-marker.txt").write_text("stale-live-home", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    manager = bin_dir / "agy-cli-manager"
    _write_executable(
        manager,
        """#!/usr/bin/env python3
import json, sys
if "ensure-active" in sys.argv:
    print(json.dumps({"active": "google-active"}))
elif "current" in sys.argv:
    print("google-active")
else:
    raise SystemExit(2)
""",
    )

    security = bin_dir / "security"
    _write_executable(security, "#!/bin/sh\nexit 0\n")

    record_path = tmp_path / "record.json"
    config_log = tmp_path / "config.log"
    hcom = bin_dir / "hcom"
    _write_executable(
        hcom,
        """#!/usr/bin/env python3
import json, os, pathlib, sys
if len(sys.argv) >= 4 and sys.argv[1] == "config":
    with open(os.environ["HCOM_TEST_CONFIG_LOG"], "a", encoding="utf-8") as fh:
        fh.write(f"{sys.argv[2]}={sys.argv[3]}\\n")
    raise SystemExit(0)
if len(sys.argv) >= 2 and sys.argv[1] == "agy":
    home = pathlib.Path(os.environ["HOME"])
    payload = {
        "args": sys.argv[2:],
        "home": str(home),
        "gemini_home": os.environ.get("GEMINI_CLI_HOME"),
        "hcom_dir": os.environ.get("HCOM_DIR"),
        "profile_marker": (home / "profile-marker.txt").read_text(),
        "auth_present": (home / ".gemini" / "auth.json").is_file(),
        "auth_value": (home / ".gemini" / "auth.json").read_text(),
        "keychain_present": (home / "Library" / "Keychains" / "agy.keychain-db").is_file(),
        "stale_marker": (home / "stale-marker.txt").exists(),
        "sensitive_present": any(
            key in os.environ
            for key in (
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GOOGLE_GENAI_API_KEY",
                "GH_TOKEN",
                "GITHUB_TOKEN",
                "GH_ENTERPRISE_TOKEN",
                "GITHUB_ENTERPRISE_TOKEN",
                "GITHUB_PAT",
                "GITHUB_ACTIONS_TOKEN",
            )
        ),
    }
    pathlib.Path(os.environ["HCOM_TEST_RECORD"]).write_text(json.dumps(payload))
    raise SystemExit(0)
raise SystemExit(2)
""",
    )

    state_root = original_home / ".local" / "state" / "hcom-agy-safe"
    env = os.environ.copy()
    env.update({
        "HOME": str(original_home),
        "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
        "NEXUS_AGY_MANAGER": str(manager),
        "NEXUS_AGY_MANAGER_ROOT": str(manager_root),
        "NEXUS_HCOM_AGY_STATE_ROOT": str(state_root),
        "NEXUS_HCOM_BIN": str(hcom),
        "HCOM_TEST_RECORD": str(record_path),
        "HCOM_TEST_CONFIG_LOG": str(config_log),
        "GEMINI_API_KEY": "must-not-leak",
        "GOOGLE_API_KEY": "must-not-leak",
        "GOOGLE_GENAI_API_KEY": "must-not-leak",
        "GH_TOKEN": "must-not-leak",
        "GITHUB_TOKEN": "must-not-leak",
        "GH_ENTERPRISE_TOKEN": "must-not-leak",
        "GITHUB_ENTERPRISE_TOKEN": "must-not-leak",
        "GITHUB_PAT": "must-not-leak",
        "GITHUB_ACTIONS_TOKEN": "must-not-leak",
    })

    proc = subprocess.run(
        [sys.executable, str(LAUNCHER), "--model", "gpt-oss-120b-medium"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["args"] == ["--model", "gpt-oss-120b-medium"]
    assert payload["profile_marker"] == "active-profile"
    assert payload["auth_present"] is True
    assert payload["auth_value"] == "active-auth"
    assert payload["keychain_present"] is True
    assert payload["sensitive_present"] is False
    assert payload["gemini_home"] == payload["home"]
    assert payload["hcom_dir"] == str((original_home / ".hcom").resolve())
    assert Path(payload["home"]).parent == state_root.resolve()
    assert not Path(payload["home"]).exists()
    assert list(state_root.glob("session.*")) == []
    assert stat.S_IMODE(state_root.stat().st_mode) == 0o700

    config_lines = config_log.read_text(encoding="utf-8").splitlines()
    assert config_lines == [
        "auto_approve=0",
        "auto_trust_workspace=0",
        "relay_enabled=0",
    ]


def test_launcher_rejects_headless_before_creating_ephemeral_home(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(LAUNCHER), "--headless"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "HEADLESS_DISABLED_EPHEMERAL_HOME_LIFETIME" in proc.stderr
    assert not (tmp_path / ".local" / "state" / "hcom-agy-safe").exists()
