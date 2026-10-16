"""Model-neutral, no-shell CLI worker used by governed self-hosted execution."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Tuple

from nexus.executors.exec_policy import (
    assert_git_repo_config_safe,
    git_target_directory,
    is_git_executable,
    validate_exec,
)
from nexus.services.agy_account_pool import GITHUB_CREDENTIAL_KEYS

_logger = logging.getLogger(__name__)


class CliWorkerStatus(str, Enum):
    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"
    START_FAILED = "START_FAILED"


# HOME stays inherited because model worker CLIs keep their own provider login
# there; the GitHub credential channels (gh config dir, git global config and
# its credential helper) are redirected per request instead. See
# _isolated_github_credential_environment.
_INHERITED_ENV_ALLOWLIST = frozenset({
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONPATH",
    "TMPDIR",
    "VIRTUAL_ENV",
})


_ENV_KEY_PRESENT_SENTINEL = "present"
"""Presence-only sentinel used in env receipts.

Contract: task-scoped env values (and any hash derived from them) MUST NOT
persist in trajectory action payloads or result receipts.  Only key *names*
and this static sentinel may be stored.
"""


def bounded_environment_receipt(
    environment: Optional[Mapping[str, str]],
) -> Tuple[Tuple[str, str], ...]:
    """Bind task-scoped env key *names* without persisting values or derived hashes.

    Each entry records only the key name and a static ``"present"`` sentinel.
    Raw values and any hash derived from those values are never stored.
    """
    return tuple(sorted((str(key), _ENV_KEY_PRESENT_SENTINEL) for key in (environment or {})))


def _resolve_executable(executable: str) -> str:
    if not isinstance(executable, str) or not executable.strip():
        raise ValueError("executable must be non-empty")
    # Preserve an explicitly supplied symlink path (notably a virtualenv
    # python shim).  Resolving it to the base interpreter changes the runtime
    # environment and can make installed verifier packages disappear.
    explicit = Path(executable).expanduser()
    if explicit.is_absolute() and explicit.is_file():
        return str(explicit)
    resolved = shutil.which(executable)
    if resolved is None:
        raise ValueError(f"executable not found: {executable}")
    resolved_path = Path(resolved)
    return str(resolved_path if resolved_path.is_absolute() else resolved_path.resolve())


def _validate_worker_argv(argv: Tuple[str, ...]) -> None:
    """Thin wrapper kept for compatibility; policy lives in exec_policy."""
    if not argv:
        raise ValueError("argv must be non-empty")
    validate_exec(argv[0], argv[1:])


# GitHub credentials (GH_TOKEN / GITHUB_TOKEN / GITHUB_PAT / ...) must never
# enter a worker process namespace: a delegated worker could otherwise
# interpret an inherited broad Owner GitHub credential as external-publication
# authority.  The canonical key set is owned by
# nexus.services.agy_account_pool.GITHUB_CREDENTIAL_KEYS.
_GITHUB_CREDENTIAL_ENV_KEYS = frozenset(key.upper() for key in GITHUB_CREDENTIAL_KEYS)


def _reject_github_credentials(environment: Optional[Mapping[str, str]]) -> None:
    """Fail closed when a worker environment carries a GitHub credential key."""
    if environment is None:
        return
    present = sorted(key for key in environment if str(key).upper() in _GITHUB_CREDENTIAL_ENV_KEYS)
    if present:
        raise ValueError(
            "worker environment cannot carry GitHub credentials: " + ", ".join(present)
        )


_POST_KILL_DRAIN_SECONDS = 2.0


def _isolated_github_credential_environment(
    config_root: str, supplied: Optional[Mapping[str, str]]
) -> dict[str, str]:
    """Point GitHub credential lookups at an empty per-request directory.

    gh reads ``GH_CONFIG_DIR`` and git only reaches ``~/.git-credentials`` through
    a credential helper configured in global/system config, so both channels are
    cut without moving the worker's own provider login out of ``HOME``. Keys
    explicitly supplied through ``request.env`` (already GitHub-credential
    checked) win.
    """
    isolated = {
        "GH_CONFIG_DIR": os.path.join(config_root, "gh"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    for key in supplied or ():
        isolated.pop(str(key), None)
    return isolated


def _hash_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Optional passive trajectory context (seam only – does NOT affect execution)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CliWorkerTrajectoryContext:
    """Immutable trajectory identity context for passive telemetry seam.

    All fields are passed through to ``seal_trajectory_step`` /
    ``bind_trajectory_step_result`` without affecting CLI execution.  Any
    telemetry failure is swallowed; CLI behaviour is identical with or without
    this context.
    """

    repo_root: str
    task_id: str
    trajectory_id: str
    attempt_id: str
    step_index: int
    source_revision: str
    # Optional identity fields
    candidate_id: Optional[str] = None
    base_source_revision: Optional[str] = None
    working_state_manifest_sha256: Optional[str] = None
    # Caller-supplied pre-action state; will be redacted/bounded by the trajectory API
    pre_action_state: Any = field(default_factory=dict)


@dataclass(frozen=True)
class CliWorkerRequest:
    executable: str
    argv: Tuple[str, ...]
    cwd: str
    timeout_seconds: float = 60.0
    env: Optional[Mapping[str, str]] = None
    # Optional passive trajectory telemetry context; None preserves legacy behaviour exactly.
    trajectory_context: Optional[CliWorkerTrajectoryContext] = None
    # Optional runtime-owned macOS Seatbelt profile (SBPL text).  When set,
    # the validated command runs under ``/usr/bin/sandbox-exec -f <profile>``;
    # a missing ``sandbox-exec`` fails the start closed (#1912).
    seatbelt_profile: Optional[str] = None
    # Kill the process group and run-tagged descendants after a normal exit
    # too, not only on timeout, so nothing outlives the receipt (#1912).
    sweep_descendants_on_exit: bool = False
    # Directories whose resident processes (by cwd) are swept after exit, and
    # a strict environment mode that inherits nothing ambient: only
    # ``request.env`` plus the worker's own bookkeeping keys (#1912).
    sweep_roots: Tuple[str, ...] = ()
    exact_env: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable", _resolve_executable(self.executable))
        object.__setattr__(self, "argv", tuple(str(item) for item in self.argv))
        validate_exec(self.executable, self.argv)
        target_cwd = Path(self.cwd).expanduser().resolve(strict=False)
        if not target_cwd.is_dir():
            raise ValueError("cwd must be an existing directory")
        object.__setattr__(self, "cwd", str(target_cwd))
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        _reject_github_credentials(self.env)

    @property
    def command(self) -> Tuple[str, ...]:
        return (self.executable, *self.argv)


@dataclass
class CliWorkerResult:
    status: CliWorkerStatus
    executable_identity: str
    argv: Tuple[str, ...]
    cwd: str
    exit_code: Optional[int]
    stdout: bytes
    stderr: bytes
    wall_time_ms: int
    process_group_id: Optional[int]
    process_group_killed: bool = False
    timed_out: bool = False
    executable_sha256: str = ""
    env: Tuple[Tuple[str, str], ...] = ()
    telemetry: dict[str, int] = field(default_factory=dict)
    # None when no post-exit sweep was requested; False when a tagged
    # descendant survived the sweep.
    descendants_swept: Optional[bool] = None
    seatbelt_profile_sha256: str = ""
    # sha256 of the sorted key names of the child environment.
    env_keys_sha256: str = ""

    @staticmethod
    def hash_bytes(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    @property
    def stdout_sha256(self) -> str:
        return self.hash_bytes(self.stdout)

    @property
    def stderr_sha256(self) -> str:
        return self.hash_bytes(self.stderr)


def _kill_process_group(process: subprocess.Popen[bytes]) -> bool:
    try:
        os.killpg(process.pid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return False


_RUN_TAG_ENV = "NEXUS_CLI_WORKER_RUN_TAG"
_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
_SWEEP_DEADLINE_SECONDS = 2.0


def _tagged_pids(tag: str, starts: Optional[dict[int, Optional[int]]] = None) -> set[int]:
    """PIDs (other than ours) whose environment carries ``tag``.

    When ``starts`` is given, each match also records its Linux start time
    (read before its environ) so the caller can detect PID reuse before it
    kills; None where no ``/proc`` start time exists.
    """
    own = os.getpid()
    needle = f"{_RUN_TAG_ENV}={tag}"
    found: set[int] = set()
    proc = Path("/proc")
    if proc.is_dir() and (proc / "self" / "environ").exists():
        needle_bytes = needle.encode()
        for entry in proc.iterdir():
            if not entry.name.isdigit() or int(entry.name) == own:
                continue
            before = _proc_start_ticks(entry) if starts is not None else None
            try:
                environ = (entry / "environ").read_bytes()
            except (FileNotFoundError, ProcessLookupError):
                if _pid_alive(int(entry.name)) and not _proc_is_zombie(entry):
                    raise  # environ vanished but the process lives: unknown
                continue  # exited meanwhile
            except OSError:
                if _proc_is_zombie(entry):
                    continue  # a dead zombie's environ is unreadable; no thread runs
                try:
                    same_uid = entry.stat().st_uid == os.getuid()
                except (FileNotFoundError, ProcessLookupError):
                    continue  # exited meanwhile
                if same_uid and not _predates_run(entry, tag):
                    # One of ours we cannot inspect: unknown, not clean.
                    # (Same-uid non-dumpable system processes such as
                    # ``(sd-pam)`` that started before the worker cannot be
                    # its descendants.)
                    raise
                continue
            else:
                if not environ and _proc_state(entry) in ("Z", "X") and not _proc_is_zombie(entry):
                    # A dead thread-group leader whose other threads still run
                    # reads as an empty environ: that says nothing about the
                    # tag, so the process is unknown, not clean.
                    raise PermissionError(f"empty environ of dead leader {entry.name} with threads")
                if needle_bytes in environ:
                    found.add(int(entry.name))
                    if starts is not None:
                        starts[int(entry.name)] = before
        return found
    out = subprocess.run(
        ["ps", "-axww", "-E", "-o", "pid=,command="],
        env=_probe_env(),
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout
    if not any(line.split(None, 1)[:1] == [str(own)] for line in out.splitlines()):
        # A complete listing always includes this process.
        raise ValueError("ps -E listing does not include this process")
    for line in out.splitlines():
        if needle not in line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            # A tagged row we cannot attribute to a pid: unknown, not clean.
            # (Untagged rows may be environment continuation lines; skip them.)
            raise ValueError(f"unparseable tagged ps row: {line[:80]!r}")
        if int(parts[0]) != own:
            found.add(int(parts[0]))
            if starts is not None:
                starts[int(parts[0])] = None  # ps gives no comparable start tick
    return found


_PROBE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _probe_env() -> dict[str, str]:
    """Minimal environment for ps/lsof probes: system PATH, C locale.

    The sweep's verdict rests on these tools, so nothing inherited (a PATH
    entry, LD_PRELOAD/DYLD_* or other loader variables pointing at
    worker-writable files) may influence which code they run.
    """
    return {"PATH": _PROBE_PATH, "LC_ALL": "C", "LANG": "C"}


# run tag -> the worker's Linux start time (clock ticks since boot).
_RUN_START_TICKS: dict[str, int] = {}


def _proc_start_ticks(entry: Path) -> Optional[int]:
    """``starttime`` from ``/proc/<pid>/stat`` (clock ticks since boot), or None."""
    try:
        return int((entry / "stat").read_text().rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        return None


def _predates_run(entry: Path, tag: str) -> bool:
    """True when ``entry`` provably started before the run's worker process."""
    floor = _RUN_START_TICKS.get(tag)
    started = _proc_start_ticks(entry)
    return floor is not None and started is not None and started < floor


