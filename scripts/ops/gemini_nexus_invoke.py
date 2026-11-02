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
import contextlib
import fcntl
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
GEMINI_BIN = Path(os.environ.get("GEMINI_BIN", "/Users/jameschen/.npm-global/bin/gemini"))
DEFAULT_LOCK = Path("/tmp/nexus_gemini_invoke.lock")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.core import argv_command  # noqa: E402 - needs REPO_ROOT on sys.path

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


_LOCK_FDS: dict[Path, int] = {}


def _acquire_lock(lock_path: Path) -> bool:
    """Single-flight lock held with flock, so the kernel drops it when the holder dies (#3203).

    A lock file left behind by a killed run no longer blocks later runs. The
    descriptor stays open until ``_release_lock``; the file names the last holder pid.
    The Gemini child and its descendants inherit the descriptor, so the lock is held
    until the last of them exits too.
    The path is shared (``/tmp`` by default), so a symlink, a hard link or another
    user's file there raises ``OSError`` instead of being opened and truncated.
    """
    while True:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o644)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                raise OSError(f"unsafe lock file (not a private regular file): {lock_path}")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        except BaseException:
            os.close(fd)
            raise
        try:
            current = os.stat(lock_path)
        except FileNotFoundError:
            current = None
        if current is None or not os.path.samestat(os.fstat(fd), current):
            # The file was unlinked or replaced while we waited for it (an older invoker
            # unlinked it on release): retry on the file now at the path.
            os.close(fd)
            continue
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        _LOCK_FDS[lock_path] = fd
        return True


def _release_lock(lock_path: Path) -> None:
    """Close our descriptor; the lock file stays (#3203).

    Not unlinked: a descendant that left the Gemini group (``setsid``) or survived its
    SIGKILL may still hold the lock through the inherited descriptor. Unlinking would let
    the next run lock a new file at the same path beside it; keeping the file makes the
    next run wait for that holder.
    """
    fd = _LOCK_FDS.pop(lock_path, None)
    if fd is not None:
        os.close(fd)


_held_depth = 0
_held_signal: int | None = None


def _on_terminating_signal(signum: int, _frame: Any) -> None:
    global _held_signal
    if _held_depth:
        if _held_signal is None:
            _held_signal = signum
        return
    raise SystemExit(128 + signum)


@contextlib.contextmanager
def _signals_held() -> Iterator[None]:
    """Hold SIGTERM/SIGHUP for the block (as #3220 does); a held one then exits with
    128 + its number. For the reap and the group stop, which end on their own."""
    global _held_depth, _held_signal
    _held_depth += 1
    try:
        yield
    finally:
        _held_depth -= 1
        if _held_depth == 0 and _held_signal is not None:
            signum, _held_signal = _held_signal, None
            raise SystemExit(128 + signum)


