"""Measurement-only snapshot of the worker's raw Target diff (Issue #2721).

The #2721 re-measure scores the bare arm and the Nexus P1 arm on the same
thing: the worker's raw worktree diff at the moment it stops, before Nexus
verification, Candidate capture or cleanup can change or drop it.  This module
takes that snapshot for the P1 arm.

It is enabled ONLY when ``NEXUS_MEASUREMENT_WORKTREE_DIFF=1`` is set in the
process environment at start (read once, at import, as #2742 does); the live
Gateway never sets it, so for live nothing here runs: no git command, no new
task-state key.  A worker child process inherits the start-time value, never a
value set later in the parent (``align_child_env``).

The diff is computed exactly like the bare arm's ``capture_diff``
(``scripts/bench/measure_2721/common.py``): a throwaway ``GIT_INDEX_FILE`` in a
temporary directory, ``read-tree <base>``, ``add -A -- .``, then
``diff --cached --binary --no-color --no-ext-diff <base>``.  The worktree's own
index and files are untouched.  git runs hardened (no fsmonitor, hooks or
transports; no inherited ``GIT_*``; no system or global config; no prompt;
stdin closed) within one time budget, and the stored text is capped at 8 MiB.

``record_after_worker`` is called by the runtime coordination bridge right
after ``WorkerRegistry.invoke`` returns or raises (a timed-out worker returns a
receipt after its process group was killed), so the snapshot exists before the
runtime records ``WORKER_COMPLETED`` and before escalation, finalization,
verification, capture or cleanup touch the Target.  It never raises and never
changes the task outcome: any failure is recorded as
``measurement_worktree_diff_error``.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Optional

MEASUREMENT_WORKTREE_DIFF_ENV = "NEXUS_MEASUREMENT_WORKTREE_DIFF"
# Snapshot taken once at import (= process start); a variable set later must
# not enable anything (#2742 pattern).
MEASUREMENT_WORKTREE_DIFF_AT_START = (
    str(os.environ.get(MEASUREMENT_WORKTREE_DIFF_ENV, "") or "").strip() == "1"
)
MAX_DIFF_BYTES = 8 * 1024 * 1024
GIT_TIME_BUDGET_SECONDS = 120.0
_GIT_SAFE_CONFIG = (
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "protocol.allow=never",
)  # fmt: skip

DIFF_KEY = "measurement_worktree_diff"
SHA256_KEY = "measurement_worktree_diff_sha256"
BYTES_KEY = "measurement_worktree_diff_bytes"
TRUNCATED_KEY = "measurement_worktree_diff_truncated"
BASE_KEY = "measurement_worktree_diff_base"
ERROR_KEY = "measurement_worktree_diff_error"
INVOCATION_KEY = "measurement_worktree_diff_invocation"
STATE_KEYS = (DIFF_KEY, SHA256_KEY, BYTES_KEY, TRUNCATED_KEY, BASE_KEY, ERROR_KEY, INVOCATION_KEY)


class MeasurementDiffError(RuntimeError):
    """A failed snapshot; ``str(exc)`` is the short code that is recorded."""


def enabled() -> bool:
    """Whether the start-time snapshot of the environment enabled the capture."""
    return MEASUREMENT_WORKTREE_DIFF_AT_START


def align_child_env(env: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Give a worker child process the start-time value, not a later one.

    With the variable unset at start and unset now this changes nothing.
    """
    if MEASUREMENT_WORKTREE_DIFF_AT_START:
        env[MEASUREMENT_WORKTREE_DIFF_ENV] = "1"
    else:
        env.pop(MEASUREMENT_WORKTREE_DIFF_ENV, None)
    return env


