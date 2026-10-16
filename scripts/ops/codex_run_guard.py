#!/usr/bin/env python3
"""CLI over ``nexus.executors.codex_run_boundary`` for the Codex launcher (#2254).

Run as ``python3 -I`` from the launcher; the repository root is taken from this
file's location, never from the caller's cwd or PYTHONPATH.

  home <run_home>                          create the disposable HOME (auth only)
  snapshot <target>                        print escaping symlinks + .git state (JSON)
  verify <target>                          read the snapshot on stdin; exit 6 on change
  exec <run_home> -- <cmd> [args...]       exec cmd with the allowlisted env
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.executors import codex_run_boundary as boundary  # noqa: E402

ESCAPE_EXIT = 6


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
    if len(argv) >= 4 and argv[0] == "exec" and argv[2] == "--":
        home = Path(argv[1])
        env = boundary.codex_child_env(None, home=home, tmpdir=home / "tmp")
        os.execvpe(argv[3], argv[3:], env)
    print("usage: codex_run_guard.py home|snapshot|verify|exec ...", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
