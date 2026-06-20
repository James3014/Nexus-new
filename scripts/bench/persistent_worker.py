#!/usr/bin/env python3
"""
Phase 6: Persistent Worker for Nexus Benchmark Runner

Keeps Nexus runtime alive across multiple tasks.
Eliminates ~10-15s cold start per task (Python startup + Nexus import).

Protocol: stdin/stdout JSON lines
  Input:  {"action": "run_cli", "args": ["bug", "--task", "..."], "env": {...}, "timeout_sec": 180}
  Output: {"status": "ok", "stdout": "...", "stderr": "...", "returncode": 0, "elapsed_sec": float}
  Input:  {"action": "shutdown"}
  Output: {"status": "shutdown"}
"""
from __future__ import annotations

import json
import os
import sys
import time
import logging
import subprocess
import tempfile
from pathlib import Path

# Suppress noisy logs during worker lifetime
logging.basicConfig(level=logging.WARNING)

# ── Cold start: one-time imports (~10-15s) ──────────────────────────────────
print("[worker] Starting persistent worker...", file=sys.stderr, flush=True)
_t0 = time.monotonic()

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import Nexus runtime once
os.environ.setdefault("NEXUS_FORCE_INPLACE_EXECUTOR", "1")
os.environ.setdefault("NEXUS_MEMORY_AUTO_INIT", "0")
os.environ.setdefault("NEXUS_FINDINGS_LANCEDB_SYNC", "0")
os.environ.setdefault("NEXUS_LEARN_CLOSURE_WRITEBACK", "0")

# Import key modules to warm the runtime
from nexus.services.gateway import BattlesuitGateway  # noqa: F401
from nexus.engine.local_model_policy import LocalModelPolicy  # noqa: F401

_t1 = time.monotonic()
print(f"[worker] Nexus runtime ready in {_t1 - _t0:.1f}s", file=sys.stderr, flush=True)
# ────────────────────────────────────────────────────────────────────────────


def run_cli_in_process(args: list[str], env: dict[str, str], timeout_sec: int, cwd: str) -> dict:
    """Execute nexus CLI in a subprocess, but with pre-warmed runtime."""
    cmd = [sys.executable, "scripts/engine/nexus_cli.py", *args]
    full_env = os.environ.copy()
    full_env.update(env)

    with tempfile.TemporaryDirectory(prefix="nexus-worker-") as tmp:
        stdout_path = Path(tmp) / "stdout.txt"
        stderr_path = Path(tmp) / "stderr.txt"
        start = time.monotonic()
        try:
            with stdout_path.open("w+") as stdout_f, stderr_path.open("w+") as stderr_f:
                proc = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    env=full_env,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_f,
                    stderr=stderr_f,
                    start_new_session=True,
                )
                deadline = time.monotonic() + max(1, timeout_sec)
                while True:
                    rc = proc.poll()
                    if rc is not None:
                        stdout_f.flush()
                        stderr_f.flush()
                        elapsed = time.monotonic() - start
                        return {
                            "status": "ok",
                            "stdout": stdout_path.read_text(errors="replace"),
                            "stderr": stderr_path.read_text(errors="replace"),
                            "returncode": rc,
                            "elapsed_sec": round(elapsed, 4),
                        }
                    if time.monotonic() >= deadline:
                        try:
                            os.killpg(proc.pid, 9)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                        elapsed = time.monotonic() - start
                        stdout_f.flush()
                        stderr_f.flush()
                        return {
                            "status": "timeout",
                            "stdout": stdout_path.read_text(errors="replace"),
                            "stderr": stderr_path.read_text(errors="replace"),
                            "returncode": -1,
                            "elapsed_sec": round(elapsed, 4),
                        }
                    time.sleep(0.1)
        except Exception as exc:
            elapsed = time.monotonic() - start
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(exc),
                "returncode": -1,
                "elapsed_sec": round(elapsed, 4),
            }


def handle_task(payload: dict) -> dict:
    """Execute a CLI task using the warm runtime."""
    args = payload.get("args", [])
    env = payload.get("env", {})
    timeout_sec = payload.get("timeout_sec", 180)
    cwd = payload.get("cwd", str(REPO_ROOT))

    return run_cli_in_process(args, env, timeout_sec, cwd)


def main() -> None:
    """Main loop: read JSON lines from stdin, execute, write results to stdout."""
    print("[worker] Listening for tasks on stdin...", file=sys.stderr, flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            _send({"status": "error", "error": f"Invalid JSON: {exc}"})
            continue

        action = payload.get("action", "run_cli")

        if action == "shutdown":
            _send({"status": "shutdown"})
            print("[worker] Shutdown requested.", file=sys.stderr, flush=True)
            break

        if action == "run_cli":
            result = handle_task(payload)
            _send(result)
        else:
            _send({"status": "error", "error": f"Unknown action: {action}"})


def _send(obj: dict) -> None:
    """Write a JSON line to stdout."""
    print(json.dumps(obj, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
