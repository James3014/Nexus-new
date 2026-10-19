"""Measurement-only snapshot of the worker's raw Target diff (Issue #2721).

The #2721 re-measure scores the bare arm and the Nexus P1 arm on the same
thing: the worker's raw worktree diff at the moment it stops, before Nexus
verification, Candidate capture or cleanup can change or drop it.  This module
takes that snapshot for the P1 arm.

It is enabled ONLY when ``NEXUS_MEASUREMENT_WORKTREE_DIFF=1`` is set in the
process environment at start (read once, at import, as #2742 does); the live
Gateway never sets it, so for live nothing here runs: no git command, no new
task-state key.  A worker child process inherits the start-time value, never a
value set later in the parent (``align_child_env``).

The diff follows the shared measurement rule (base attributes, no global
config), which workspace-b6 is adopting for the bare arm: a throwaway
``GIT_INDEX_FILE`` in a temporary directory, ``read-tree <base>``,
``add -A -- .``, then ``diff --cached --binary --no-color --no-ext-diff
--no-textconv <base>``, every call with ``--attr-source=<base>``.  The worktree's own
index and files are untouched.  Before any git call the Target is checked in
Python: its ``.git`` file must point at ``<Controller common dir>/worktrees/
<name>`` (Controller from the task contract), else ``gitdir_untrusted``.  git
then runs with ``GIT_DIR``/``GIT_WORK_TREE`` pinned to those trusted paths and
hardened: attributes come only from the trusted base tree
(``--attr-source=<base>``; a worker-written ``.gitattributes`` is ignored, and
filter definitions come only from the Controller config), no textconv, no
attributes file or system attributes, no fsmonitor, hooks or
transports, no other inherited ``GIT_*``, no system or global config, no
prompt, stdin closed.  One 30 s budget covers every git call; the diff streams
through a pipe, hashed as it arrives, and git is killed (by its PID) beyond
256 MiB or the deadline (``too_large`` / ``git_timeout``, partial byte count
only).  The stored text is capped at 8 MiB and flagged lossy (with the exact
bytes as base64 when within the cap) when it is not valid UTF-8.

``record_after_worker`` is called by the runtime coordination bridge right
after ``WorkerRegistry.invoke`` returns or raises (a timed-out worker returns a
receipt after its process group was killed), so the snapshot exists before the
runtime records ``WORKER_COMPLETED`` and before escalation, finalization,
verification, capture or cleanup touch the Target.  It never raises and never
changes the task outcome: any failure is recorded as
``measurement_worktree_diff_error``.  One caveat: the snapshot runs inside the
attempt's wall-time budget (nexus-runtime checks the deadline right after
``worker.invoke``), so the outcome can change only if the snapshot itself
(at most 30 s, recorded as ``measurement_worktree_diff_elapsed_ms``) exhausts
the remaining wall budget, turning it into ``WALL_TIME_BUDGET_EXHAUSTED``.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import selectors
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Optional

MEASUREMENT_WORKTREE_DIFF_ENV = "NEXUS_MEASUREMENT_WORKTREE_DIFF"
# Snapshot taken once at import (= process start); a variable set later must
# not enable anything (#2742 pattern).
MEASUREMENT_WORKTREE_DIFF_AT_START = (
    str(os.environ.get(MEASUREMENT_WORKTREE_DIFF_ENV, "") or "").strip() == "1"
)
MAX_DIFF_BYTES = 8 * 1024 * 1024
# Hard ceiling on what git may stream at all; beyond it git is killed and the
# snapshot is recorded as ``too_large`` (the stored text is capped separately).
MAX_TOTAL_DIFF_BYTES = 256 * 1024 * 1024
GIT_TIME_BUDGET_SECONDS = 30.0
_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
# Every git call also gets ``--attr-source=<base>`` (the trusted base commit):
# attributes come from the base tree, never from a worker-written
# ``.gitattributes``, so the worker cannot name a filter or textconv while we
# capture (#2761 review), and eol/binary handling matches the shared rule.
_GIT_SAFE_CONFIG = (
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "protocol.allow=never",
    "-c", "core.attributesFile=/dev/null",
    "-c", "core.splitIndex=false",
    "-c", "core.untrackedCache=false",
    "-c", "index.threads=1",
)  # fmt: skip
_READ_CHUNK = 1024 * 1024

DIFF_KEY = "measurement_worktree_diff"
SHA256_KEY = "measurement_worktree_diff_sha256"
BYTES_KEY = "measurement_worktree_diff_bytes"
TRUNCATED_KEY = "measurement_worktree_diff_truncated"
BASE_KEY = "measurement_worktree_diff_base"
LOSSY_KEY = "measurement_worktree_diff_lossy"
B64_KEY = "measurement_worktree_diff_b64"
PARTIAL_BYTES_KEY = "measurement_worktree_diff_partial_bytes"
ERROR_KEY = "measurement_worktree_diff_error"
INVOCATION_KEY = "measurement_worktree_diff_invocation"
ATTEMPT_KEY = "measurement_worktree_diff_attempt_id"
ELAPSED_KEY = "measurement_worktree_diff_elapsed_ms"
STATE_KEYS = (
    DIFF_KEY,
    SHA256_KEY,
    BYTES_KEY,
    TRUNCATED_KEY,
    BASE_KEY,
    LOSSY_KEY,
    B64_KEY,
    PARTIAL_BYTES_KEY,
    ERROR_KEY,
    INVOCATION_KEY,
    ATTEMPT_KEY,
    ELAPSED_KEY,
)


class MeasurementDiffError(RuntimeError):
    """A failed snapshot; ``str(exc)`` is the short code that is recorded."""

    def __init__(self, code: str, *, partial_bytes: Optional[int] = None) -> None:
        super().__init__(code)
        self.partial_bytes = partial_bytes


def enabled() -> bool:
    """Whether the start-time snapshot of the environment enabled the capture."""
    return MEASUREMENT_WORKTREE_DIFF_AT_START


def align_child_env(env: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Give a worker child process the start-time value, not a later one.

    With the variable unset at start and unset now this changes nothing.
    """
    if MEASUREMENT_WORKTREE_DIFF_AT_START:
        env[MEASUREMENT_WORKTREE_DIFF_ENV] = "1"
    else:
        env.pop(MEASUREMENT_WORKTREE_DIFF_ENV, None)
    return env


