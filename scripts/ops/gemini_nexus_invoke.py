#!/usr/bin/env python3
"""
Reliable Gemini headless invoker for Nexus workflows.

Features:
- single-flight lock (prevent concurrent invocations)
- preflight probe
- timeout + retry with backoff
- explicit classification for auth-loop / timeout / non-zero exit
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GEMINI_BIN = Path("/Users/jameschen/.npm-global/bin/gemini")
DEFAULT_LOCK = Path("/tmp/nexus_gemini_invoke.lock")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.core.decorators import nexus_metabolize
AUTH_PROMPT = "Opening authentication page in your browser. Do you want to continue? [Y/n]:"


def _acquire_lock(lock_path: Path) -> bool:
    try:
        # O_EXCL gives us an atomic single-flight lock
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _run_once(
    *,
    model: str,
    prompt: str,
    cwd: Path,
    timeout_sec: int,
) -> tuple[int, str]:
    cmd = [
        str(GEMINI_BIN),
        "-m",
        model,
        "-y",
        "--output-format",
        "text",
        "-p",
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ, "GEMINI_SANDBOX": "true"},
        )
        output = f"{proc.stdout or ''}{proc.stderr or ''}"
        return proc.returncode, output
    except subprocess.TimeoutExpired as exc:
        out = f"{exc.stdout or ''}{exc.stderr or ''}"
        return 124, out


def _classify(exit_code: int, output: str) -> str:
    if AUTH_PROMPT in output:
        return "AUTH_LOOP"
    if exit_code == 124:
        return "TIMEOUT"
    if exit_code != 0:
        return "NON_ZERO_EXIT"
    return "OK"


def _read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if prompt and prompt_file:
        raise ValueError("Use either --prompt or --prompt-file, not both.")
    if prompt_file:
        return Path(prompt_file).read_text(encoding="utf-8")
    if prompt:
        return prompt
    raise ValueError("One of --prompt or --prompt-file is required.")


@nexus_metabolize(task_name="Headless Gemini Invoker")
def main() -> int:
    parser = argparse.ArgumentParser(description="Reliable Gemini+Nexus headless invoker")
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--prompt-file", default=None)
    parser.add_argument("--cwd", default=str(REPO_ROOT))
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-sec", type=int, default=3)
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK))
    parser.add_argument("--preflight", action="store_true", help="Run a tiny probe before task execution")
    parser.add_argument("--report-file", default="", help="Optional json report file path")
    args = parser.parse_args()

    if not GEMINI_BIN.exists():
        print(json.dumps({"status": "error", "reason": "gemini_bin_missing", "path": str(GEMINI_BIN)}))
        return 2

    cwd = Path(args.cwd).resolve()
    lock_path = Path(args.lock_file).resolve()
    prompt = _read_prompt(args.prompt, args.prompt_file)

    if not _acquire_lock(lock_path):
        report = {
            "status": "blocked",
            "reason": "single_flight_lock_active",
            "lock_file": str(lock_path),
        }
        print(json.dumps(report, ensure_ascii=False))
        return 3

    attempts: list[dict] = []
    try:
        if args.preflight:
            p_code, p_out = _run_once(
                model=args.model,
                prompt="reply with exactly: OK",
                cwd=cwd,
                timeout_sec=min(30, args.timeout_sec),
            )
            p_cls = _classify(p_code, p_out)
            attempts.append({"phase": "preflight", "exit_code": p_code, "classification": p_cls})
            if p_cls != "OK" or "OK" not in p_out:
                report = {
                    "status": "fail",
                    "reason": "preflight_failed",
                    "attempts": attempts,
                    "hint": "Run interactive `gemini` once to refresh auth/session.",
                }
                if args.report_file:
                    Path(args.report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False))
                return 4

        for i in range(1, args.max_retries + 2):
            code, output = _run_once(
                model=args.model,
                prompt=prompt,
                cwd=cwd,
                timeout_sec=args.timeout_sec,
            )
            cls = _classify(code, output)
            attempts.append({"phase": "task", "attempt": i, "exit_code": code, "classification": cls})
            if cls == "OK":
                report = {
                    "status": "ok",
                    "attempts": attempts,
                    "output": output.strip(),
                }
                if args.report_file:
                    Path(args.report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(output.strip())
                return 0
            if cls == "AUTH_LOOP":
                # do not spam retries if auth loop is detected
                break
            if i <= args.max_retries:
                time.sleep(args.retry_backoff_sec * i)

        report = {
            "status": "fail",
            "reason": attempts[-1]["classification"] if attempts else "unknown",
            "attempts": attempts,
            "hint": "If AUTH_LOOP, run interactive `gemini` once and approve browser auth.",
        }
        if args.report_file:
            Path(args.report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 5
    finally:
        _release_lock(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
