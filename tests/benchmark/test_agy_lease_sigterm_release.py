"""A SIGTERM during a leased Agy attempt releases the account claim before exiting.

Online A/B 20261013b: a provider timeout killed the leaseholder without unwinding, so the
durable claim receipt survived and blocked the account (AGY_ACCOUNT_POOL_BUSY). The timeout
now terminates the provider process group with SIGTERM first; the leaseholder must release.
Runs in a child interpreter so the signal never reaches the test runner.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CHILD = """
import os, signal, sys, time
from types import SimpleNamespace
from scripts.bench import agy_account_lease as lease

marker, home = sys.argv[1], sys.argv[2]

class Claim:
    account_alias_hash = "alias-hash"
    lease_id_hash = "lease-hash"
    internal_id = "google-01"
    lease = SimpleNamespace(execution_env={"HOME": home})

    def release(self):
        with open(marker, "w") as fh:
            fh.write("released")

def attempt(_env):
    os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(10)

lease._attempt_under_claim(lease.LeasedRunResult(status="failed"), Claim(), attempt, {}, "flash")
"""


def test_sigterm_during_attempt_releases_claim(tmp_path: Path) -> None:
    marker = tmp_path / "released"
    home = tmp_path / "home"
    home.mkdir()
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, str(marker), str(home)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert marker.exists(), (
        f"claim not released on SIGTERM (rc={proc.returncode}): {proc.stderr[-2000:]}"
    )
    assert proc.returncode == 128 + 15
