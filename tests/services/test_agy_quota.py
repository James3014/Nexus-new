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


def test_merge_snapshot_preserves_prior_known_freshness_on_failure(tmp_path: Path) -> None:
    snapshot = tmp_path / "quota.json"
    snapshot.write_text(
        json.dumps({
            "checked_at": "2026-10-01T00:00:00+00:00",
            "accounts": [
                {
                    "account": "acct1",
                    "ok": True,
                    "checked_at": "2026-10-01T00:00:00+00:00",
                    "groups": {
                        "Gemini Models": {"weekly": {"status": "known", "remaining_pct": 80.0}}
                    },
                }
            ],
        }),
        encoding="utf-8",
    )

    payload = quota.merge_snapshot(
        snapshot_path=snapshot,
        current_names={"acct1"},
        refreshed_rows=[
            {
                "account": "acct1",
                "ok": False,
                "error": "deadline_exceeded",
                "checked_at": "2026-10-03T00:00:00+00:00",
            }
        ],
        partial=True,
        checked_at="2026-10-03T00:00:00+00:00",
    )

    assert len(payload["accounts"]) == 1
    acct = payload["accounts"][0]
    assert acct["account"] == "acct1"
    assert acct["ok"] is True
    assert acct["checked_at"] == "2026-10-01T00:00:00+00:00"
    assert acct["groups"]["Gemini Models"]["weekly"]["remaining_pct"] == 80.0


def test_merge_snapshot_retains_failed_accounts_without_silent_removal(tmp_path: Path) -> None:
    snapshot = tmp_path / "quota.json"
    payload = quota.merge_snapshot(
        snapshot_path=snapshot,
        current_names={"new_acct"},
        refreshed_rows=[
            {
                "account": "new_acct",
                "ok": False,
                "error": "timeout",
                "checked_at": "2026-10-03T00:00:00+00:00",
            }
        ],
        partial=True,
        checked_at="2026-10-03T00:00:00+00:00",
    )

    assert len(payload["accounts"]) == 1
    assert payload["accounts"][0]["account"] == "new_acct"
    assert payload["accounts"][0]["ok"] is False
    assert payload["accounts"][0]["error"] == "timeout"


def test_quota_main_bounds_total_timeout_and_emits_progress(tmp_path: Path, monkeypatch) -> None:
    pool_root = tmp_path / "pool"
    accounts_dir = pool_root / "accounts"
    accounts_dir.mkdir(parents=True)
    (accounts_dir / "acct1").mkdir()
    (accounts_dir / "acct2").mkdir()

    snapshot_path = tmp_path / "snapshot.json"
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_ROOT", str(pool_root))
    monkeypatch.setenv("NEXUS_AGY_QUOTA_SNAPSHOT", str(snapshot_path))

    progress_events: list[dict[str, object]] = []

    def fake_query(
        account_home, account_name, email, agy_binary, timeout, checked_at, on_progress=None
    ):
        return {
            "account": account_name,
            "email": email,
            "ok": True,
            "groups": {},
            "checked_at": checked_at,
        }

    monkeypatch.setattr(quota, "query_account", fake_query)

    rc = quota.main(["--timeout", "15"], on_progress=progress_events.append)
    assert rc == 0
    event_types = [e.get("phase") for e in progress_events]
    assert "STARTING" in event_types
    assert "FINISHED" in event_types

    start_event = next(e for e in progress_events if e.get("phase") == "STARTING")
    assert start_event.get("total_timeout") == 15.0


def test_quota_main_deadline_exceeded_marks_remaining_accounts(tmp_path: Path, monkeypatch) -> None:
    pool_root = tmp_path / "pool"
    accounts_dir = pool_root / "accounts"
    accounts_dir.mkdir(parents=True)
    (accounts_dir / "acct1").mkdir()
    (accounts_dir / "acct2").mkdir()

    snapshot_path = tmp_path / "snapshot.json"
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_ROOT", str(pool_root))
    monkeypatch.setenv("NEXUS_AGY_QUOTA_SNAPSHOT", str(snapshot_path))

    # Give a tiny total-timeout and make the first query take time to exceed the deadline
    import time

    def slow_query(
        account_home, account_name, email, agy_binary, timeout, checked_at, on_progress=None
    ):
        time.sleep(0.05)
        return {
            "account": account_name,
            "email": email,
            "ok": True,
            "groups": {},
            "checked_at": checked_at,
        }

    monkeypatch.setattr(quota, "query_account", slow_query)

    progress_events: list[dict[str, object]] = []
    rc = quota.main(
        ["acct1", "acct2", "--timeout", "10", "--total-timeout", "0.01"],
        on_progress=progress_events.append,
    )
    assert rc == 2
    event_types = [e.get("phase") for e in progress_events]
    assert "DEADLINE_EXCEEDED" in event_types

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    acct2_row = next(a for a in payload["accounts"] if a["account"] == "acct2")
    assert acct2_row["ok"] is False
    assert acct2_row["error"] == "deadline_exceeded"