def _proc_state(entry: Path) -> Optional[str]:
    """The state letter from ``/proc/<pid>/stat``, or None when unreadable."""
    try:
        return (entry / "stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return None


def _proc_is_zombie(entry: Path) -> bool:
    """True when ``entry`` is a zombie or dead process with no live threads.

    ``/proc/<pid>/stat`` reports Z for a thread-group leader whose main thread
    exited while its other threads keep running, so Z/X counts as dead only
    when ``/proc/<pid>/task`` lists at most one thread. Fails closed: an
    unreadable stat or task listing is not a zombie.
    """
    state = _proc_state(entry)
    if state not in ("Z", "X"):
        return False
    try:
        threads = sum(1 for _ in (entry / "task").iterdir())
    except OSError:
        return False
    return threads <= 1


def _process_table() -> dict[int, int]:
    """``pid -> ppid`` for every visible process."""
    out = subprocess.run(
        ["ps", "-axo", "pid=,ppid="],
        env=_probe_env(),
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout
    table: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            # A partial table would let a pre-existing process pass as new.
            raise ValueError(f"unparseable ps row: {line!r}")
        if int(parts[0]) in table:
            raise ValueError(f"duplicate ps row: {line!r}")
        table[int(parts[0])] = int(parts[1])
    return table


class _DescendantTracker:
    """Record every descendant of ``root_pid`` by polling the process table.

    Catches children that clear their environment (so the run tag is lost)
    and call ``setsid`` (so the process group kill misses them), as long as
    they are observed while their parent is still alive.
    """

    def __init__(self, root_pid: int, interval: float = 0.1) -> None:
        self._root = root_pid
        self._pids: set[int] = {root_pid}
        self._interval = interval
        # Set when any poll could not read the process table: descendants
        # spawned in that gap are unknown, so the sweep cannot claim clean.
        self.probe_failed = False
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _snapshot(self) -> None:
        try:
            table = _process_table()
        except Exception:  # noqa: BLE001
            self.probe_failed = True
            return
        if os.getpid() not in table:
            self.probe_failed = True  # structurally incomplete snapshot
            return
        with self._lock:
            changed = True
            while changed:
                changed = False
                for pid, ppid in table.items():
                    if ppid in self._pids and pid not in self._pids:
                        self._pids.add(pid)
                        changed = True

    def _run(self) -> None:
        while not self._stop.is_set():
            self._snapshot()
            self._stop.wait(self._interval)

    def stop(self) -> set[int]:
        self._snapshot()
        self._stop.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            # A poll is still blocked; its outcome would arrive too late.
            self.probe_failed = True
        with self._lock:
            return set(self._pids) - {self._root}


@dataclass(frozen=True)
class _SweepBaseline:
    """Process facts recorded just before the worker starts."""

    started_at: float
    preexisting: frozenset[int]
    protected: frozenset[int]


def _ancestors(pid: int, table: dict[int, int]) -> set[int]:
    found: set[int] = set()
    while pid > 1 and pid not in found:
        found.add(pid)
        pid = table.get(pid, 1)
    return found


def _sweep_baseline() -> Optional[_SweepBaseline]:
    try:
        table = _process_table()
    except Exception:  # noqa: BLE001
        return None
    # A real snapshot always contains this process and its parent.
    if os.getpid() not in table or os.getppid() not in table:
        return None
    started_at = _ps_clock_now()
    if started_at is None:
        return None
    return _SweepBaseline(
        started_at=started_at,
        preexisting=frozenset(table),
        protected=frozenset(_ancestors(os.getpid(), table)),
    )


_START_MARGIN_SECONDS = 1.0
_LSTART_FORMAT = "%a %b %d %H:%M:%S %Y"


def _ps_clock_now() -> Optional[float]:
    """ "Now" on the clock ``ps -o lstart`` reports, as epoch seconds.

    ``lstart`` is derived from boot time plus process start ticks, which in
    VMs can drift seconds away from ``time.time()``; comparing a worker's
    ``lstart`` against the wall clock would then mistake a fresh process for
    a pre-existing one.  The start time of a ``ps`` launched now is on the
    same clock as every later ``lstart`` reading.
    """
    try:
        completed = subprocess.run(
            ["/bin/sh", "-c", "exec ps -o lstart= -p $$"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_probe_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    parts = completed.stdout.split()
    if completed.returncode != 0 or len(parts) != 5:
        return None
    try:
        return time.mktime(time.strptime(" ".join(parts), _LSTART_FORMAT))
    except ValueError:
        return None


def _started_after_by_us(pids: set[int], since: float) -> Optional[set[int]]:
    """Subset of ``pids`` owned by our uid and started at/after ``since``.

    ``ps -o lstart`` has one-second resolution, so a margin is allowed; the
    pre-start pid snapshot excludes anything that already existed.  Returns
    None when ``ps`` cannot vouch for a pid that is still alive, so callers
    fail closed instead of treating an unreadable process as absent.
    """
    if not pids:
        return set()
    try:
        completed = subprocess.run(
            ["ps", "-o", "pid=,uid=,lstart=", "-p", ",".join(str(pid) for pid in sorted(pids))],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_probe_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # ps exits 1 when some requested pid is gone; that is checked below.
    if completed.returncode not in (0, 1):
        return None
    out = completed.stdout
    uid = os.getuid()
    found: set[int] = set()
    seen: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 7 or not parts[0].isdigit() or not parts[1].isdigit():
            return None
        if int(parts[0]) in seen:
            return None
        try:
            started = time.mktime(time.strptime(" ".join(parts[2:7]), _LSTART_FORMAT))
        except ValueError:
            return None
        seen.add(int(parts[0]))
        if int(parts[1]) == uid and started >= since - _START_MARGIN_SECONDS:
            found.add(int(parts[0]))
    # A pid ps did not report is fine only if it has already exited.
    if any(_pid_alive(pid) for pid in pids - seen):
        return None
    return found


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pids_with_cwd_under(
    roots: Tuple[str, ...], baseline: Optional[_SweepBaseline] = None
) -> Optional[set[int]]:
    """Worker-era PIDs whose current directory is inside one of ``roots``.

    Only processes owned by our uid, started at or after the worker, absent
    from the pre-start snapshot, and not this process or its ancestors.
    Without a baseline nothing is killed (never kill unknown processes), and
    None is returned when roots were requested so the sweep is not reported
    clean; None also means ``lsof``/``ps`` could not be read.
    """
    if not roots:
        return set()
    if baseline is None:
        return None
    real_roots = [os.path.realpath(root).rstrip(os.sep) for root in roots]
    try:
        completed = subprocess.run(
            ["lsof", "-nP", "-a", "-d", "cwd", "-Fpn"],
            env=_probe_env(),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = completed.stdout
    # A complete listing always includes this process; partial or failed
    # output (non-zero exit) is not proof that no worker process remains.
    if completed.returncode != 0 or f"p{os.getpid()}" not in out.splitlines():
        return None
    found: set[int] = set()
    seen: set[int] = set()
    pid: Optional[int] = None
    # Each record is p<pid>, then fcwd (macOS lsof; Linux lsof omits it),
    # then n<path>.
    expect = "p"
    for line in out.splitlines():
        field = line[:1]
        if expect == "p" and field == "p" and line[1:].isdigit():
            pid = int(line[1:])
            if pid in seen:
                return None  # duplicate record
            seen.add(pid)
            expect = "f"
        elif expect == "f" and line == "fcwd":
            expect = "n"
        elif (expect == "n" or (expect == "f" and sys.platform != "darwin")) and (
            field == "n" and line[1:]
        ):
            assert pid is not None
            cwd = os.path.realpath(line[1:])
            if any(cwd == root or cwd.startswith(root + os.sep) for root in real_roots):
                found.add(pid)
            expect = "p"
        else:
            return None  # unexpected or malformed field: incomplete scan
    if expect != "p" or os.getpid() not in seen:
        return None
    found -= baseline.preexisting | baseline.protected | {os.getpid()}
    return _started_after_by_us(found, baseline.started_at)


def _sweep_clean(tracked: set[int], cwd_pids: Optional[set[int]]) -> bool:
    """Kill tracked and cwd-matched pids; unknown cwd scan never counts as clean."""
    killed = _kill_and_confirm(tracked | (cwd_pids or set()))
    return killed and cwd_pids is not None


def _kill_and_confirm(pids: set[int]) -> bool:
    """SIGKILL ``pids`` (never ourselves or our parent); True when none survive."""
    targets = {pid for pid in pids if pid > 1} - {os.getpid(), os.getppid()}
    for pid in targets:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + _SWEEP_DEADLINE_SECONDS
    while True:
        alive = set()
        for pid in targets:
            try:
                os.kill(pid, 0)
                alive.add(pid)
            except ProcessLookupError:
                pass
            except PermissionError:
                alive.add(pid)  # exists but cannot be signalled: not confirmed dead
        if alive:
            # A killed process may linger as an unreaped zombie; it runs nothing.
            try:
                completed = subprocess.run(
                    ["ps", "-o", "pid=,stat=", "-p", ",".join(str(pid) for pid in alive)],
                    env=_probe_env(),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                rows = [line.split() for line in completed.stdout.splitlines()]
                well_formed = (
                    completed.returncode == 0
                    and all(len(row) == 2 and row[0].isdigit() for row in rows)
                    and len({row[0] for row in rows}) == len(rows)
                )
                # Only a clean, unambiguous listing may excuse a zombie.
                if well_formed:
                    for pid_text, stat in rows:
                        if stat.startswith("Z") and int(pid_text) in alive:
                            alive.discard(int(pid_text))
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
        if not alive:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _sweep_tagged_processes(tag: str) -> bool:
    """SIGKILL processes carrying the run tag; True only when none survive."""
    try:
        deadline = time.monotonic() + _SWEEP_DEADLINE_SECONDS
        while True:
            starts: dict[int, Optional[int]] = {}
            pids = _tagged_pids(tag, starts)
            if not pids:
                return True
            for pid in pids:
                # A pid freed and reused since the scan is not ours to kill.
                before = starts.get(pid)
                if before is not None and _proc_start_ticks(Path("/proc") / str(pid)) != before:
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            if time.monotonic() >= deadline:
                return not _tagged_pids(tag)
            time.sleep(0.1)
    except Exception as exc:  # noqa: BLE001
        _logger.debug("timeout sweep failed (treated as not clean): %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public descendant-sweep facade (#2260)
#
# ``agy_dispatch_boundary`` confines the dispatcher's agy child the way
# ``run_cli_worker`` confines a CLI worker. It owns no sweep internals: the
# run-tag env name, the start-tick registry and the kill logic stay here and are
# reached only through these names.
# ---------------------------------------------------------------------------

#: Environment variable that carries a run's tag into the worker and its children.
RUN_TAG_ENV = _RUN_TAG_ENV


def sweep_baseline() -> Optional[_SweepBaseline]:
    """Record the pre-start process facts; ``None`` when they cannot be read."""
    return _sweep_baseline()


def track_run(run_tag: str, pid: int) -> _DescendantTracker:
    """Register the launched worker ``pid`` for ``run_tag`` and start tracking children.

    The returned tracker has ``stop() -> set[int]`` and ``probe_failed``; pass it
    to ``sweep_run`` and always pair this call with ``release_run``.
    """
    ticks = _proc_start_ticks(Path("/proc") / str(pid))
    if ticks is not None:
        _RUN_START_TICKS[run_tag] = ticks
    return _DescendantTracker(pid)


def sweep_run(
    run_tag: str,
    tracker: Any,
    baseline: Optional[_SweepBaseline],
    roots: Iterable[str],
) -> bool:
    """Stop ``tracker`` and SIGKILL every surviving descendant of the run.

    True only when the sweep is provably clean: tracked descendants and
    processes with a cwd under ``roots`` are dead, no process still carries the
    run tag, the baseline was readable and no process-table poll failed.
    """
    tracked = tracker.stop() - (baseline.preexisting if baseline else frozenset())
    tagged_clean = _sweep_tagged_processes(run_tag)
    return bool(
        _sweep_clean(tracked, _pids_with_cwd_under(tuple(roots), baseline))
        and tagged_clean
        and baseline is not None
        and not tracker.probe_failed
    )


def release_run(run_tag: str) -> None:
    """Forget the run's start-tick entry (idempotent)."""
    _RUN_START_TICKS.pop(run_tag, None)


# ---------------------------------------------------------------------------
# Passive trajectory telemetry helpers (fail-open; MUST NOT affect execution)
# ---------------------------------------------------------------------------


def _build_action_payload(request: CliWorkerRequest) -> dict[str, Any]:
    """Construct a bounded action payload for trajectory telemetry.

    Only identifies the executable, argv, cwd, and timeout.  Task-scoped env
    key *names* are recorded as presence-only metadata sufficient for action
    identity.  Raw env values and any hash derived from those values are never
    stored; inherited ambient env is also excluded.
    """
    return {
        "executable": request.executable,
        "argv": list(request.argv),
        "cwd": request.cwd,
        "timeout_seconds": request.timeout_seconds,
        # Presence-only: key names only – no raw values, no value-derived hashes,
        # no ambient env.
        "task_env_receipt": [{"key": str(k)} for k in sorted((request.env or {}).keys())],
    }


def _seal_step(
    ctx: CliWorkerTrajectoryContext,
    request: CliWorkerRequest,
) -> Any:
    """Call seal_trajectory_step; return TrajectoryStepRef or None on any failure."""
    try:
        from nexus.research.clm_system_one.trajectory_continuity import (
            resolve_research_evidence_root,
            seal_trajectory_step,
        )

        evidence_root = resolve_research_evidence_root(ctx.repo_root)
        return seal_trajectory_step(
            evidence_root=evidence_root,
            task_id=ctx.task_id,
            trajectory_id=ctx.trajectory_id,
            attempt_id=ctx.attempt_id,
            candidate_id=ctx.candidate_id,
            step_index=ctx.step_index,
            source_revision=ctx.source_revision,
            base_source_revision=ctx.base_source_revision or "",
            working_state_manifest_sha256=ctx.working_state_manifest_sha256 or "",
            pre_action_state=ctx.pre_action_state,
            action_type="cli_worker_execute",
            action_payload=_build_action_payload(request),
        )
    except Exception as exc:  # noqa: BLE001
        _logger.debug("trajectory seal_step failed (swallowed): %s", exc)
        return None


def _bind_result(
    ctx: CliWorkerTrajectoryContext,
    step_ref: Any,
    result: CliWorkerResult,
) -> None:
    """Call bind_trajectory_step_result; swallow all failures."""
    if step_ref is None:
        return
    try:
        from nexus.research.clm_system_one.trajectory_continuity import (
            bind_trajectory_step_result,
            resolve_research_evidence_root,
        )

        evidence_root = resolve_research_evidence_root(ctx.repo_root)
        action_result: dict[str, Any] = {
            "status": result.status.value,
            "exit_code": result.exit_code,
            "stdout": result.stdout.decode("utf-8", errors="replace"),
            "stderr": result.stderr.decode("utf-8", errors="replace"),
            "wall_time_ms": result.wall_time_ms,
            "timed_out": result.timed_out,
            "process_group_killed": result.process_group_killed,
        }
        bind_trajectory_step_result(
            evidence_root=evidence_root,
            step_ref=step_ref,
            action_result=action_result,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.debug("trajectory bind_result failed (swallowed): %s", exc)


# ---------------------------------------------------------------------------
# Main execution entry point
# ---------------------------------------------------------------------------


def run_cli_worker(
    request: CliWorkerRequest,
    *,
    on_process_group: Optional[Callable[[Optional[int]], None]] = None,
) -> CliWorkerResult:
    """Run one isolated CLI invocation and return execution evidence."""

    started = time.monotonic()
    executable_sha256 = _hash_file(request.executable)
    # Verifiers must not inherit ambient lifecycle controls, provider tokens,
    # or target-root overrides.  Callers can still pass task-scoped values
    # explicitly through ``request.env``.
    environment = (
        {}
        if request.exact_env
        else {key: value for key, value in os.environ.items() if key in _INHERITED_ENV_ALLOWLIST}
    )
    # Defensive second check: the request constructor already rejects GitHub
    # credential keys, but the send path must also fail closed so a future
    # env-supplying caller can never reintroduce a broad Owner credential.
    _reject_github_credentials(request.env)
    if request.env is not None:
        environment.update({str(key): str(value) for key, value in request.env.items()})
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    run_tag = secrets.token_hex(16)
    environment[_RUN_TAG_ENV] = run_tag
    isolated_home = tempfile.mkdtemp(prefix="nexus-cli-worker-home-")
    for key, value in _isolated_github_credential_environment(isolated_home, request.env).items():
        environment[key] = value

    if is_git_executable(request.executable):
        # Global/system config is neutralised above, but the target repository's
        # own config and .gitattributes would still run repo-defined programs.
        try:
            assert_git_repo_config_safe(
                git_target_directory(request.argv, request.cwd),
                environment,
                request.executable,
            )
        except ValueError:
            shutil.rmtree(isolated_home, ignore_errors=True)
            raise

    # ------------------------------------------------------------------
    # Passive trajectory telemetry seam (pre-Popen)
    # Seal BEFORE subprocess.Popen; failures are swallowed and MUST NOT
    # affect CLI execution or the returned CliWorkerResult.
    # ------------------------------------------------------------------
    _step_ref: Any = None
    if request.trajectory_context is not None:
        try:
            _step_ref = _seal_step(request.trajectory_context, request)
        except Exception as exc:  # noqa: BLE001
            _logger.debug("trajectory seam seal failure (swallowed): %s", exc)

    command: Tuple[str, ...] = request.command
    seatbelt_sha256 = ""
    descendants_swept: Optional[bool] = None
    if request.seatbelt_profile is not None:
        seatbelt_sha256 = hashlib.sha256(request.seatbelt_profile.encode("utf-8")).hexdigest()
        if not (os.path.isfile(_SANDBOX_EXEC) and os.access(_SANDBOX_EXEC, os.X_OK)):
            shutil.rmtree(isolated_home, ignore_errors=True)
            return CliWorkerResult(
                status=CliWorkerStatus.START_FAILED,
                executable_identity=request.executable,
                executable_sha256=executable_sha256,
                argv=request.argv,
                cwd=request.cwd,
                exit_code=None,
                stdout=b"",
                stderr=b"seatbelt_unavailable",
                wall_time_ms=max(0, int((time.monotonic() - started) * 1000)),
                process_group_id=None,
                env=bounded_environment_receipt(request.env),
                seatbelt_profile_sha256=seatbelt_sha256,
            )
        profile_path = Path(isolated_home) / "worker.sb"
        profile_path.write_text(request.seatbelt_profile, encoding="utf-8")
        command = (_SANDBOX_EXEC, "-f", str(profile_path), *request.command)

    process: Optional[subprocess.Popen[bytes]] = None
    tracker: Optional[_DescendantTracker] = None
    try:
        baseline = _sweep_baseline() if request.sweep_descendants_on_exit else None
        process = subprocess.Popen(
            command,
            cwd=request.cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
        if on_process_group is not None:
            on_process_group(process.pid)
        worker_ticks = _proc_start_ticks(Path("/proc") / str(process.pid))
        if worker_ticks is not None:
            _RUN_START_TICKS[run_tag] = worker_ticks
        tracker = _DescendantTracker(process.pid) if request.sweep_descendants_on_exit else None
        try:
            stdout, stderr = process.communicate(timeout=request.timeout_seconds)
            timed_out = False
            group_killed = False
            status = CliWorkerStatus.COMPLETED
            if tracker is not None:
                tracked = tracker.stop() - (baseline.preexisting if baseline else frozenset())
                _kill_process_group(process)
                tagged_clean = _sweep_tagged_processes(run_tag)
                descendants_swept = (
                    _sweep_clean(tracked, _pids_with_cwd_under(request.sweep_roots, baseline))
                    and tagged_clean
                    and baseline is not None
                    and not tracker.probe_failed
                )
        except subprocess.TimeoutExpired as exc:
            group_killed = _kill_process_group(process)
            if tracker is not None:
                tracked = tracker.stop() - (baseline.preexisting if baseline else frozenset())
                if (
                    not _sweep_clean(tracked, _pids_with_cwd_under(request.sweep_roots, baseline))
                    or baseline is None
                    or tracker.probe_failed
                ):
                    group_killed = False
            # Descendants that called setsid() left the group; find them by the
            # per-run tag in their environment and kill them too.  A receipt may
            # only claim a clean kill when no tagged process survives.
            if not _sweep_tagged_processes(run_tag):
                group_killed = False
            try:
                stdout, stderr = process.communicate(timeout=_POST_KILL_DRAIN_SECONDS)
            except subprocess.TimeoutExpired as drain_exc:
                # A descendant escaped the process group (setsid) and still
                # holds the pipes: do not block the controller, and record the
                # kill as not clean.
                group_killed = False
                stdout = drain_exc.stdout or b""
                stderr = drain_exc.stderr or b""
                for pipe in (process.stdout, process.stderr):
                    try:
                        if pipe is not None:
                            pipe.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    process.wait(timeout=_POST_KILL_DRAIN_SECONDS)
                except subprocess.TimeoutExpired:
                    pass
            if exc.stdout:
                stdout = (exc.stdout or b"") + stdout
            if exc.stderr:
                stderr = (exc.stderr or b"") + stderr
            timed_out = True
            status = CliWorkerStatus.TIMED_OUT
        exit_code = process.returncode
        process_group_id = process.pid
    except OSError as exc:
        if tracker is not None:
            tracker.stop()
        if process is not None:
            # Failed after launch: never leave the worker or its group running.
            _kill_process_group(process)
            if request.sweep_descendants_on_exit:
                descendants_swept = False
        stdout = b""
        stderr = str(exc).encode("utf-8", errors="replace")
        exit_code = None
        process_group_id = None
        timed_out = False
        group_killed = False
        status = CliWorkerStatus.START_FAILED
    finally:
        _RUN_START_TICKS.pop(run_tag, None)
        if on_process_group is not None:
            on_process_group(None)
        shutil.rmtree(isolated_home, ignore_errors=True)

    wall_time_ms = max(0, int((time.monotonic() - started) * 1000))
    result = CliWorkerResult(
        status=status,
        executable_identity=request.executable,
        executable_sha256=executable_sha256,
        argv=request.argv,
        cwd=request.cwd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        wall_time_ms=wall_time_ms,
        process_group_id=process_group_id,
        process_group_killed=group_killed,
        timed_out=timed_out,
        # Receipt only exposes the bounded task-scoped overlay, never the
        # inherited allowlist (which may contain machine-specific paths).
        env=bounded_environment_receipt(request.env),
        telemetry={
            "wall_time_ms": wall_time_ms,
            "process_group_id": process_group_id or 0,
        },
        descendants_swept=descendants_swept,
        seatbelt_profile_sha256=seatbelt_sha256,
        env_keys_sha256=hashlib.sha256("\n".join(sorted(environment)).encode("utf-8")).hexdigest(),
    )

    # ------------------------------------------------------------------
    # Passive trajectory telemetry seam (post-execution)
    # Bind result AFTER execution; failures are swallowed and MUST NOT
    # change the returned CliWorkerResult.
    # ------------------------------------------------------------------
    if request.trajectory_context is not None:
        try:
            _bind_result(request.trajectory_context, _step_ref, result)
        except Exception as exc:  # noqa: BLE001
            _logger.debug("trajectory seam bind failure (swallowed): %s", exc)

    return result