@contextlib.contextmanager
def _termination_signals_raise() -> Iterator[None]:
    """Turn SIGTERM and SIGHUP into SystemExit so ``finally`` stops the Gemini group (#3203).

    Only on the main thread. An ignored signal (``nohup``) stays ignored, and a handler
    not installed from Python (``getsignal`` returns None) is left in place.
    The previous handlers are restored on the way out.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous: dict[int, Any] = {}
    try:
        for signum in (signal.SIGTERM, signal.SIGHUP):
            current = signal.getsignal(signum)
            if current is not None and current is not signal.SIG_IGN:
                previous[signum] = signal.signal(signum, _on_terminating_signal)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


GROUP_POLL_SECONDS = 0.05
GROUP_STOP_SETTLE_SECONDS = 5.0


def _group_stopped_if_exited(proc: subprocess.Popen) -> bool:
    """Non-blocking: False while the Gemini child runs. Once it has exited, SIGKILL what
    it left in its group, then reap it (``argv_command.kill_group_if_exited``), so a
    descendant does not outlive the run. The only place the child is reaped; the
    terminating signals are held, so none lands between the reap and ``returncode``."""
    with _signals_held():
        return bool(argv_command.kill_group_if_exited(proc))


def _stop_child_group(proc: subprocess.Popen) -> None:
    """SIGKILL the Gemini child's own group and reap it, unless it is already reaped.

    The child is reaped only by ``_group_stopped_if_exited``, after its group is killed,
    so while it is unreaped its pid still names its group and ``killpg`` cannot reach an
    unrelated one; once reaped, nothing is signalled.
    """
    with _signals_held():
        if proc.returncode is not None or not argv_command._leader_unreaped(proc.pid):
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass  # nothing left, or (macOS) only the exited, unreaped child is left
        deadline = time.monotonic() + GROUP_STOP_SETTLE_SECONDS
        while not _group_stopped_if_exited(proc):
            if time.monotonic() >= deadline:
                raise ChildProcessError(f"Gemini child {proc.pid} still runs after SIGKILL")
            time.sleep(GROUP_POLL_SECONDS)


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

    proc = None
    try:
        # Only _group_stopped_if_exited may reap the child (SIGCHLD at its default).
        argv_command.require_child_stays_unreaped()
        # Own session, so the whole Gemini group can be stopped. The child also inherits
        # the single-flight lock descriptor: if the invoker is SIGKILLed, the lock stays
        # held until the orphaned Gemini group is gone too (#3203). Signals are held so
        # none lands between the spawn and ``proc`` being set (``finally`` needs it).
        with _signals_held():
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=_gemini_subprocess_env(),
                bufsize=1,
                start_new_session=True,
                pass_fds=tuple(_LOCK_FDS.values()),
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
                _stop_child_group(proc)
                classification = "TIMEOUT_WALLCLOCK"
                return_code = 124
                break
            
            # Inactivity timeout check
            if inactivity_timeout_sec and (current_time - last_activity_time) > inactivity_timeout_sec:
                _stop_child_group(proc)
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
            
            if _group_stopped_if_exited(proc):
                # Process finished but might still have data in pipe
                remaining = proc.stdout.read()
                if remaining:
                    output_chunks.append(remaining)
                    print(remaining, end="", flush=True)
                break

        if proc.returncode is None and not _group_stopped_if_exited(proc):
            _stop_child_group(proc)
        elif classification == "OK":
            # A timeout already reaped the group above; keep its 124.
            return_code = proc.returncode

    except Exception as exc:
        output_chunks.append(str(exc))
        return_code = 1
        classification = "ERROR"
    finally:
        # A signal-raised exit or any other interrupt still stops the group before
        # main releases the lock.
        if proc is not None:
            _stop_child_group(proc)

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
    # Not resolve(): a symlink planted at the lock path must reach O_NOFOLLOW, not be followed.
    lock_path = Path(os.path.abspath(args.lock_file))
    prompt = _read_prompt(args.prompt, args.prompt_file)
    inact_timeout = args.inactivity_timeout_sec if args.inactivity_timeout_sec > 0 else None

    try:
        acquired = _acquire_lock(lock_path)
    except OSError as exc:
        report = {
            "status": "blocked",
            "reason": "single_flight_lock_unusable",
            "lock_file": str(lock_path),
            "detail": str(exc),
        }
        print(json.dumps(report, ensure_ascii=False))
        return 3
    if not acquired:
        report = {
            "status": "blocked",
            "reason": "single_flight_lock_active",
            "lock_file": str(lock_path),
            "hint": "The holder may be a descendant of an earlier invoker; `lsof <lock_file>` names it.",
        }
        print(json.dumps(report, ensure_ascii=False))
        return 3

    attempts: list[dict] = []
    with _termination_signals_raise():
        return _run_attempts(args, cwd, lock_path, prompt, inact_timeout, attempts)


def _run_attempts(args, cwd, lock_path, prompt, inact_timeout, attempts) -> int:
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
