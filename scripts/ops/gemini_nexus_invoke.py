#!/usr/bin/env python3
"""
Reliable Gemini headless invoker for Nexus workflows.

Features:
- single-flight lock (prevent concurrent invocations)
- preflight probe
- timeout + retry with backoff (skipped for critical failures like inactivity timeout)
- explicit classification for auth-loop / timeout / inactivity
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
GEMINI_BIN = Path(os.environ.get("GEMINI_BIN", "/Users/jameschen/.npm-global/bin/gemini"))
DEFAULT_LOCK = Path("/tmp/nexus_gemini_invoke.lock")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# We keep this for context but don't strictly require it if it's missing
try:
    from nexus.core.decorators import nexus_metabolize
except ImportError:
    def nexus_metabolize(task_name=None):
        return lambda func: func

AUTH_PROMPT = "Opening authentication page in your browser. Do you want to continue? [Y/n]:"


def _gemini_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    # These flags are Nexus-side routing/contract signals. Passing them through
    # to the Gemini CLI changes auth/headless behavior on local Code Assist
    # sessions and can force an interactive browser prompt.
    env.pop("NEXUS_RUNNER", None)
    env.pop("GEMINI_SANDBOX", None)
    return env


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
    inactivity_timeout_sec: int | None = None,
) -> tuple[int, str, float, str]:
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
    start_time = time.time()
    output_chunks = []
    return_code = 0
    classification = "OK"

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=_gemini_subprocess_env(),
            bufsize=1,
        )

        last_activity_time = time.time()
        
        import selectors
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)

        while True:
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Wall clock timeout check
            if elapsed > timeout_sec:
                proc.kill()
                classification = "TIMEOUT_WALLCLOCK"
                return_code = 124
                break
            
            # Inactivity timeout check
            if inactivity_timeout_sec and (current_time - last_activity_time) > inactivity_timeout_sec:
                proc.kill()
                classification = "TIMEOUT_INACTIVITY"
                return_code = 124
                break

            # Poll for output
            events = sel.select(timeout=1.0)
            if events:
                line = proc.stdout.readline()
                if line:
                    output_chunks.append(line)
                    print(line, end="", flush=True)
                    last_activity_time = time.time()
                else:
                    # EOF
                    break
            
            if proc.poll() is not None:
                # Process finished but might still have data in pipe
                remaining = proc.stdout.read()
                if remaining:
                    output_chunks.append(remaining)
                    print(remaining, end="", flush=True)
                break

        if proc.poll() is None:
            proc.kill()
            proc.wait()
        else:
            return_code = proc.returncode

    except Exception as exc:
        output_chunks.append(str(exc))
        return_code = 1
        classification = "ERROR"

    final_output = "".join(output_chunks)
    elapsed_sec = round(time.time() - start_time, 4)
    
    if classification == "OK":
        classification = _classify(return_code, final_output)

    return return_code, final_output, elapsed_sec, classification


def _classify(exit_code: int, output: str) -> str:
    if AUTH_PROMPT in output:
        return "AUTH_LOOP"
    if exit_code == 124:
        # Should be caught in the loop, but as a backup
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
    parser.add_argument("--inactivity-timeout-sec", type=int, default=0, help="Timeout if no output for N seconds (0=disabled)")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-sec", type=int, default=3)
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK))
    parser.add_argument("--preflight", action="store_true", help="Run a tiny probe before task execution")
    parser.add_argument("--preflight-only", action="store_true", help="Run only preflight probe and exit")
    parser.add_argument("--report-file", default="", help="Optional json report file path")
    args = parser.parse_args()

    if not GEMINI_BIN.exists():
        print(json.dumps({"status": "error", "reason": "gemini_bin_missing", "path": str(GEMINI_BIN)}))
        return 2

    cwd = Path(args.cwd).resolve()
    lock_path = Path(args.lock_file).resolve()
    prompt = _read_prompt(args.prompt, args.prompt_file)
    inact_timeout = args.inactivity_timeout_sec if args.inactivity_timeout_sec > 0 else None

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
            p_code, p_out, p_elap, p_cls = _run_once(
                model=args.model,
                prompt="reply with exactly: OK",
                cwd=cwd,
                timeout_sec=min(60, args.timeout_sec),
                inactivity_timeout_sec=inact_timeout,
            )
            attempts.append({
                "phase": "preflight", 
                "exit_code": p_code, 
                "classification": p_cls,
                "elapsed_sec": p_elap
            })
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
            if args.preflight_only:
                report = {
                    "status": "ok",
                    "reason": "preflight_ok",
                    "attempts": attempts,
                }
                if args.report_file:
                    Path(args.report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False))
                return 0

        for i in range(1, args.max_retries + 2):
            code, output, elap, cls = _run_once(
                model=args.model,
                prompt=prompt,
                cwd=cwd,
                timeout_sec=args.timeout_sec,
                inactivity_timeout_sec=inact_timeout,
            )
            attempts.append({
                "phase": "task", 
                "attempt": i, 
                "exit_code": code, 
                "classification": cls,
                "elapsed_sec": elap
            })
            if cls == "OK":
                report = {
                    "status": "ok",
                    "attempts": attempts,
                    "meta": {"prompt_bytes": len(prompt.encode("utf-8"))},
                    "output": output.strip()[-4000:],
                }
                if args.report_file:
                    Path(args.report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                # Main output already printed via _run_once
                return 0
            
            # STOP RETRY STORM for critical infrastructure issues
            if cls in ["AUTH_LOOP", "TIMEOUT_INACTIVITY", "TIMEOUT_WALLCLOCK"]:
                break
                
            if i <= args.max_retries:
                print(f"[Retry {i}] Failed with {cls}, backing off...", file=sys.stderr)
                time.sleep(args.retry_backoff_sec * i)

        report = {
            "status": "fail",
            "reason": attempts[-1]["classification"] if attempts else "unknown",
            "attempts": attempts,
            "meta": {"prompt_bytes": len(prompt.encode("utf-8"))},
            "hint": "If AUTH_LOOP or TIMEOUT, check connectivity or split task.",
        }
        if args.report_file:
            Path(args.report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 5
    finally:
        _release_lock(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