def _git_env(index_file: str, target: "TrustedTarget") -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_INDEX_FILE": index_file,
        # Pinned to the trusted Controller paths: git never reads the
        # worker-controlled ``.git`` file (#2761 review).
        "GIT_DIR": str(target.gitdir),
        "GIT_WORK_TREE": str(target.worktree),
        "GIT_CEILING_DIRECTORIES": str(target.worktree.parent),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ATTR_NOSYSTEM": "1",
    })
    return env


@dataclass(frozen=True)
class TrustedTarget:
    """A Target resolved against the Controller: its worktree and gitdir."""

    worktree: Path
    gitdir: Path
    common_dir: Path


def _read_gitdir_pointer(dotgit: Path) -> Optional[Path]:
    try:
        text = dotgit.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("gitdir:"):
        return None
    pointer = Path(text[len("gitdir:") :].strip())
    return (dotgit.parent / pointer).resolve()


def _common_dir(gitdir: Path) -> Path:
    try:
        text = (gitdir / "commondir").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return gitdir.resolve()
    return (gitdir / text).resolve()


def _repo_common_dir(root: Path) -> Optional[Path]:
    dotgit = root / ".git"
    if dotgit.is_dir() and not dotgit.is_symlink():
        return dotgit.resolve()
    if dotgit.is_file():
        gitdir = _read_gitdir_pointer(dotgit)
        return _common_dir(gitdir) if gitdir is not None else None
    return None


