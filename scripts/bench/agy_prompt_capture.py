#!/usr/bin/env python3
"""Bench-only ``agy`` wrapper that records the exact prompt each arm sends (online A/B S21).

The runner puts a directory whose ``agy`` execs this file first on PATH and points
``NEXUS_AGY_BIN`` and ``NEXUS_AGY_EXECUTABLE`` at it, so the bare arm (scripts/bench/agy_provider)
and the with-Nexus arm (runtime print-CLI transport) cross the same boundary.  Each model call
writes one new JSON file into this run's private capture dir (``$NEXUS_BENCH_PROMPT_CAPTURE_DIR``,
created 0700 by the runner) and then runs the real binary (``$NEXUS_BENCH_PROMPT_CAPTURE_REAL``)
with identical argv/stdin.

* arm/key/run come from ``NEXUS_BENCH_ARM`` / ``NEXUS_BENCH_CAPTURE_KEY`` /
  ``NEXUS_BENCH_CAPTURE_RUN_ID`` set by the runner; a call without them is recorded as
  ``unknown`` and the audit fails closed.
* Files are created with ``O_CREAT|O_EXCL|O_NOFOLLOW`` (never appended, never through a symlink).
* stdin is consumed whenever the prompt is not in argv and stdin is not a TTY (pipe, file or
  socket); it is read to EOF and forwarded unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

PRINT_FLAGS = ("-p", "--print")


class CaptureRefused(RuntimeError):
    """The capture location is not a private regular directory/file of this run."""


def prompt_from_argv(argv: list[str]) -> str | None:
    for index, item in enumerate(argv):
        if item in PRINT_FLAGS and index + 1 < len(argv) and not argv[index + 1].startswith("-"):
            return argv[index + 1]
        for flag in PRINT_FLAGS:
            if item.startswith(flag + "="):
                return item.split("=", 1)[1]
    return None


def _has_print_flag(argv: list[str]) -> bool:
    return any(item in PRINT_FLAGS or item.startswith(("-p=", "--print=")) for item in argv)


def _stdin_has_data_source() -> bool:
    try:
        return not os.isatty(sys.stdin.fileno())
    except (OSError, ValueError):
        return False


def capture_record(argv: list[str], stdin_text: str, env: dict[str, str]) -> dict[str, object]:
    prompt = prompt_from_argv(argv)
    text = prompt if prompt is not None else stdin_text
    return {
        "schema": "nexus_bench_prompt_capture_v2",
        "run_id": env.get("NEXUS_BENCH_CAPTURE_RUN_ID") or "unknown",
        "arm": env.get("NEXUS_BENCH_ARM") or "unknown",
        "key": env.get("NEXUS_BENCH_CAPTURE_KEY") or "unknown",
        "task_id": env.get("NEXUS_TASK_ID") or "",
        "argv": list(argv),
        "prompt_transport": "argv" if prompt is not None else "stdin",
        "prompt": text,
        "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "ts": time.time(),
        "pid": os.getpid(),
    }


def _private_dir(path: Path) -> Path:
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise CaptureRefused(f"capture dir is not a real directory: {path}")
    return path


def write_record(record: dict[str, object], capture_dir: str) -> Path:
    root = _private_dir(Path(capture_dir))
    name = f"{record['arm']}__{record['key']}__{time.time_ns()}-{os.getpid()}.json"
    path = root / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
    return path


def main(argv: list[str]) -> int:
    env = dict(os.environ)
    real = env.get("NEXUS_BENCH_PROMPT_CAPTURE_REAL") or ""
    if not real:
        sys.stderr.write("agy_prompt_capture: NEXUS_BENCH_PROMPT_CAPTURE_REAL is not set\n")
        return 127
    stdin_bytes = b""
    read_stdin = prompt_from_argv(argv) is None and _stdin_has_data_source()
    if read_stdin:
        stdin_bytes = sys.stdin.buffer.read()
    capture_dir = env.get("NEXUS_BENCH_PROMPT_CAPTURE_DIR") or ""
    if capture_dir and (_has_print_flag(argv) or stdin_bytes):
        write_record(capture_record(argv, stdin_bytes.decode("utf-8", "replace"), env), capture_dir)
    if not read_stdin:
        os.execv(real, [real, *argv])
    proc = subprocess.run([real, *argv], input=stdin_bytes, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
