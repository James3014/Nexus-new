"""#2998 F3: nexus-hcom-agy-safe refuses a direct leased-profile launch while the Agy pool is stopped.

With NEXUS_HCOM_AGY_LEASE_ACCOUNT set the launcher used to copy the pool
profile and start ``hcom agy`` without the #2990 stop check.  The dispatcher's
--hcom-collab launch passes its environment (and so the override) on; a hand-set
lease environment without NEXUS_AGY_POOL_STOPPED_OVERRIDE=1 is refused.
Fake hcom and manager executables; no real account.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "ops" / "nexus-hcom-agy-safe"
OVERRIDE = "NEXUS_AGY_POOL_STOPPED_OVERRIDE"


def _leased_launcher_env(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    original_home = tmp_path / "owner-home"
    manager_root = original_home / ".nexus" / "agy-account-pool" / "runtime"
    profile = manager_root / "accounts" / "primary"
    (profile / ".gemini").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    manager = bin_dir / "agy-cli-manager"
    manager.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    manager.chmod(0o755)
    hcom_marker = tmp_path / "hcom-ran"
    hcom = bin_dir / "hcom"
    hcom.write_text(f"#!/bin/sh\ntouch '{hcom_marker}'\nexit 0\n", encoding="utf-8")
    hcom.chmod(0o755)
    state_root = original_home / ".local" / "state" / "hcom-agy-safe"
    env = {k: v for k, v in os.environ.items() if k != OVERRIDE}
    env.update({
        "HOME": str(original_home),
        "HCOM_DIR": str(original_home / ".hcom"),
        "NEXUS_AGY_MANAGER": str(manager),
        "NEXUS_AGY_MANAGER_ROOT": str(manager_root),
        "NEXUS_HCOM_AGY_STATE_ROOT": str(state_root),
        "NEXUS_HCOM_BIN": str(hcom),
        "NEXUS_HCOM_AGY_LEASE_ACCOUNT": "primary",
        "NEXUS_HCOM_AGY_PROFILE_HOME": str(profile),
        "NEXUS_HCOM_AGY_LEASE_ID_HASH": "lease-hash",
        "NEXUS_HCOM_AGY_ACCOUNT_ALIAS_HASH": "alias-hash",
    })
    return env, hcom_marker, state_root


def test_hcom_agy_safe_leased_profile_launch_refused_while_stopped(tmp_path) -> None:
    """F3: the issue's repro (lease env set by hand, no dispatcher) no longer starts hcom agy."""
    env, hcom_marker, state_root = _leased_launcher_env(tmp_path)
    lease_path = tmp_path / "lease.lock"
    status_read_fd, status_write_fd = os.pipe()
    with lease_path.open("a+") as lease_fh:
        env["NEXUS_HCOM_AGY_LEASE_FD"] = str(lease_fh.fileno())
        env["NEXUS_HCOM_AGY_STATUS_FD"] = str(status_write_fd)
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER)],
            env=env,
            pass_fds=(lease_fh.fileno(), status_write_fd),
            capture_output=True,
            text=True,
            check=False,
        )
    os.close(status_write_fd)
    with os.fdopen(status_read_fd, "r", encoding="utf-8") as stream:
        statuses = [json.loads(line) for line in stream if line.strip()]

    assert proc.returncode == 3, proc.stderr
    assert proc.stderr.startswith("hcom-agy-safe: AGY_ACCOUNT_POOL_STOPPED: ")
    assert [row["event"] for row in statuses] == ["pre_provider_failed"]
    assert not hcom_marker.exists()
    assert not state_root.exists()  # no session copy of the pool profile
