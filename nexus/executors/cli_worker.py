"""Model-neutral, no-shell CLI worker used by governed self-hosted execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time
from typing import Callable, Mapping, Optional, Tuple


class CliWorkerStatus(str, Enum):
    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"
    START_FAILED = "START_FAILED"


_FORBIDDEN_SUBCOMMANDS = {
    ("git", "commit"),
    ("git", "merge"),
    ("git", "push"),
    ("git", "rebase"),
}


def _resolve_executable(executable: str) -> str:
    if not isinstance(executable, str) or not executable.strip():
        raise ValueError("executable must be non-empty")
    resolved = shutil.which(executable)
    if resolved is None:
        raise ValueError(f"executable not found: {executable}")
    return str(Path(resolved).resolve())


def _validate_worker_argv(argv: Tuple[str, ...]) -> None:
    if not argv:
        raise ValueError("argv must be non-empty")
    normalized = tuple(str(item).strip().lower() for item in argv)
    for command, subcommand in _FORBIDDEN_SUBCOMMANDS:
        if command in normalized:
            index = normalized.index(command)
            if normalized[index + 1 : index + 2] == (subcommand,):
                raise ValueError(f"worker command cannot invoke git {subcommand}")


def _hash_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class CliWorkerRequest:
    executable: str
    argv: Tuple[str, ...]
    cwd: str
    timeout_seconds: float = 60.0
    env: Optional[Mapping[str, str]] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable", _resolve_executable(self.executable))
        object.__setattr__(self, "argv", tuple(str(item) for item in self.argv))
        _validate_worker_argv((Path(self.executable).name, *self.argv))
        target_cwd = Path(self.cwd).expanduser().resolve(strict=False)
        if not target_cwd.is_dir():
            raise ValueError("cwd must be an existing directory")
        object.__setattr__(self, "cwd", str(target_cwd))
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

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
    telemetry: dict[str, int] = field(default_factory=dict)

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


def run_cli_worker(
    request: CliWorkerRequest,
    *,
    on_process_group: Optional[Callable[[Optional[int]], None]] = None,
) -> CliWorkerResult:
    """Run one isolated CLI invocation and return execution evidence."""

    started = time.monotonic()
    executable_sha256 = _hash_file(request.executable)
    environment = None
    if request.env is not None:
        environment = os.environ.copy()
        environment.update({str(key): str(value) for key, value in request.env.items()})
    process: Optional[subprocess.Popen[bytes]] = None
    try:
        process = subprocess.Popen(
            request.command,
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
        try:
            stdout, stderr = process.communicate(timeout=request.timeout_seconds)
            timed_out = False
            group_killed = False
            status = CliWorkerStatus.COMPLETED
        except subprocess.TimeoutExpired as exc:
            group_killed = _kill_process_group(process)
            stdout, stderr = process.communicate()
            if exc.stdout:
                stdout = (exc.stdout or b"") + stdout
            if exc.stderr:
                stderr = (exc.stderr or b"") + stderr
            timed_out = True
            status = CliWorkerStatus.TIMED_OUT
        exit_code = process.returncode
        process_group_id = process.pid
    except OSError as exc:
        stdout = b""
        stderr = str(exc).encode("utf-8", errors="replace")
        exit_code = None
        process_group_id = None
        timed_out = False
        group_killed = False
        status = CliWorkerStatus.START_FAILED
    finally:
        if on_process_group is not None:
            on_process_group(None)
    wall_time_ms = max(0, int((time.monotonic() - started) * 1000))
    return CliWorkerResult(
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
        telemetry={
            "wall_time_ms": wall_time_ms,
            "process_group_id": process_group_id or 0,
        },
    )
