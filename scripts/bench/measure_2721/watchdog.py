"""Row bookkeeping for workspace-35's run watchdog (#2721).

Protocol (in ``<run_root>/run/``):
* ``current_row.json``: written before each row (row_id, task_id, arm,
  started_at, cap_s); updated with ``snapshot_taken`` once the diff is captured;
  ``started_at`` (UTC, trailing ``Z``) is written once per row and never
  rewritten -- workspace-35's supervisor kills leftover verifier pytest started
  after ``started_at - 5 s``; the row itself carries the same ``started_at``;
* ``rows_done``: an integer, incremented after each row;
* ``infra_events.jsonl``: written by the watchdog; a row listed there is
  INFRA and is re-run in every arm.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def _run_dir(run_root: Path) -> Path:
    path = Path(run_root) / "run"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_atomic(path: Path, text: str) -> None:
    partial = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)


def begin_row(run_root: Path, *, row_id: str, task_id: str, arm: str, cap_s: float) -> str:
    """Write ``current_row.json``; returns its ``started_at`` (the row records the same value)."""
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_atomic(_run_dir(run_root) / "current_row.json", json.dumps({
        "row_id": row_id, "task_id": task_id, "arm": arm, "cap_s": cap_s,
        "started_at": started_at, "snapshot_taken": False,
    }, sort_keys=True))
    return started_at


def mark_snapshot(run_root: Path) -> None:
    path = _run_dir(run_root) / "current_row.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data["snapshot_taken"] = True
    data["snapshot_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_atomic(path, json.dumps(data, sort_keys=True))


def end_row(run_root: Path) -> int:
    path = _run_dir(run_root) / "rows_done"
    done = int(path.read_text().strip() or 0) + 1 if path.is_file() else 1
    _write_atomic(path, f"{done}\n")
    return done


def infra_event_for(run_root: Path, row_id: str) -> Optional[dict[str, Any]]:
    """The watchdog's event for ``row_id`` (it makes the row INFRA), else None."""
    path = _run_dir(run_root) / "infra_events.jsonl"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("row_id") == row_id:
            return event
    return None
