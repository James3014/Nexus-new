#!/usr/bin/env python3
"""Replay recent nexus-agy-dispatch pool failures under the #2410 queue/rotate policy.

Read-only.  It reads ``operations/*/operation.json`` under the Agy operation
root and, for every dispatch that ended without a provider attempt because the
pool was busy (``AGY_ACCOUNT_POOL_BUSY``) or reported exhausted
(``ACCOUNT_UNAVAILABLE``), decides what the #2410 dispatcher would have done:

* busy: the old dispatch stopped after its fixed pool wait.  The new one
  queues until its own total deadline, so it is ``WOULD_QUEUE`` unless it had
  already waited the whole budget.  ``lease_freed_in_budget`` says whether
  another recorded operation released a lease inside that longer wait.  A
  waiter that did wait the whole budget while later arrivals were proven to
  hold a lease (their provider process started before it gave up)
  ``WOULD_LEASE_FIFO``: the new queue serves waiters oldest first.  Records
  keep no per-dispatch timeout or exact lease times, so this is a
  reconstruction from ``started_at`` / ``provider_started_at`` /
  ``finished_at``.
* exhausted: the old dispatcher put an account into a one-hour manager
  cooldown after every ``TIMEOUT``; the new one cools it for five minutes.
  When the pool snapshot still listed usable accounts and some account was
  cooling only because of a TIMEOUT more than five minutes old, the dispatch
  ``WOULD_CLAIM_OR_QUEUE``.  When the earliest new-policy recovery falls
  inside the dispatch budget it ``WOULD_QUEUE_UNTIL_RECOVERY``.

Only alias hashes, timestamps and failure kinds are read or printed; the
records hold no account names or credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

POOL_BUSY = "AGY_ACCOUNT_POOL_BUSY"
POOL_EXHAUSTED = "ACCOUNT_UNAVAILABLE"
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_TIMEOUT_COOLDOWN_MINUTES = 60.0
NEW_TIMEOUT_COOLDOWN_MINUTES = 5.0
ATTEMPT_FLOOR_SECONDS = 5.0
ACCOUNT_COOLDOWN_FAILURES = frozenset({
    "AUTH_OR_SESSION_INVALID",
    "TOKEN_EXPIRED",
    "TOKEN_REFRESH_FAILED",
    "RATE_LIMITED",
    "ACCOUNT_UNAVAILABLE",
    "ACCOUNT_DISABLED",
})


def _ts(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def load_records(operation_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((operation_root / "operations").glob("*/operation.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _account_failures(record: dict[str, Any]) -> list[tuple[str, str, float]]:
    """(alias hash, failure kind, at) for each account this operation gave up on."""
    out: list[tuple[str, str, float]] = []
    for entry in record.get("failure_history") or []:
        if not isinstance(entry, dict):
            continue
        alias = entry.get("account_alias_hash")
        kind = entry.get("failure_kind")
        at = _ts(entry.get("at"))
        if isinstance(alias, str) and alias and isinstance(kind, str) and at is not None:
            out.append((alias, kind, at))
    if not out:
        alias = record.get("account_alias_hash")
        kind = record.get("failure_kind")
        at = _ts(record.get("finished_at"))
        if isinstance(alias, str) and alias and isinstance(kind, str) and at is not None:
            out.append((alias, kind, at))
    return out


def replay(
    records: list[dict[str, Any]],
    *,
    window_start: float,
    window_end: float,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    timeout_cooldown_seconds: float = DEFAULT_TIMEOUT_COOLDOWN_MINUTES * 60.0,
    new_timeout_cooldown_seconds: float = NEW_TIMEOUT_COOLDOWN_MINUTES * 60.0,
) -> dict[str, Any]:
    in_window = [
        record
        for record in records
        if (created := _ts(record.get("created_at"))) is not None
        and window_start <= created <= window_end
    ]
    timeout_cooldowns: list[tuple[str, float, float]] = []
    new_timeout_cooldowns: list[tuple[str, float, float]] = []
    other_cooldowns: list[tuple[str, float, float]] = []
    lease_spans: list[tuple[str, float, float]] = []
    # (operation start, first proof it held a lease): a provider process
    # only starts under a lease, so provider_started_at bounds the claim time.
    lease_proofs: list[tuple[float, float]] = []
    for record in records:
        for alias, kind, at in _account_failures(record):
            if kind == "TIMEOUT":
                timeout_cooldowns.append((alias, at, at + timeout_cooldown_seconds))
                new_timeout_cooldowns.append((alias, at, at + new_timeout_cooldown_seconds))
            elif kind in ACCOUNT_COOLDOWN_FAILURES:
                other_cooldowns.append((alias, at, at + timeout_cooldown_seconds))
        alias = record.get("account_alias_hash")
        started = _ts(record.get("started_at"))
        finished = _ts(record.get("finished_at"))
        if isinstance(alias, str) and alias and started is not None and finished is not None:
            lease_spans.append((alias, started, finished))
        provider_started = _ts(record.get("provider_started_at"))
        if started is not None and provider_started is not None:
            lease_proofs.append((started, provider_started))

    def cooling_at(spans: list[tuple[str, float, float]], at: float) -> dict[str, float]:
        active: dict[str, float] = {}
        for alias, begin, end in spans:
            if begin <= at < end:
                active[alias] = max(active.get(alias, 0.0), end)
        return active

    budget = max(0.0, timeout_seconds - ATTEMPT_FLOOR_SECONDS)
    rows: list[dict[str, Any]] = []
    for record in in_window:
        kind = record.get("failure_kind")
        if kind not in (POOL_BUSY, POOL_EXHAUSTED):
            continue
        if int(record.get("attempts") or 0) != 0:
            continue
        started = _ts(record.get("started_at")) or _ts(record.get("created_at"))
        finished = _ts(record.get("finished_at")) or started
        assert started is not None and finished is not None
        old_wait = max(0.0, finished - started)
        progress = record.get("quota_preflight_progress") or {}
        usable = progress.get("usable_count") if isinstance(progress, dict) else None
        row: dict[str, Any] = {
            "operation_id": record.get("operation_id"),
            "created_at": record.get("created_at"),
            "failure_kind": kind,
            "old_wait_seconds": round(old_wait, 1),
            "snapshot_usable_count": usable,
        }
        if kind == POOL_BUSY:
            freed = any(
                started + old_wait <= end <= started + budget for _alias, _begin, end in lease_spans
            )
            # Later arrivals proven to hold a lease (their provider started)
            # while this dispatch was still waiting: FIFO serves it first.
            barged = sum(
                1
                for arrived, provider_started in lease_proofs
                if started < arrived and provider_started < finished
            )
            row["lease_freed_in_budget"] = freed
            row["later_arrivals_leased_during_wait"] = barged
            if old_wait < budget - 1.0:
                row["verdict"] = "WOULD_QUEUE"
            elif barged:
                row["verdict"] = "WOULD_LEASE_FIFO"
            else:
                row["verdict"] = "ALREADY_WAITED_FULL_BUDGET"
        else:
            timeout_cooled = cooling_at(timeout_cooldowns, finished)
            new_timeout_cooled = cooling_at(new_timeout_cooldowns, finished)
            other_cooled = cooling_at(other_cooldowns, finished)
            # Cooling only because of a TIMEOUT older than the new short cooldown.
            freed = {
                alias
                for alias in timeout_cooled
                if alias not in other_cooled and alias not in new_timeout_cooled
            }
            row["accounts_cooling_only_from_timeout"] = len([
                alias for alias in timeout_cooled if alias not in other_cooled
            ])
            row["accounts_freed_by_short_timeout_cooldown"] = len(freed)
            row["accounts_cooling_from_other_failures"] = len(other_cooled)
            soonest = min([*new_timeout_cooled.values(), *other_cooled.values()], default=None)
            row["new_policy_earliest_recovery_at"] = (
                datetime.fromtimestamp(soonest, tz=timezone.utc).isoformat()
                if soonest is not None
                else None
            )
            if freed and (usable is None or int(usable) > 0):
                row["verdict"] = "WOULD_CLAIM_OR_QUEUE"
            elif soonest is not None and soonest - finished <= budget - old_wait:
                row["verdict"] = "WOULD_QUEUE_UNTIL_RECOVERY"
            else:
                row["verdict"] = "STILL_EXHAUSTED"
        rows.append(row)

    verdicts = Counter(row["verdict"] for row in rows)
    kinds = Counter(row["failure_kind"] for row in rows)
    resolved = sum(count for verdict, count in verdicts.items() if verdict.startswith("WOULD_"))
    return {
        "window_start": datetime.fromtimestamp(window_start, tz=timezone.utc).isoformat(),
        "window_end": datetime.fromtimestamp(window_end, tz=timezone.utc).isoformat(),
        "operations_in_window": len(in_window),
        "pool_failures": len(rows),
        "pool_failures_by_kind": dict(sorted(kinds.items())),
        "verdicts": dict(sorted(verdicts.items())),
        "would_queue_or_rotate": resolved,
        "assumed_timeout_seconds": timeout_seconds,
        "assumed_timeout_cooldown_seconds": timeout_cooldown_seconds,
        "new_timeout_cooldown_seconds": new_timeout_cooldown_seconds,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--operation-root",
        default=str(Path.home() / ".local/state/nexus-agy-operations"),
    )
    parser.add_argument("--hours", type=float, default=48.0)
    parser.add_argument("--until", help="ISO-8601 window end (default: now)")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Assumed --timeout of each dispatch (records do not store it)",
    )
    parser.add_argument(
        "--timeout-cooldown-minutes",
        type=float,
        default=DEFAULT_TIMEOUT_COOLDOWN_MINUTES,
        help="Manager cooldown the old dispatcher applied after a TIMEOUT",
    )
    parser.add_argument("--rows", action="store_true", help="Include one row per failure")
    args = parser.parse_args(argv)

    end = _ts(args.until) if args.until else datetime.now(timezone.utc).timestamp()
    if end is None:
        parser.error("--until must be ISO-8601")
    start = end - timedelta(hours=args.hours).total_seconds()
    report = replay(
        load_records(Path(args.operation_root).expanduser()),
        window_start=start,
        window_end=end,
        timeout_seconds=args.timeout_seconds,
        timeout_cooldown_seconds=args.timeout_cooldown_minutes * 60.0,
    )
    if not args.rows:
        report.pop("rows")
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