def verify_target(worktree: str, controller_root: str) -> TrustedTarget:
    """Check, in Python and before any git call, that the Target is trusted.

    The Target must be a non-symlinked directory whose ``.git`` file points
    at ``<Controller common dir>/worktrees/<name>`` (the Controller comes from
    the task contract, never from the worktree), and that registration must
    point back at this Target.  A repository-level ``info/attributes`` (the
    one attribute source ``--attr-source`` does not replace) is refused too.
    """
    if not worktree or not Path(worktree).is_dir():
        raise MeasurementDiffError("worktree_missing")
    if Path(worktree).is_symlink():
        raise MeasurementDiffError("worktree_symlink")
    resolved = Path(worktree).resolve()
    if not controller_root:
        raise MeasurementDiffError("controller_unknown")
    common = _repo_common_dir(Path(controller_root).resolve())
    if common is None or not common.is_dir():
        raise MeasurementDiffError("controller_unknown")
    dotgit = resolved / ".git"
    if dotgit.is_symlink() or not dotgit.is_file():
        raise MeasurementDiffError("gitdir_untrusted")
    gitdir = _read_gitdir_pointer(dotgit)
    if gitdir is None or gitdir.parent != common / "worktrees" or not gitdir.is_dir():
        raise MeasurementDiffError("gitdir_untrusted")
    # The registration's commondir must be the Controller's own.
    if _common_dir(gitdir) != common:
        raise MeasurementDiffError("gitdir_untrusted")
    try:
        back = Path((gitdir / "gitdir").read_text(encoding="utf-8").strip())
    except (OSError, UnicodeDecodeError) as exc:
        raise MeasurementDiffError("gitdir_untrusted") from exc
    # The registration must point back at this Target.
    if (gitdir / back).resolve() != dotgit:
        raise MeasurementDiffError("gitdir_untrusted")
    for directory in (gitdir, common):
        try:
            if (directory / "info" / "attributes").stat().st_size > 0:
                raise MeasurementDiffError("info_attributes_present")
        except FileNotFoundError:
            pass
    return TrustedTarget(worktree=resolved, gitdir=gitdir, common_dir=common)


