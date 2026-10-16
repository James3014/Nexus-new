"""#2410 replay: past pool failures classified under the queue/rotate policy."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
replay_mod = SourceFileLoader(
    "agy_pool_failure_replay", str(ROOT / "scripts" / "ops" / "agy_pool_failure_replay.py")
).load_module()

T0 = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)


def _at(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def _write(root: Path, op_id: str, **fields) -> None:
    path = root / "operations" / op_id / "operation.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"operation_id": op_id, **fields}), encoding="utf-8")


def _records(tmp_path: Path) -> list[dict]:
    root = tmp_path / "ops"
    # A slow task timed out on account A: the old dispatcher cooled A for an hour.
    _write(
        root,
        "agyop_timeout",
        created_at=_at(-20),
        started_at=_at(-20),
        finished_at=_at(-10),
        failure_kind="TIMEOUT",
        account_alias_hash="aaaaaaaaaaaa",
        attempts=1,
        failure_history=[
            {"account_alias_hash": "aaaaaaaaaaaa", "failure_kind": "TIMEOUT", "at": _at(-10)}
        ],
    )
    # Exhausted while the snapshot still listed usable accounts.
    _write(
        root,
        "agyop_exhausted",
        created_at=_at(0),
        started_at=_at(0),
        finished_at=_at(0.01),
        failure_kind="ACCOUNT_UNAVAILABLE",
        attempts=0,
        quota_preflight_progress={"usable_count": 3, "blocked_count": 1, "unknown_count": 0},
    )
    # Exhausted with no TIMEOUT cooldown in play and nothing usable.
    _write(
        root,
        "agyop_really_exhausted",
        created_at=_at(120),
        started_at=_at(120),
        finished_at=_at(120.01),
        failure_kind="ACCOUNT_UNAVAILABLE",
        attempts=0,
        quota_preflight_progress={"usable_count": 0, "blocked_count": 4, "unknown_count": 0},
    )
    # Busy after the old fixed 15 s wait, and busy after a full 900 s wait.
    _write(
        root,
        "agyop_busy_short",
        created_at=_at(1),
        started_at=_at(1),
        finished_at=_at(1.25),
        failure_kind="AGY_ACCOUNT_POOL_BUSY",
        attempts=0,
    )
    _write(
        root,
        "agyop_busy_full",
        created_at=_at(2),
        started_at=_at(2),
        finished_at=_at(17),
        failure_kind="AGY_ACCOUNT_POOL_BUSY",
        attempts=0,
    )
    # A full 900 s wait while nobody else leased: still busy under FIFO.
    _write(
        root,
        "agyop_busy_full_alone",
        created_at=_at(200),
        started_at=_at(200),
        finished_at=_at(215),
        failure_kind="AGY_ACCOUNT_POOL_BUSY",
        attempts=0,
    )
    # A timeout only 2 minutes before an exhaustion: still inside the new
    # 5-minute cooldown, so the dispatch queues until it ends.
    _write(
        root,
        "agyop_recent_timeout",
        created_at=_at(280),
        started_at=_at(280),
        finished_at=_at(298),
        failure_kind="TIMEOUT",
        account_alias_hash="cccccccccccc",
        attempts=1,
    )
    _write(
        root,
        "agyop_exhausted_recent",
        created_at=_at(300),
        started_at=_at(300),
        finished_at=_at(300.01),
        failure_kind="ACCOUNT_UNAVAILABLE",
        attempts=0,
        quota_preflight_progress={"usable_count": 1, "blocked_count": 3, "unknown_count": 0},
    )
    # Outside the window and a completed operation: ignored.
    _write(
        root,
        "agyop_old",
        created_at=_at(-60 * 72),
        failure_kind="AGY_ACCOUNT_POOL_BUSY",
        attempts=0,
    )
    _write(
        root,
        "agyop_done",
        created_at=_at(3),
        started_at=_at(3),
        finished_at=_at(8),
        account_alias_hash="bbbbbbbbbbbb",
        status="COMPLETED",
        attempts=1,
    )
    return replay_mod.load_records(root)


def test_replay_classifies_each_pool_failure(tmp_path: Path) -> None:
    records = _records(tmp_path)
    end = (T0 + timedelta(hours=6)).timestamp()
    report = replay_mod.replay(records, window_start=end - 48 * 3600, window_end=end)

    by_id = {row["operation_id"]: row for row in report["rows"]}
    assert report["pool_failures"] == 6
    assert by_id["agyop_exhausted"]["verdict"] == "WOULD_CLAIM_OR_QUEUE"
    assert by_id["agyop_exhausted"]["accounts_freed_by_short_timeout_cooldown"] == 1
    assert by_id["agyop_really_exhausted"]["verdict"] == "STILL_EXHAUSTED"
    assert by_id["agyop_exhausted_recent"]["verdict"] == "WOULD_QUEUE_UNTIL_RECOVERY"
    assert by_id["agyop_busy_short"]["verdict"] == "WOULD_QUEUE"
    assert by_id["agyop_busy_short"]["lease_freed_in_budget"] is True
    # agyop_done leased while agyop_busy_full was still waiting.
    assert by_id["agyop_busy_full"]["later_arrivals_leased_during_wait"] == 1
    assert by_id["agyop_busy_full"]["verdict"] == "WOULD_LEASE_FIFO"
    assert by_id["agyop_busy_full_alone"]["verdict"] == "ALREADY_WAITED_FULL_BUDGET"
    assert report["would_queue_or_rotate"] == 4
    assert report["verdicts"] == {
        "ALREADY_WAITED_FULL_BUDGET": 1,
        "STILL_EXHAUSTED": 1,
        "WOULD_CLAIM_OR_QUEUE": 1,
        "WOULD_LEASE_FIFO": 1,
        "WOULD_QUEUE": 1,
        "WOULD_QUEUE_UNTIL_RECOVERY": 1,
    }


def test_replay_cli_prints_summary_without_rows(tmp_path: Path, capsys) -> None:
    _records(tmp_path)
    code = replay_mod.main([
        "--operation-root",
        str(tmp_path / "ops"),
        "--until",
        (T0 + timedelta(hours=6)).isoformat(),
    ])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["pool_failures"] == 6
    assert "rows" not in report
