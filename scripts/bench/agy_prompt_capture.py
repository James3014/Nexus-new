#!/usr/bin/env python3
"""Bench-only ``agy`` wrapper that records the exact prompt each arm sends (online A/B S21).

The runner puts a directory whose ``agy`` execs this file first on PATH and points
``NEXUS_AGY_BIN`` at it, so the bare arm (scripts/bench/agy_provider) and the with-Nexus arm
(runtime print-CLI transport) cross the same boundary.  Each call appends one JSON record to
``$NEXUS_BENCH_PROMPT_CAPTURE_DIR/<arm>__<key>.jsonl`` and then runs the real binary
(``$NEXUS_BENCH_PROMPT_CAPTURE_REAL``) with identical argv/stdin.

* arm/key come from ``NEXUS_BENCH_ARM`` / ``NEXUS_BENCH_CAPTURE_KEY`` set by the runner per leg;
  a call that arrives without them is recorded as ``unknown`` (the audit then fails closed).
* stdin is consumed only when the prompt is not in argv (``-p``/``--print`` value) and stdin is
  a pipe or regular file; it is read to EOF (blocking) and forwarded unchanged.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

PRINT_FLAGS = ("-p", "--print")


def prompt_from_argv(argv: list[str]) -> str | None:
    for index, item in enumerate(argv):
        if item in PRINT_FLAGS and index + 1 < len(argv):
            return argv[index + 1]
        for flag in PRINT_FLAGS:
            if item.startswith(flag + "="):
                return item.split("=", 1)[1]
    return None


def _stdin_is_data() -> bool:
    try:
        mode = os.fstat(sys.stdin.fileno()).st_mode
    except (OSError, ValueError):
        return False
    return stat.S_ISFIFO(mode) or stat.S_ISREG(mode)


def capture_record(argv: list[str], stdin_text: str, env: dict[str, str]) -> dict[str, object]:
    prompt = prompt_from_argv(argv)
    return {
        "schema": "nexus_bench_prompt_capture_v1",
        "arm": env.get("NEXUS_BENCH_ARM") or "unknown",
        "key": env.get("NEXUS_BENCH_CAPTURE_KEY") or "unknown",
        "task_id": env.get("NEXUS_TASK_ID") or "",
        "argv": list(argv),
        "prompt_transport": "argv" if prompt is not None else "stdin",
        "prompt": prompt if prompt is not None else stdin_text,
        "ts": time.time(),
        "pid": os.getpid(),
    }


def write_record(record: dict[str, object], capture_dir: str) -> Path:
    root = Path(capture_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{record['arm']}__{record['key']}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def main(argv: list[str]) -> int:
    env = dict(os.environ)
    real = env.get("NEXUS_BENCH_PROMPT_CAPTURE_REAL") or ""
    if not real:
        sys.stderr.write("agy_prompt_capture: NEXUS_BENCH_PROMPT_CAPTURE_REAL is not set\n")
        return 127
    stdin_bytes = b""
    read_stdin = prompt_from_argv(argv) is None and _stdin_is_data()
    if read_stdin:
        stdin_bytes = sys.stdin.buffer.read()
    capture_dir = env.get("NEXUS_BENCH_PROMPT_CAPTURE_DIR") or ""
    if capture_dir and (prompt_from_argv(argv) is not None or read_stdin):
        write_record(capture_record(argv, stdin_bytes.decode("utf-8", "replace"), env), capture_dir)
    if not read_stdin:
        os.execv(real, [real, *argv])
    proc = subprocess.run([real, *argv], input=stdin_bytes, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
