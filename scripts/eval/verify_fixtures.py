#!/usr/bin/env python3
"""Verify every memory_ab_tasks_v1 fixture is red before any repair.

Each fixture is copied to a temp dir and its repro.py is executed there. A
fixture is valid only when repro exits non-zero (the bug is present) within
the time budget. Exit 0 when all fixtures are red, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "memory_ab_tasks_v1"
REPRO_TIME_BUDGET_SECONDS = 5.0
REPRO_HARD_TIMEOUT_SECONDS = 30
REQUIRED_KEYS = ("id", "bug_class", "variant", "problem_statement", "target_file", "repro_file")


def load_task(task_dir: Path) -> dict:
    meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_KEYS if key not in meta]
    if missing:
        raise ValueError(f"{task_dir}: task.json missing {missing}")
    if meta["id"] != task_dir.name:
        raise ValueError(f"{task_dir}: task id {meta['id']!r} does not match directory name")
    for name in (meta["target_file"], meta["repro_file"]):
        if not (task_dir / name).is_file():
            raise ValueError(f"{task_dir}: missing {name}")
    return meta


def run_repro(work_dir: Path, repro_file: str, python: str = sys.executable) -> tuple[int, float, str]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [python, repro_file],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=REPRO_HARD_TIMEOUT_SECONDS,
        )
        returncode, output = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        output = f"TIMEOUT after {REPRO_HARD_TIMEOUT_SECONDS}s: {exc}"
    return returncode, time.monotonic() - started, output


def verify_fixture(task_dir: Path) -> dict:
    meta = load_task(task_dir)
    with tempfile.TemporaryDirectory(prefix="memory_ab_fixture_") as tmp:
        work = Path(tmp) / meta["id"]
        shutil.copytree(task_dir, work, ignore=shutil.ignore_patterns("__pycache__"))
        returncode, elapsed, output = run_repro(work, meta["repro_file"])
    red = returncode != 0
    within_budget = elapsed < REPRO_TIME_BUDGET_SECONDS
    return {
        "task_id": meta["id"],
        "bug_class": meta["bug_class"],
        "red": red,
        "returncode": returncode,
        "elapsed_sec": round(elapsed, 3),
        "within_budget": within_budget,
        "ok": red and within_budget,
        "output_tail": output.strip().splitlines()[-1:] if output.strip() else [],
    }


def verify_all(fixtures_dir: Path = FIXTURES_DIR) -> list[dict]:
    task_dirs = sorted(p for p in fixtures_dir.iterdir() if (p / "task.json").is_file())
    return [verify_fixture(p) for p in task_dirs]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks-dir", type=Path, default=FIXTURES_DIR, help="fixture set to verify (default: v1)")
    args = parser.parse_args(argv)
    results = verify_all(args.tasks_dir)
    for item in results:
        status = "RED" if item["ok"] else "BAD"
        print(f"{status:4} {item['task_id']:32} rc={item['returncode']} t={item['elapsed_sec']}s {item['output_tail']}")
    bad = [item["task_id"] for item in results if not item["ok"]]
    print(f"{len(results) - len(bad)}/{len(results)} fixtures red")
    return 1 if bad or not results else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