def test_independent_real_query_obeys_fractional_total_deadline(tmp_path, monkeypatch):
    import sys
    import time

    pool = tmp_path / "pool"
    (pool / "accounts" / "one").mkdir(parents=True)
    executable = tmp_path / "fake-agy"
    executable.write_text(
        "#!" + sys.executable + "\nimport time\ntime.sleep(0.8)\n"
        "print('Gemini Models Weekly Limit Remaining 80%')\n"
    )
    executable.chmod(0o700)
    snapshot = tmp_path / "snapshot.json"
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_ROOT", str(pool))
    monkeypatch.setenv("NEXUS_AGY_QUOTA_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("NEXUS_AGY_BINARY", str(executable))
    start = time.monotonic()
    result = quota.main(["--timeout", "15", "--total-timeout", "0.1"])
    elapsed = time.monotonic() - start
    assert result == 2
    assert elapsed < 0.5, f"deadline ignored: {elapsed:.3f}s"
    assert json.loads(snapshot.read_text())["accounts"][0]["ok"] is False


def test_independent_failed_refresh_keeps_old_time_and_latest_failure(tmp_path):
    old = "2000-01-01T00:00:00+00:00"
    new = "2026-10-03T00:00:00+00:00"
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({
            "checked_at": old,
            "accounts": [{"account": "legacy", "ok": True, "groups": {"Gemini Models": {}}}],
        })
    )
    result = quota.merge_snapshot(
        snapshot_path=snapshot,
        current_names={"legacy"},
        partial=True,
        refreshed_rows=[{"account": "legacy", "ok": False, "error": "timeout", "checked_at": new}],
        checked_at=new,
    )
    row = result["accounts"][0]
    assert row["ok"] is True
    assert row["checked_at"] == old
    assert row["last_refresh"] == {"ok": False, "error": "timeout", "checked_at": new}

def test_query_timeout_reaps_usage_process(tmp_path: Path, monkeypatch) -> None:
    import sys
    import time

    account_home = tmp_path / "account"
    account_home.mkdir()
    pid_file = tmp_path / "agy.pid"
    executable = tmp_path / "fake-agy"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import os, time\n"
        "from pathlib import Path\n"
        "Path(os.environ['PID_FILE']).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("PID_FILE", str(pid_file))

    row = quota.query_account(
        account_home=account_home,
        account_name="one",
        email=None,
        agy_binary=str(executable),
        timeout=0.1,
        checked_at="2026-10-07T00:00:00+00:00",
    )

    assert row["ok"] is False
    assert row["error"] == "timeout"
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        raise AssertionError(f"timed-out usage process still alive: {pid}")


def test_wrapper_sigterm_reaps_active_usage_process(tmp_path: Path) -> None:
    import sys
    import time

    pool = tmp_path / "pool"
    account_home = pool / "accounts" / "one"
    account_home.mkdir(parents=True)
    snapshot = tmp_path / "snapshot.json"
    pid_file = tmp_path / "agy.pid"
    executable = tmp_path / "fake-agy"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import os, time\n"
        "from pathlib import Path\n"
        "Path(os.environ['PID_FILE']).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)

    env = os.environ.copy()
    env.update({
        "NEXUS_AGY_ACCOUNT_POOL_ROOT": str(pool),
        "NEXUS_AGY_QUOTA_SNAPSHOT": str(snapshot),
        "NEXUS_AGY_BINARY": str(executable),
        "PID_FILE": str(pid_file),
    })
    wrapper = subprocess.Popen(
        [sys.executable, str(QUOTA_PATH), "--timeout", "30"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 3.0
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pid_file.exists(), "usage child did not start"
        child_pid = int(pid_file.read_text())

        wrapper.terminate()
        wrapper.wait(timeout=3.0)
        assert wrapper.returncode != 0

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            raise AssertionError(f"usage child survived wrapper SIGTERM: {child_pid}")
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait()