def _run_git(
    worktree: str,
    attr_source: str,
    args: list[str],
    env: Mapping[str, str],
    deadline: float,
    step: str,
) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise MeasurementDiffError("git_timeout")
    try:
        result = subprocess.run(
            ["git", f"--attr-source={attr_source}", *_GIT_SAFE_CONFIG, *args],
            cwd=worktree,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=remaining,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MeasurementDiffError("git_timeout") from exc
    except OSError as exc:
        raise MeasurementDiffError(f"git_unavailable:{step}") from exc
    if result.returncode != 0:
        raise MeasurementDiffError(f"git_failed:{step}")


def _stream_git(
    worktree: str,
    attr_source: str,
    args: list[str],
    env: Mapping[str, str],
    deadline: float,
    *,
    max_bytes: int,
    max_total_bytes: int,
) -> tuple[bytes, str, int]:
    """Run git, hashing every byte as it streams; keep the first ``max_bytes``.

    git is killed (by its own PID) when it exceeds ``max_total_bytes`` or the
    deadline; hashing happens inside the same loop, so inside the deadline.
    """
    try:
        proc = subprocess.Popen(
            ["git", f"--attr-source={attr_source}", *_GIT_SAFE_CONFIG, *args],
            cwd=worktree,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise MeasurementDiffError("git_unavailable:diff") from exc
    assert proc.stdout is not None
    digest = hashlib.sha256()
    head = bytearray()
    total = 0
    failure: Optional[str] = None
    selector = selectors.DefaultSelector()
    try:
        selector.register(proc.stdout, selectors.EVENT_READ)
        fd = proc.stdout.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "git_timeout"
                break
            if not selector.select(timeout=remaining):
                continue
            chunk = os.read(fd, _READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_total_bytes:
                failure = "too_large"
                break
            digest.update(chunk)
            if len(head) < max_bytes:
                head.extend(chunk[: max_bytes - len(head)])
        if failure is None:
            try:
                returncode = proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                failure = "git_timeout"
            else:
                if returncode != 0:
                    raise MeasurementDiffError("git_failed:diff")
        if failure is not None:
            raise MeasurementDiffError(failure, partial_bytes=total)
    finally:
        selector.close()
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        proc.stdout.close()
    return bytes(head), digest.hexdigest(), total


def capture_worktree_diff(
    worktree: str,
    base: str,
    *,
    controller_root: str,
    max_bytes: Optional[int] = None,
    max_total_bytes: Optional[int] = None,
    time_budget_seconds: Optional[float] = None,
) -> dict[str, Any]:
    """The bare arm's ``capture_diff`` rule, hardened and bounded.

    Returns the state values (diff text capped at ``max_bytes``, sha256 and
    byte count of the full diff, truncation and lossy-decoding flags, base, and
    the exact bytes as base64 when the decoding was lossy and not truncated).
    Raises ``MeasurementDiffError`` with a short code on any failure.
    """
    # Limits are read at call time (module constants), so tests can lower them.
    max_bytes = MAX_DIFF_BYTES if max_bytes is None else max_bytes
    max_total_bytes = MAX_TOTAL_DIFF_BYTES if max_total_bytes is None else max_total_bytes
    if time_budget_seconds is None:
        time_budget_seconds = GIT_TIME_BUDGET_SECONDS
    if not base:
        raise MeasurementDiffError("base_missing")
    if not _REVISION.match(base):
        raise MeasurementDiffError("base_invalid")
    trusted = verify_target(worktree, controller_root)
    target = str(trusted.worktree)
    deadline = time.monotonic() + time_budget_seconds
    with tempfile.TemporaryDirectory(prefix="nexus-m2721-index-") as tmp:
        env = _git_env(str(Path(tmp) / "index"), trusted)
        _run_git(target, base, ["read-tree", base], env, deadline, "read_tree")
        _run_git(target, base, ["add", "-A", "--", "."], env, deadline, "add")
        head, sha256, total = _stream_git(
            target,
            base,
            [
                "diff", "--cached", "--binary", "--no-color", "--no-ext-diff",
                "--no-textconv", base,
            ],
            env,
            deadline,
            max_bytes=max_bytes,
            max_total_bytes=max_total_bytes,
        )  # fmt: skip
    truncated = total > max_bytes
    try:
        text, lossy = head.decode("utf-8"), False
    except UnicodeDecodeError:
        text, lossy = head.decode("utf-8", errors="replace"), True
    values: dict[str, Any] = {
        DIFF_KEY: text,
        SHA256_KEY: sha256,
        BYTES_KEY: total,
        TRUNCATED_KEY: truncated,
        LOSSY_KEY: lossy,
        BASE_KEY: base,
    }
    if lossy and not truncated:
        values[B64_KEY] = base64.b64encode(head).decode("ascii")
    return values


def record_after_worker(
    *,
    read_state: Callable[[str], Optional[Mapping[str, Any]]],
    mutate_state: Callable[[str, Callable[[dict[str, Any]], None]], Any],
    task_id: Any,
    attempt_id: str,
    lease: Any,
    invocation: int,
) -> None:
    """Persist the snapshot for one worker invocation; never raises.

    Every return of ``WorkerRegistry.invoke`` is a real worker run, so each
    call (re)writes the snapshot of the matching attempt, replacing every
    earlier ``measurement_worktree_diff*`` field (an earlier diff, error or
    ``persist_failed``).  A resume that does not re-invoke the worker never
    reaches this function.  ``invocation`` (execution receipts recorded before
    this worker ran) and the attempt id are kept as metadata.  Nothing is ever
    written into another attempt's state.
    """
    if not MEASUREMENT_WORKTREE_DIFF_AT_START or not task_id:
        return
    attempt = str(attempt_id or "")

    def writable(current: Mapping[str, Any]) -> bool:
        return str(current.get("attempt_id") or "") == attempt

    def write(current: dict[str, Any], values: Mapping[str, Any]) -> None:
        if not writable(current):
            return
        for key in STATE_KEYS:
            current.pop(key, None)
        current.update(values)
        current[INVOCATION_KEY] = int(invocation)
        current[ATTEMPT_KEY] = attempt

    try:
        state = read_state(str(task_id)) or {}
        if not writable(state):
            return
        base = str(
            getattr(lease, "initial_head", "") or state.get("target_initial_revision") or ""
        ).strip()
        worktree = str(getattr(lease, "target_worktree", "") or "")
        contract = state.get("contract")
        controller_root = str(
            (contract.get("controller_repo_root") if isinstance(contract, Mapping) else None)
            or state.get("controller_worktree")
            or ""
        )
        started = time.monotonic()
        try:
            values: dict[str, Any] = capture_worktree_diff(
                worktree, base, controller_root=controller_root
            )
        except MeasurementDiffError as exc:
            values = {ERROR_KEY: str(exc), BASE_KEY: base}
            if exc.partial_bytes is not None:
                values[PARTIAL_BYTES_KEY] = exc.partial_bytes
        except Exception as exc:  # noqa: BLE001 - measurement never changes the outcome
            values = {ERROR_KEY: f"unexpected:{type(exc).__name__}", BASE_KEY: base}
        values[ELAPSED_KEY] = max(0, int((time.monotonic() - started) * 1000))
        mutate_state(str(task_id), lambda current: write(current, values))
    except Exception:  # noqa: BLE001 - measurement never changes the outcome
        try:
            mutate_state(
                str(task_id), lambda current: write(current, {ERROR_KEY: "persist_failed"})
            )
        except Exception:  # noqa: BLE001
            pass
