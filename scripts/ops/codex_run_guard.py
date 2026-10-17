#!/usr/bin/env python3
"""CLI over ``nexus.executors.codex_run_boundary`` for the Codex launcher (#2254).

Run as ``python3 -I`` from the launcher; the repository root is taken from this
file's location, never from the caller's cwd or PYTHONPATH.

  home <run_home>                          create the disposable HOME (auth only)
  snapshot <target>                        print escaping symlinks + .git state (JSON)
  verify <target>                          read the snapshot on stdin; exit 6 on change
  writeback <run_home>                     copy a refreshed auth.json back to the host
  exec <run_home> [<work_dir>] -- <cmd>    run cmd with the allowlisted env, then
                                           kill every descendant it left (#2367)
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.executors import cli_worker  # noqa: E402
from nexus.executors import codex_run_boundary as boundary  # noqa: E402

ESCAPE_EXIT = 6


def run_in_own_group(
    command: list[str], env: dict[str, str], work_dir: Optional[Path] = None
) -> int:
    """Run codex in its own session; once it exits, kill everything it left.

    The whole process group is killed while the exited leader is still
    unreaped (so its PID and group id cannot have been reused), then the
    ``cli_worker`` descendant sweep kills children that left the group with
    ``setsid``: every tracked descendant, every process carrying this run's
    tag, and every worker-era process whose cwd is under the work copy or the
    run HOME (#2367).  A sweep that cannot prove it is clean fails the run, so
    nothing can still write to the work copy when ``verify`` runs.
    """
    state: dict[str, Any] = {"group": None, "pending": []}

    def forward(signum: int, _frame: object) -> None:
        if state["group"] is None:
            state["pending"].append(signum)  # launch still in progress
            return
        try:
            os.killpg(state["group"], signum)
        except (ProcessLookupError, PermissionError):
            pass  # the group is gone or holds only the zombie leader

    # Installed before Popen: a signal during launch is queued, never lost.
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, forward)
    run_tag = secrets.token_hex(16)
    env = {**env, cli_worker.RUN_TAG_ENV: run_tag}
    roots = tuple(
        str(path) for path in (work_dir, Path(env["HOME"]) if "HOME" in env else None) if path
    )
    baseline = cli_worker.sweep_baseline()
    try:
        child = subprocess.Popen(command, env=env, start_new_session=True)
    except OSError as error:
        print(f"[nexus-enforced] codex_start_failed: {error}", file=sys.stderr)
        return 127
    state["group"] = child.pid
    for signum in state["pending"]:
        forward(signum, None)
    tracker = cli_worker.track_run(run_tag, child.pid)
    try:
        # Wait without reaping: the zombie leader pins its PID and group id.
        while True:
            try:
                os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
                break
            except InterruptedError:
                continue
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            # macOS reports EPERM for a group whose only member is the
            # zombie leader; any live member is still swept below.
            pass
        status = child.wait()
        clean = cli_worker.sweep_run(run_tag, tracker, baseline, roots)
    finally:
        tracker.stop()
        cli_worker.release_run(run_tag)
    if not clean:
        print(
            "[nexus-enforced] codex_descendant_sweep_unclean: a codex descendant could not "
            "be proven dead",
            file=sys.stderr,
        )
        return ESCAPE_EXIT
    return status if status >= 0 else 128 - status


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "home":
        reason = boundary.materialize_codex_home(Path(argv[1]))
        if reason:
            print(f"[nexus-enforced] {reason}", file=sys.stderr)
            return 2
        return 0
    if len(argv) == 2 and argv[0] == "snapshot":
        print(json.dumps(boundary.target_integrity_snapshot(Path(argv[1])), sort_keys=True))
        return 0
    if len(argv) == 2 and argv[0] == "verify":
        try:
            before = json.loads(sys.stdin.read())
        except ValueError:
            print("[nexus-enforced] codex_target_snapshot_unreadable", file=sys.stderr)
            return ESCAPE_EXIT
        failure = boundary.target_integrity_failure(
            before, boundary.target_integrity_snapshot(Path(argv[1]))
        )
        if failure:
            print(f"[nexus-enforced] {failure}: {argv[1]}", file=sys.stderr)
            return ESCAPE_EXIT
        return 0
    if len(argv) == 2 and argv[0] == "writeback":
        boundary.write_back_refreshed_auth(Path(argv[1]))
        return 0
    if len(argv) >= 4 and argv[0] == "exec" and "--" in argv[2:4]:
        home = Path(argv[1])
        work_dir = Path(argv[2]) if argv[3] == "--" else None
        command = argv[argv.index("--", 2) + 1 :]
        if not command:
            print("usage: codex_run_guard.py exec <run_home> [<work_dir>] -- cmd", file=sys.stderr)
            return 64
        env = boundary.codex_child_env(None, home=home, tmpdir=home / "tmp")
        return run_in_own_group(command, env, work_dir)
    print("usage: codex_run_guard.py home|snapshot|verify|exec ...", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