def _git_env(index_file: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_INDEX_FILE": index_file,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    })
    return env


def _run_git(
    worktree: str,
    args: list[str],
    env: Mapping[str, str],
    deadline: float,
    step: str,
    **kwargs: Any,
) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise MeasurementDiffError("git_timeout")
    try:
        result = subprocess.run(
            ["git", *_GIT_SAFE_CONFIG, *args],
            cwd=worktree,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            timeout=remaining,
            check=False,
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        raise MeasurementDiffError("git_timeout") from exc
    except OSError as exc:
        raise MeasurementDiffError(f"git_unavailable:{step}") from exc
    if result.returncode != 0:
        raise MeasurementDiffError(f"git_failed:{step}")


def capture_worktree_diff(
    worktree: str,
    base: str,
    *,
    max_bytes: int = MAX_DIFF_BYTES,
    time_budget_seconds: float = GIT_TIME_BUDGET_SECONDS,
) -> dict[str, Any]:
    """The bare arm's ``capture_diff`` rule, hardened and bounded.

    Returns the state values (diff text capped at ``max_bytes``, sha256 and
    byte count of the full diff, truncation flag, base).  Raises
    ``MeasurementDiffError`` with a short code on any failure.
    """
    if not base:
        raise MeasurementDiffError("base_missing")
    if not worktree or not Path(worktree).is_dir():
        raise MeasurementDiffError("worktree_missing")
    deadline = time.monotonic() + time_budget_seconds
    with tempfile.TemporaryDirectory(prefix="nexus-m2721-index-") as tmp:
        env = _git_env(str(Path(tmp) / "index"))
        quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        _run_git(worktree, ["read-tree", base], env, deadline, "read_tree", **quiet)
        _run_git(worktree, ["add", "-A", "--", "."], env, deadline, "add", **quiet)
        out_path = Path(tmp) / "diff.out"
        with out_path.open("wb") as out:
            _run_git(
                worktree,
                ["diff", "--cached", "--binary", "--no-color", "--no-ext-diff", base],
                env,
                deadline,
                "diff",
                stdout=out,
                stderr=subprocess.DEVNULL,
            )
        digest = hashlib.sha256()
        total = 0
        head = bytearray()
        with out_path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                total += len(chunk)
                if len(head) < max_bytes:
                    head.extend(chunk[: max_bytes - len(head)])
    return {
        DIFF_KEY: bytes(head).decode("utf-8", errors="replace"),
        SHA256_KEY: digest.hexdigest(),
        BYTES_KEY: total,
        TRUNCATED_KEY: total > max_bytes,
        BASE_KEY: base,
    }


def record_after_worker(
    *,
    read_state: Callable[[str], Optional[Mapping[str, Any]]],
    mutate_state: Callable[[str, Callable[[dict[str, Any]], None]], Any],
    task_id: Any,
    attempt_id: str,
    lease: Any,
    invocation: int,
) -> None:
    """Persist the snapshot for one worker invocation; never raises.

    Write-once per invocation: a resumed run of the same invocation keeps the
    first snapshot (or the first error).  ``invocation`` counts the execution
    receipts recorded before this worker ran, so a later escalated worker
    (a fresh Target, the one P1 finalizes) replaces the earlier snapshot.
    """
    if not MEASUREMENT_WORKTREE_DIFF_AT_START or not task_id:
        return
    try:
        state = read_state(str(task_id)) or {}
        if _already_recorded(state, invocation):
            return
        base = str(
            getattr(lease, "initial_head", "") or state.get("target_initial_revision") or ""
        ).strip()
        worktree = str(getattr(lease, "target_worktree", "") or "")
        try:
            values: dict[str, Any] = capture_worktree_diff(worktree, base)
        except MeasurementDiffError as exc:
            values = {ERROR_KEY: str(exc), BASE_KEY: base}
        except Exception as exc:  # noqa: BLE001 - measurement never changes the outcome
            values = {ERROR_KEY: f"unexpected:{type(exc).__name__}", BASE_KEY: base}
        values[INVOCATION_KEY] = int(invocation)

        def persist(current: dict[str, Any]) -> None:
            if str(current.get("attempt_id") or "") != str(attempt_id or ""):
                return
            if _already_recorded(current, invocation):
                return
            for key in STATE_KEYS:
                current.pop(key, None)
            current.update(values)

        mutate_state(str(task_id), persist)
    except Exception:  # noqa: BLE001 - measurement never changes the outcome
        try:
            mutate_state(
                str(task_id),
                lambda current: current.setdefault(ERROR_KEY, "persist_failed"),
            )
        except Exception:  # noqa: BLE001
            pass


def _already_recorded(state: Mapping[str, Any], invocation: int) -> bool:
    if DIFF_KEY not in state and ERROR_KEY not in state:
        return False
    recorded = state.get(INVOCATION_KEY)
    recorded = recorded if isinstance(recorded, int) and not isinstance(recorded, bool) else 0
    return recorded >= invocation
