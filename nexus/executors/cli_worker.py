"""Model-neutral, no-shell CLI worker used by governed self-hosted execution."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Tuple

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
_INHERITED_ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "PYTHONPATH",
        "TMPDIR",
        "VIRTUAL_ENV",
    }
)


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
_SWEEP_DEADLINE_SECONDS = 2.0


def _tagged_pids(tag: str) -> set[int]:
    """PIDs (other than ours) whose environment carries ``tag``."""
    own = os.getpid()
    needle = f"{_RUN_TAG_ENV}={tag}"
    found: set[int] = set()
    proc = Path("/proc")
    if proc.is_dir() and (proc / "self" / "environ").exists():
        needle_bytes = needle.encode()
        for entry in proc.iterdir():
            if not entry.name.isdigit() or int(entry.name) == own:
                continue
            try:
                if needle_bytes in (entry / "environ").read_bytes():
                    found.add(int(entry.name))
            except OSError:
                continue
        return found
    out = subprocess.run(
        ["ps", "-axww", "-E", "-o", "pid=,command="],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) != own and needle in parts[1]:
            found.add(int(parts[0]))
    return found


def _sweep_tagged_processes(tag: str) -> bool:
    """SIGKILL processes carrying the run tag; True only when none survive."""
    try:
        deadline = time.monotonic() + _SWEEP_DEADLINE_SECONDS
        while True:
            pids = _tagged_pids(tag)
            if not pids:
                return True
            for pid in pids:
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
    environment = {
        key: value for key, value in os.environ.items() if key in _INHERITED_ENV_ALLOWLIST
    }
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
