"""Run the dispatcher's agy child as a separate macOS account (Cairnwork #19 Phase B, #2884).

``nexus-agy-dispatch --run-as-user _cairnwork_worker`` keeps every account
decision (selection, lease, rotation, quarantine) in the dispatcher, which runs
as the Owner.  Only the agy process itself runs as the worker account, which
cannot enter the Owner's home (0750), the account pool or Cairnwork's tree.
The one-time sudo setup is Cairnwork PR #121 (``scripts/setup_worker_user.sh``):

* worker user ``_cairnwork_worker``; run group ``_cairnwork_wrun`` (Owner + worker);
* ``/Users/Shared/cairnwork-worker/worker-runs``: Owner, group ``_cairnwork_wrun``, 2710;
* ``/Users/Shared/cairnwork-worker/bin``: Owner, 0755, holding ``agy-worker-exec``
  (``scripts/ops/agy-worker-exec``) and the ``agy`` copy (``install_agy_worker_exec.sh``);
* sudoers: ``james ALL=(_cairnwork_worker) NOPASSWD: <bin>/agy-worker-exec``.

Per attempt the dispatcher (as the Owner):

1. creates ``worker-runs/<run_tag>`` (128-bit random, 2770; the group is inherited
   from worker-runs) holding ``work`` (a copy of the target without ``.git``,
   plus a fresh one-commit git snapshot so source-effect observation keeps
   working), ``home`` (only the leased account's agy session files, as in the
   normal path), ``tmp`` and the Seatbelt profile;
2. launches ``sudo -n -u <worker> <bin>/agy-worker-exec <run_root> <workdir>
   <profile> -- <bin>/agy <agy args>``; the wrapper validates its arguments,
   sets ``umask 007`` and execs ``sandbox-exec`` with a fixed environment;
3. after exit, sweeps the run's worker processes through ``agy-worker-exec
   --sweep`` (the Owner cannot signal another uid; the same sudoers rule allows
   this mode, so no sudoers change is needed), copies changed files back into
   the target through the group permission, and deletes the run directory.

The leased account directory is only read (its two agy session files are
copied, exactly as the normal path does); nothing in it is chmod-ed or
chown-ed.  Refreshed agy auth is not written back, matching the normal path,
which also discards the disposable HOME.

The Seatbelt profile is the normal #1912/#2202 profile (including the #2863
Launch Services and #2470 run-HOME denies) plus a cross-run deny: no read or
write anywhere under worker-runs except this run's own subpath, and no signal
to any process outside this run's sandbox instance.  All runs share one uid, so
only Seatbelt separates them.  The workdir, run HOME, TMPDIR and profile are
pinned against rename/replace inside the otherwise writable run root.

Trust and limits (#2885 review r1):

* The Owner-side caller is trusted for the profile content; the wrapper only
  checks where the profile lives.
* ``--sweep`` finds untracked worker processes by run tag through ``ps -E``;
  macOS hides the environment of Apple system binaries (``/bin/sleep``,
  ``/bin/sh`` ...), so a tagged system binary is only found by the tracker or
  by its cwd.  Copy-back does not trust the run dir, so this is not a safety
  hole.
* ``sudo`` closes the inherited lease-lock descriptor (#2888), so only the dispatcher
  holds the account flock.  Before launch it records the run in its lease receipt
  (``AccountLeaseClaim.mark_worker_run``) and it never releases the claim after an
  unclean worker sweep.  If the dispatcher dies, the pool removes the receipt only
  after ``reap_orphaned_worker_run`` proves the run is gone.
* A clean sweep does not prove that no worker process survived (one that
  clears its environment, leaves the run directory and was never seen by the
  tracker is not found).  Copy-back therefore re-opens the workdir with
  ``O_NOFOLLOW`` and requires the same (device, inode) the dispatcher created,
  walks it only through directory fds, refuses symlinks, special files and
  hard-linked files, stages every file and re-checks its hash against the
  plan before anything in the target changes, refuses when the target itself
  changed since the copy (three-way), and caps entry count and total size.
"""

from __future__ import annotations

import grp
import hashlib
import json
import os
import pwd
import secrets
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from nexus.executors import cli_worker
from nexus.executors.agy_dispatch_boundary import (
    AGY_WRITE_BOUNDARY_UNAVAILABLE,
    KEEP_RUN_ROOT_ENV,
    WORKER_RUNS_DIR,
    AgyDispatchBoundary,
    AgyWriteBoundaryError,
    _prepare_run_home_keychain,
    boundary_available,
)
from nexus.executors.agy_write_admission import (
    AGY_RUN_HOME_SETTINGS,
    TARGET_AGY_CUSTOMIZATION_PATHS,
    CredentialPathOverlapError,
    _sbpl_path,
    agy_child_env,
    build_seatbelt_profile,
    materialize_run_home,
    worker_home,
)

WORKER_USER = "_cairnwork_worker"
WORKER_RUN_GROUP = "_cairnwork_wrun"
# One definition of the worker-runs path, owned by the boundary module so the
# default (Owner-uid) profile can deny it without importing this module (#2888).
WORKER_RUNS = WORKER_RUNS_DIR
WORKER_ROOT = WORKER_RUNS.parent
WORKER_BIN = WORKER_ROOT / "bin"
WORKER_WRAPPER = WORKER_BIN / "agy-worker-exec"
WORKER_AGY = WORKER_BIN / "agy"
SUDO_PATH = "/usr/bin/sudo"
SWEEP_FLAG = "--sweep"
WORKDIR_NAME = "work"
PROFILE_NAME = "agy-dispatch.sb"
WRAPPER_STARTED_MARKER = ".worker-exec-started"
WORKER_RUNS_MODE = 0o2710
RUN_DIR_MODE = 0o2770
SWEEP_TIMEOUT_SECONDS = 30.0
# The sudo process itself gets only this; the wrapper discards it and builds its own.
LAUNCH_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"}

AGY_WORKER_ACCOUNT_REFUSED = "AGY_WORKER_ACCOUNT_REFUSED"
AGY_WORKER_LAUNCH_FAILED = "AGY_WORKER_LAUNCH_FAILED"
AGY_WORKER_COPY_BACK_FAILED = "AGY_WORKER_COPY_BACK_FAILED"  # target partly written
AGY_WORKER_COPY_BACK_REFUSED = "AGY_WORKER_COPY_BACK_REFUSED"  # nothing applied

# Receipt lines on stderr (same prefix as the dispatcher's status line), written
# only for a boundary the dispatcher gave a ``receipt_context``: one
# WORKER_LAUNCH, WORKER_SWEEP and WORKER_CLEANUP per attempt, owner-side data only.
RECEIPT_PREFIX = "NEXUS_AGY_DISPATCH "

# The wrapper this module speaks to: this reference must exist and match the installed copy.
REPO_WRAPPER = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "agy-worker-exec"


def _refuse(reason: str) -> AgyWriteBoundaryError:
    return AgyWriteBoundaryError(
        f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:{AGY_WORKER_ACCOUNT_REFUSED}:{reason}"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cross_run_profile(
    base_profile: str,
    *,
    runs_dir: Path,
    run_root: Path,
    pinned_entries: Iterable[Path] = (),
) -> str:
    """Add the cross-run rules to the normal profile.

    The read/write deny on ``runs_dir`` and the read re-allow of ``run_root``
    go right after ``(allow default)``: the normal profile's later
    ``(deny file-write*)``/``(allow file-write* run_root ...)`` lines then
    re-open writes only inside this run, and its write denies inside the run
    (``.git``, the run-HOME settings) still come last and win.  Signals are
    limited to this sandbox instance (separate ``sandbox-exec`` runs never
    share one, probed on macOS 27).

    ``pinned_entries`` (the workdir, the run HOME, TMPDIR, the profile) get a
    final ``literal`` write deny: the run root is writable, so without it the
    worker could rename one of them away and plant a symlink or a fresh
    directory under the name the dispatcher later reads back.  Creating and
    editing files inside them stays allowed.
    """
    head = "(version 1)\n(allow default)\n"
    if not base_profile.startswith(head):
        raise ValueError("unexpected base profile shape")
    runs, root = _sbpl_path(runs_dir), _sbpl_path(run_root)
    cross_run = (
        ";; Cairnwork #19 Phase B: other runs share this uid; only this run's subpath is visible\n"
        f'(deny file-read* file-write* (subpath "{runs}"))\n'
        f'(allow file-read* (subpath "{root}"))\n'
        # stat of worker-runs itself (not a listing): cd/mkdir -p/git resolve
        # absolute paths through it; without this they fail with ENOTDIR/EPERM.
        f'(allow file-read-metadata (literal "{runs}"))\n'
    )
    signals = "(deny signal)\n(allow signal (target same-sandbox))\n"
    pinned = [f'  (literal "{_sbpl_path(path)}")' for path in pinned_entries]
    tail = "\n".join(["(deny file-write*", *pinned, ")"]) + "\n" if pinned else ""
    return head + cross_run + base_profile[len(head) :] + signals + tail


def worker_argv(
    agy_argv: Iterable[str],
    *,
    run_root: Path,
    workdir: Path,
    profile_path: Path,
    user: str = WORKER_USER,
    wrapper: Path = WORKER_WRAPPER,
    agy: Path = WORKER_AGY,
) -> list[str]:
    """``sudo -n -u <user> <wrapper> <run_root> <workdir> <profile> -- <agy> <args>``.

    ``agy_argv[0]`` (the Owner's agy) is replaced by the worker-readable copy.
    """
    args = list(agy_argv)
    if not args:
        raise ValueError("empty agy argv")
    return [
        SUDO_PATH,
        "-n",
        "-u",
        user,
        str(wrapper),
        str(run_root),
        str(workdir),
        str(profile_path),
        "--",
        str(agy),
        *args[1:],
    ]


def sweep_argv(
    run_root: Path,
    pid_tokens: Iterable[str],
    *,
    user: str = WORKER_USER,
    wrapper: Path = WORKER_WRAPPER,
) -> list[str]:
    """``sudo -n -u <user> <wrapper> --sweep <run_root> <pid>:<start>...``.

    Each token is ``pid:<ps lstart with "_" for blanks>``; the wrapper kills a
    listed pid only while its start time still matches, so a pid reused by
    another run's process after the tracker saw it is never killed.
    """
    return [
        SUDO_PATH,
        "-n",
        "-u",
        user,
        str(wrapper),
        SWEEP_FLAG,
        str(run_root),
        *sorted(set(pid_tokens), key=lambda token: int(token.split(":", 1)[0])),
    ]


def sweep_run_root(
    run_root: Path,
    pid_tokens: Iterable[str] = (),
    *,
    user: str = WORKER_USER,
    wrapper: Path = WORKER_WRAPPER,
    run_command: Optional[Callable[..., Any]] = None,
) -> str:
    """Sweep a validated worker run through the wrapper with a fixed launch environment."""
    return sweep_run_root_report(
        run_root, pid_tokens, user=user, wrapper=wrapper, run_command=run_command
    )[0]


def sweep_run_root_report(
    run_root: Path,
    pid_tokens: Iterable[str] = (),
    *,
    user: str = WORKER_USER,
    wrapper: Path = WORKER_WRAPPER,
    run_command: Optional[Callable[..., Any]] = None,
) -> tuple[str, str]:
    """``sweep_run_root``'s verdict and the wrapper's last stdout line ("" if none).

    The line tells an explicit ``AGY_WORKER_SWEEP unclean <pids>`` report apart
    from a sweep that sudo or the wrapper refused (also verdict ``UNCLEAN``).
    """
    try:
        completed = (run_command or subprocess.run)(
            sweep_argv(run_root, pid_tokens, user=user, wrapper=wrapper),
            cwd="/",
            env=dict(LAUNCH_ENV),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=SWEEP_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "SWEEP_ERROR", ""
    lines = (completed.stdout or "").strip().splitlines()
    last = lines[-1] if lines else ""
    if completed.returncode == 0 and last == "AGY_WORKER_SWEEP clean":
        return "CLEAN", last
    return "UNCLEAN", last


_PS_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}

PS_PATH = "/bin/ps"
PS_TIMEOUT_SECONDS = 10.0
_RUN_TAG_DIGITS = frozenset("0123456789abcdef")


def _worker_user_has_no_process(user: str, run_command: Callable[..., Any]) -> bool:
    """True only when ``ps`` positively reports that ``user`` owns no process.

    Observed on macOS 27: ``ps -U <user> -o pid=`` exits 0 and prints one pid per
    line while the user owns a process; when the user exists and owns none it
    exits 1 with empty stdout and empty stderr; for an unknown user it also exits
    1 with empty stdout but names the user on stderr.  Only the first no-match
    shape counts, so a missing user, a ``ps`` failure or an unexpected exit code
    never reads as "nothing runs".
    """
    try:
        completed = run_command(
            [PS_PATH, "-U", user, "-o", "pid="],
            cwd="/",
            env=dict(_PS_ENV),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    pid_lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return completed.returncode == 1 and not pid_lines and not (completed.stderr or "").strip()


def _valid_receipt_run_root(receipt: Mapping[str, Any]) -> Optional[tuple[Path, list[int]]]:
    """Validate the worker fields a lease receipt carries (same checks as the journal path)."""
    if receipt.get("worker_run_as_user") != WORKER_USER:
        return None
    raw_root = receipt.get("worker_run_root")
    if not isinstance(raw_root, str) or not raw_root or "\x00" in raw_root:
        return None
    root = Path(raw_root)
    if (
        ".." in root.parts
        or str(root.resolve()) != raw_root
        or root.parent != WORKER_RUNS.resolve()
        or len(root.name) != 32
        or not set(root.name) <= _RUN_TAG_DIGITS
    ):
        return None
    root_id = receipt.get("worker_run_root_id")
    if (
        not isinstance(root_id, list)
        or len(root_id) != 2
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in root_id)
    ):
        return None
    return root, list(root_id)


def reap_orphaned_worker_run(
    receipt: Mapping[str, Any],
    *,
    run_command: Callable[..., Any] = subprocess.run,
) -> bool:
    """True only when the worker run named by an orphaned lease receipt is proven gone (#2888).

    A ``--run-as-user`` agy runs through ``sudo``, which closes the inherited
    lease lock, so a free lock and a dead dispatcher PID prove nothing about it.
    The account pool keeps such a receipt unless this returns True; it never
    raises (any error is "not proven").

    * Run root still there: it must be the directory the dispatcher created
      (a real directory we own with the recorded device and inode); the worker
      sweep must report CLEAN; then the run root is removed.
    * Run root gone: that proves nothing (a surviving worker keeps an unlinked
      cwd, and the wrapper refuses a missing root), so only "the worker account
      owns no process at all" counts.  That is stricter than needed when other
      worker runs are active, which only delays reclaiming the account.
    """
    try:
        validated = _valid_receipt_run_root(receipt)
        if validated is None:
            return False
        root, root_id = validated
        if not os.path.lexists(root):
            return _worker_user_has_no_process(WORKER_USER, run_command)
        info = os.lstat(root)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or [info.st_dev, info.st_ino] != root_id
        ):
            return False
        if sweep_run_root(root, run_command=run_command) != "CLEAN":
            return False
        shutil.rmtree(root, ignore_errors=True)
        return not os.path.lexists(root)
    except Exception:
        return False


def pid_start_tokens(pids: Iterable[int], *, since: Optional[float]) -> list[str]:
    """``pid:<lstart>`` for each live pid started at/after ``since`` (1 s margin).

    A pid ps does not report has exited and is dropped; ``since=None`` keeps
    every reported pid.
    """
    wanted = sorted({int(p) for p in pids if int(p) > 1})
    lines: list[str] = []
    # One pid per call: ps rejects the whole list when one pid is out of range.
    for pid in wanted:
        try:
            completed = subprocess.run(
                ["ps", "-o", "pid=,lstart=", "-p", str(pid)],
                env=_PS_ENV,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        lines += completed.stdout.splitlines()
    tokens: list[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) != 6 or not parts[0].isdigit() or int(parts[0]) not in wanted:
            continue
        try:
            started = time.mktime(time.strptime(" ".join(parts[1:]), "%a %b %d %H:%M:%S %Y"))
        except ValueError:
            continue
        if since is None or started >= since - 1.0:
            tokens.append(f"{parts[0]}:{'_'.join(parts[1:])}")
    return tokens


def _check_runs_dir(runs_dir: Path, group_gid: int) -> Path:
    if runs_dir.is_symlink() or not runs_dir.is_dir():
        raise _refuse("worker_runs_missing")
    if os.path.realpath(runs_dir) != str(runs_dir):
        raise _refuse("worker_runs_not_canonical")
    info = runs_dir.stat()
    if info.st_uid != os.getuid():
        raise _refuse("worker_runs_not_owner_owned")
    if info.st_gid != group_gid:
        raise _refuse("worker_runs_wrong_group")
    if stat.S_IMODE(info.st_mode) != WORKER_RUNS_MODE:
        raise _refuse("worker_runs_wrong_mode")
    return runs_dir


def _check_owner_executable(path: Path, reason: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise _refuse(f"{reason}_missing")
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o755:
        raise _refuse(f"{reason}_not_owner_0755")


# ---------------------------------------------------------------------------
# copy-in / copy-back
# ---------------------------------------------------------------------------

_SKIPPED_TOP_LEVEL = frozenset(TARGET_AGY_CUSTOMIZATION_PATHS)
# Git metadata never crosses, at any depth (a nested repo's hooks or config
# written back into the target would run later as the Owner).
_SKIPPED_ANYWHERE = frozenset({".git"})
MAX_COPY_BACK_ENTRIES = 50_000
MAX_COPY_BACK_BYTES = 2 << 30
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_STAGING_PREFIX = ".agy-worker-staging-"


class CopyBackRefused(Exception):
    """The worker copy cannot be trusted for copy-back; nothing was applied."""


class CopyBackPartial(Exception):
    """Copy-back stopped after it had already changed the target."""


def _hash_fd(fd: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := os.read(fd, 1 << 20):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _same_inode(fd: int, info: os.stat_result) -> bool:
    now = os.fstat(fd)
    return (now.st_dev, now.st_ino) == (info.st_dev, info.st_ino)


def _walk_fd(root_fd: int, *, strict: bool) -> dict[str, tuple]:
    """``relpath -> ("dir",) | ("file", sha256, exec) | ("symlink", target) | ("other",)``.

    Walks through directory file descriptors opened with ``O_NOFOLLOW``, so a
    directory or file swapped for a symlink during the walk fails instead of
    redirecting it.  ``.git`` (any depth) and the top-level agy customization
    entries are skipped.  ``strict`` (the worker copy) also refuses hard-linked
    files and caps the entry count and total size.
    """
    entries: dict[str, tuple] = {}
    total = 0

    def visit(dir_fd: int, prefix: str) -> None:
        nonlocal total
        with os.scandir(dir_fd) as listing:
            names = sorted(entry.name for entry in listing)
        for name in names:
            if name in _SKIPPED_ANYWHERE or (not prefix and name in _SKIPPED_TOP_LEVEL):
                continue
            rel = prefix + name
            info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                entries[rel] = ("symlink", os.readlink(name, dir_fd=dir_fd))
            elif stat.S_ISDIR(info.st_mode):
                entries[rel] = ("dir",)
                sub = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
                try:
                    if not _same_inode(sub, info):
                        raise CopyBackRefused(f"entry_replaced:{rel}")
                    visit(sub, rel + "/")
                finally:
                    os.close(sub)
            elif stat.S_ISREG(info.st_mode):
                fd = os.open(name, _FILE_FLAGS, dir_fd=dir_fd)
                try:
                    opened = os.fstat(fd)
                    if not stat.S_ISREG(opened.st_mode) or not _same_inode(fd, info):
                        raise CopyBackRefused(f"entry_replaced:{rel}")
                    if strict and opened.st_nlink != 1:
                        raise CopyBackRefused(f"hard_link:{rel}")
                    digest, size = _hash_fd(fd)
                    total += size
                    entries[rel] = ("file", digest, bool(opened.st_mode & 0o100))
                finally:
                    os.close(fd)
            else:
                entries[rel] = ("other",)
            if strict and (len(entries) > MAX_COPY_BACK_ENTRIES or total > MAX_COPY_BACK_BYTES):
                raise CopyBackRefused("copy_back_too_large")

    visit(root_fd, "")
    return entries


def _walk_tree(root: Path, *, strict: bool = False) -> dict[str, tuple]:
    fd = os.open(root, _DIR_FLAGS)
    try:
        return _walk_fd(fd, strict=strict)
    finally:
        os.close(fd)


def _check_copy_caps(manifest: Mapping[str, tuple], workdir: Path) -> None:
    """Refuse a source or workdir manifest that already exceeds the copy caps."""
    if len(manifest) > MAX_COPY_BACK_ENTRIES:
        raise _refuse("target_too_large")
    total = sum(
        os.lstat(workdir / rel).st_size for rel, entry in manifest.items() if entry[0] == "file"
    )
    if total > MAX_COPY_BACK_BYTES:
        raise _refuse("target_too_large")


def _copy_in(source: Path, workdir: Path) -> dict[str, tuple]:
    """Copy ``source`` (without .git / customizations / special files) into ``workdir``.

    ``source`` is the Owner's own target; the manifest is the baseline the
    copy-back compares both the worker copy and the target against.
    """
    manifest = _walk_tree(source)
    _check_copy_caps(manifest, source)
    workdir.mkdir()
    copied = 0
    source_fd = os.open(source, _DIR_FLAGS)
    try:
        for rel, entry in sorted(manifest.items()):
            dst = workdir / rel
            kind = entry[0]
            if kind == "dir":
                dst.mkdir()
            elif kind == "symlink":
                os.symlink(entry[1], dst)
            elif kind == "file":
                # Every ancestor and the file itself are opened with O_NOFOLLOW
                # relative to the verified source fd, so an entry swapped for a
                # symlink after the walk is refused instead of followed.
                try:
                    src = _open_source(source_fd, rel)
                except OSError as exc:
                    raise _refuse("target_changed_during_copy") from exc
                try:
                    if not stat.S_ISREG(os.fstat(src).st_mode):
                        raise _refuse("target_changed_during_copy")
                    digest = hashlib.sha256()
                    out = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o666)
                    try:
                        # Read at most one byte beyond the remaining allowance to
                        # detect growth since the manifest without writing past it.
                        while chunk := os.read(src, min(1 << 20, MAX_COPY_BACK_BYTES - copied + 1)):
                            if copied + len(chunk) > MAX_COPY_BACK_BYTES:
                                raise _refuse("target_too_large")
                            digest.update(chunk)
                            view = memoryview(chunk)
                            while view:
                                view = view[os.write(out, view) :]
                            copied += len(chunk)
                    finally:
                        os.close(out)
                    if digest.hexdigest() != entry[1]:
                        raise _refuse("target_changed_during_copy")
                finally:
                    os.close(src)
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    finally:
        os.close(source_fd)
    return {rel: entry for rel, entry in manifest.items() if entry[0] != "other"}


_SNAPSHOT_GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_AUTHOR_NAME": "nexus-agy-dispatch",
    "GIT_AUTHOR_EMAIL": "nexus-agy-dispatch@localhost",
    "GIT_COMMITTER_NAME": "nexus-agy-dispatch",
    "GIT_COMMITTER_EMAIL": "nexus-agy-dispatch@localhost",
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
}


def _git_snapshot(workdir: Path) -> None:
    """A fresh one-commit repository: no history or refs of the target reach the worker."""
    for args in (
        ("init", "-q"),
        ("add", "-A"),
        ("commit", "-q", "--no-verify", "--allow-empty", "-m", "worker snapshot"),
    ):
        completed = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
            cwd=workdir,
            env=_SNAPSHOT_GIT_ENV,
            capture_output=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            raise _refuse("workdir_snapshot_failed")


def _target_entry(path: Path) -> Optional[tuple]:
    """The target's current entry in manifest form (``None`` when absent)."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return ("symlink", os.readlink(path))
    if stat.S_ISDIR(info.st_mode):
        return ("dir",)
    if stat.S_ISREG(info.st_mode):
        fd = os.open(path, _FILE_FLAGS)
        try:
            return ("file", _hash_fd(fd)[0], bool(os.fstat(fd).st_mode & 0o100))
        finally:
            os.close(fd)
    return ("other",)


def _plan(
    manifest: Mapping[str, tuple], current: Mapping[str, tuple], target_real: Path
) -> list[tuple[str, str, Optional[str]]]:
    """``[(op, relpath, sha256)]`` to bring the target to ``current``; raises on refusal.

    Three-way: every path the worker changed must still be in its baseline
    state in the target (another writer's change is never overwritten).
    """
    ops: list[tuple[str, str, Optional[str]]] = []
    for rel in sorted(current):
        entry, before = current[rel], manifest.get(rel)
        kind = entry[0]
        if kind == "other":
            raise CopyBackRefused(f"special_file:{rel}")
        if kind == "symlink":
            if before != entry:
                raise CopyBackRefused(f"symlink_created:{rel}")
            continue
        if before is not None and before[0] != kind:
            raise CopyBackRefused(f"type_changed:{rel}")
        if kind == "dir" and before is None:
            ops.append(("mkdir", rel, None))
        elif kind == "file" and before != entry:
            ops.append(("write", rel, entry[1]))
    for rel in sorted(set(manifest) - set(current), reverse=True):
        ops.append(("delete", rel, None))
    for op, rel, _sha in ops:
        destination = target_real / rel
        # ``rel`` has no ``..``; a symlink on the way would redirect the write.
        parent = os.path.dirname(destination)
        if os.path.realpath(parent) != parent:
            raise CopyBackRefused(f"destination_through_symlink:{rel}")
        if _target_entry(destination) != (None if op == "mkdir" else manifest.get(rel)):
            raise CopyBackRefused(f"target_changed:{rel}")
    return ops


def _open_source(work_fd: int, rel: str) -> int:
    """Open ``rel`` under the verified workdir fd, never following a symlink."""
    parts = rel.split("/")
    dir_fd = work_fd
    opened: list[int] = []
    try:
        for part in parts[:-1]:
            dir_fd = os.open(part, _DIR_FLAGS, dir_fd=dir_fd)
            opened.append(dir_fd)
        return os.open(parts[-1], _FILE_FLAGS, dir_fd=dir_fd)
    finally:
        for fd in opened:
            os.close(fd)


OPERATION_MARKER = ".operation-id"


def write_operation_marker(run_root: Path, operation_id: str) -> None:
    """Bind ``run_root`` to one journal operation (written by the Owner, never the worker)."""
    root_fd = os.open(run_root, _DIR_FLAGS)
    try:
        fd = os.open(
            OPERATION_MARKER,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o440,
            dir_fd=root_fd,
        )
        try:
            os.write(fd, operation_id.encode("utf-8"))
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)


def operation_marker_matches(run_root: Path, operation_id: str) -> bool:
    """True only when ``run_root`` holds an Owner-written marker naming ``operation_id``."""
    try:
        root_fd = os.open(run_root, _DIR_FLAGS)
    except OSError:
        return False
    try:
        fd = os.open(OPERATION_MARKER, _FILE_FLAGS, dir_fd=root_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 256:
                return False
            return os.read(fd, 257).decode("utf-8", "replace") == operation_id
        finally:
            os.close(fd)
    except OSError:
        return False
    finally:
        os.close(root_fd)


def _stage(work_fd: int, rel: str, sha256: str, staging: Path, index: int) -> Path:
    """Copy one worker file into ``staging``; refuse unless it is the planned content."""
    staged = staging / str(index)
    src = _open_source(work_fd, rel)
    try:
        info = os.fstat(src)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise CopyBackRefused(f"entry_replaced:{rel}")
        digest = hashlib.sha256()
        dst = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            while chunk := os.read(src, 1 << 20):
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    view = view[os.write(dst, view) :]
        finally:
            os.close(dst)
    finally:
        os.close(src)
    if digest.hexdigest() != sha256:
        raise CopyBackRefused(f"content_changed_after_plan:{rel}")
    return staged


def copy_back(
    manifest: Mapping[str, tuple],
    run_root: Path,
    workdir_name: str,
    workdir_identity: tuple[int, int],
    target: Path,
) -> None:
    """Apply the worker's changes to ``target``, all or nothing up to the final renames.

    The workdir is re-opened by name under the run root with ``O_NOFOLLOW`` and
    must be the same directory (device, inode) the dispatcher created; every
    read goes through that verified fd.  Files are staged (hash re-checked
    against the plan) before anything in the target changes.  Raises
    ``CopyBackRefused`` (nothing applied) or ``OSError``.
    """
    target_real = Path(os.path.realpath(target))
    try:
        root_fd = os.open(run_root, _DIR_FLAGS)
    except OSError as exc:
        raise CopyBackRefused("run_root_unreadable") from exc
    try:
        try:
            work_fd = os.open(workdir_name, _DIR_FLAGS, dir_fd=root_fd)
        except OSError as exc:
            raise CopyBackRefused("workdir_replaced") from exc
    finally:
        os.close(root_fd)
    staging: Optional[Path] = None
    try:
        info = os.fstat(work_fd)
        if (info.st_dev, info.st_ino) != tuple(workdir_identity):
            raise CopyBackRefused("workdir_replaced")
        try:
            current = _walk_fd(work_fd, strict=True)
        except OSError as exc:
            raise CopyBackRefused(f"workdir_walk_failed:{type(exc).__name__}") from exc
        ops = _plan(manifest, current, target_real)
        if not ops:
            return
        candidate = target_real / f"{_STAGING_PREFIX}{secrets.token_hex(8)}"
        try:
            candidate.mkdir(mode=0o700)
        except OSError as exc:
            raise CopyBackRefused(f"staging_unavailable:{type(exc).__name__}") from exc
        staging = candidate  # only a directory this call created is ever removed
        staged: dict[str, Path] = {}
        for index, (op, rel, sha) in enumerate(ops):
            if op == "write":
                assert sha is not None
                try:
                    staged[rel] = _stage(work_fd, rel, sha, staging, index)
                except OSError as exc:
                    raise CopyBackRefused(f"entry_replaced:{rel}") from exc
        _commit(ops, manifest, current, staged, target_real)
    finally:
        os.close(work_fd)
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _commit(
    ops: list[tuple[str, str, Optional[str]]],
    manifest: Mapping[str, tuple],
    current: Mapping[str, tuple],
    staged: Mapping[str, Path],
    target_real: Path,
) -> None:
    """Apply staged changes; each destination is re-checked against its baseline first.

    Before the first change a mismatch is a ``CopyBackRefused``; after it,
    ``CopyBackPartial`` (the target is partly written and needs reconciliation).
    """
    applied = 0
    for op, rel, _sha in ops:
        destination = target_real / rel
        expected = None if op == "mkdir" else manifest.get(rel)
        try:
            unchanged = _target_entry(destination) == expected
        except OSError:
            unchanged = False
        if not unchanged:
            reason = f"target_changed:{rel}"
            raise CopyBackPartial(reason) if applied else CopyBackRefused(reason)
        try:
            if op == "mkdir":
                destination.mkdir()
            elif op == "write":
                if expected is not None:
                    mode = stat.S_IMODE(os.lstat(destination).st_mode)
                else:
                    mode = 0o755 if current[rel][2] else 0o644
                os.chmod(staged[rel], mode)
                os.replace(staged[rel], destination)
            elif manifest.get(rel, ("",))[0] == "dir":
                try:
                    destination.rmdir()
                except OSError:
                    pass  # not empty in the target: leave it
            else:
                destination.unlink()
        except OSError as exc:
            reason = f"apply_failed:{rel}:{type(exc).__name__}"
            raise CopyBackPartial(reason) if applied else CopyBackRefused(reason) from exc
        applied += 1


def _group_share_tree(root: Path, gid: int, read_only: Iterable[Path] = ()) -> None:
    """Make every Owner-created entry under ``root`` usable by the run group.

    Directories 2770, files 0660 (0770 when executable), ``read_only`` files
    0640.  Symlinks are skipped (never followed).  Only paths created by the
    dispatcher for this run are touched.
    """
    frozen = {os.path.realpath(path) for path in read_only}
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files, None]:
            path = Path(current) if name is None else Path(current) / name
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
                continue
            if info.st_gid != gid:
                os.chown(path, -1, gid)
            if stat.S_ISDIR(info.st_mode):
                mode = RUN_DIR_MODE
            elif str(path) in frozen:
                mode = 0o640
            else:
                mode = 0o770 if info.st_mode & 0o100 else 0o660
            os.chmod(path, mode)


# ---------------------------------------------------------------------------
# boundary
# ---------------------------------------------------------------------------


@dataclass
class AgyWorkerAccountBoundary(AgyDispatchBoundary):
    """``AgyDispatchBoundary`` whose agy runs as the worker account."""

    source_target: Path = Path("/")
    worker_user: str = WORKER_USER
    runs_dir: Path = WORKER_RUNS
    wrapper: Path = WORKER_WRAPPER
    worker_agy: Path = WORKER_AGY
    run_gid: int = -1
    manifest: dict = field(default_factory=dict)
    workdir_identity: tuple[int, int] = (-1, -1)
    worker_failure: Optional[str] = None
    leftover_run_root: Optional[str] = None
    run_command: Callable[..., Any] = field(default=subprocess.run, repr=False)
    # sha256 of the reference wrapper that prepare_worker_account_boundary
    # verified against the installed copy (receipt field only).
    wrapper_sha256: str = ""
    # Set by the dispatcher ({"operation_id", "attempt"}); None = emit no receipts.
    receipt_context: Optional[dict] = field(default=None, repr=False)
    receipts: list = field(default_factory=list, repr=False)
    _worker_swept: Optional[bool] = field(default=None, repr=False)
    _worker_verdict: Optional[str] = field(default=None, repr=False)
    # The wrapper itself reported survivors ("AGY_WORKER_SWEEP unclean <pids>").
    _worker_reported_unclean: bool = field(default=False, repr=False)
    _worker_left: list = field(default_factory=list, repr=False)
    _receipt_events: set = field(default_factory=set, repr=False)

    launch_env = LAUNCH_ENV

    @property
    def workdir(self) -> Path:
        return self.target

    def wrap_argv(self, argv: Iterable[str]) -> list[str]:
        return worker_argv(
            argv,
            run_root=self.run_root,
            workdir=self.target,
            profile_path=self.profile_path,
            user=self.worker_user,
            wrapper=self.wrapper,
            agy=self.worker_agy,
        )

    def _emit_receipt(self, event: str, **fields: Any) -> None:
        """Write one receipt line to stderr, at most once per event; never raises.

        Only owner-side values go in (never the environment, tokens, prompt or any
        path but the run root); nothing the worker account can write is read.
        """
        if self.receipt_context is None or event in self._receipt_events:
            return
        if event != "WORKER_LAUNCH" and "WORKER_LAUNCH" not in self._receipt_events:
            return  # no launch line was written: sweep/cleanup lines would orphan
        try:
            obj = {"event": event, "attempt": self.receipt_context.get("attempt"), **fields}
            line = RECEIPT_PREFIX + json.dumps(obj, sort_keys=True) + "\n"
            sys.stderr.write(line)
            sys.stderr.flush()
        except Exception:
            # A closed stderr or an unserialisable value must not break the run.
            # The event stays unrecorded, so a launch line that was not written
            # keeps the sweep and cleanup lines from appearing without it.
            return
        self._receipt_events.add(event)
        self.receipts.append(obj)

    def _emit_launch_receipt(self) -> None:
        if self.receipt_context is None or "WORKER_LAUNCH" in self._receipt_events:
            return
        try:
            info = os.lstat(self.run_root)  # the owner's own lstat, taken before launch
            fields = {
                "operation_id": self.receipt_context.get("operation_id"),
                "run_as_user": self.worker_user,
                "run_root": str(self.run_root),
                "run_root_id": [info.st_dev, info.st_ino],
                # The pid exists only after Popen; the line is never delayed for it.
                "pid": None,
                "lstart": None,
                "wrapper_sha256": self.wrapper_sha256,
            }
        except Exception:
            return  # no launch line: the caller rejects a run without one
        self._emit_receipt("WORKER_LAUNCH", **fields)

    def _emit_sweep_receipt(self, result: str) -> None:
        # left: the bare pids the wrapper reported as surviving (it does not
        # report pid:lstart tokens); [] unless the wrapper said "unclean".
        # wrapper: the owner-side verdict of the last wrapper sweep, so a result
        # the start marker decided ("not_started") can be told apart.
        verdict = self._worker_verdict
        if verdict == "UNCLEAN" and not self._worker_reported_unclean:
            verdict = "REFUSED"  # no report line: sudo or the wrapper refused
        self._emit_receipt(
            "WORKER_SWEEP", result=result, left=list(self._worker_left), wrapper=verdict
        )

    def _sweep_result(self, started: bool) -> str:
        """The receipt word for the verdict ``sweep`` just stored in ``_swept``.

        Derived only from ``_swept`` (the value the journal's
        ``descendant_sweep_clean`` records) so "clean" and "not_started" can never
        be written for a sweep that was unclean.
        """
        if self._swept:
            return "clean" if started else "not_started"
        return "error" if self._worker_verdict == "SWEEP_ERROR" else "unclean"

    def _emit_cleanup_receipt(self) -> None:
        if "WORKER_SWEEP" not in self._receipt_events:
            # Launch line written but no sweep ran: the launch frame raised
            # before the worker existed (not launched) or the sweep failed.
            self._emit_sweep_receipt("error" if self._launched else "not_started")
        failure = self.worker_failure
        self._emit_receipt(
            "WORKER_CLEANUP",
            run_root_removed=not os.path.lexists(self.run_root),
            # kind:reason only; later segments may name worker-chosen files
            worker_failure=":".join(failure.split(":", 2)[:2]) if failure else None,
        )

    def before_launch(self) -> None:
        # Everything the dispatcher wrote (copied session files, settings,
        # keychain, permission profile, workdir copy) becomes usable by the
        # run group; the agy settings and the profile stay read-only.
        _group_share_tree(
            self.run_root,
            self.run_gid,
            read_only=(self.run_home / AGY_RUN_HOME_SETTINGS, self.profile_path),
        )
        super().before_launch()
        self._emit_launch_receipt()

    def _worker_sweep(self, pids: Iterable[int]) -> bool:
        baseline = self._baseline
        tokens = pid_start_tokens(pids, since=getattr(baseline, "started_at", None))
        self._worker_verdict, last = sweep_run_root_report(
            self.run_root,
            tokens,
            user=self.worker_user,
            wrapper=self.wrapper,
            run_command=self.run_command,
        )
        words = last.split()
        self._worker_reported_unclean = words[:2] == ["AGY_WORKER_SWEEP", "unclean"]
        self._worker_left = (
            [w for w in words[2:] if w.isascii() and w.isdigit() and len(w) <= 10][:64]
            if self._worker_reported_unclean
            else []
        )
        return self._worker_verdict == "CLEAN"

    @property
    def sweep_verdict_clean(self) -> bool:
        """The recorded verdict, without running a sweep (#2888 lease release).

        True when nothing launched or the run-once sweep finished clean; False
        when it was unclean, raised before recording a verdict, or never ran.
        """
        return not self._launched or self._swept is True

    def terminate_worker(self) -> None:
        """Kill this run's worker processes now (timeout, quota): the Owner cannot."""
        if self._launched:
            self._worker_sweep(())

    def sweep(self) -> bool:
        """Worker-side kill through the wrapper, then the normal Owner-side sweep.

        Clean only when both are clean: the wrapper found no live run-tagged,
        run-cwd or tracked worker process, and the Owner-side check confirms the
        tracked descendants are gone.
        """
        if not self._launched:
            return True
        if self._swept is not None:
            return self._swept
        # The wrapper writes the marker just before it execs agy.  Without it
        # (sudo or the wrapper refused) no worker process of this run exists,
        # and a sudo that refuses the launch refuses the sweep too; the
        # Owner-side check of the tracked descendants still has to be clean.
        started = (self.run_root / WRAPPER_STARTED_MARKER).exists()
        try:
            # stop() takes a final snapshot; the Owner-side sweep below calls it again.
            tracked = self._tracker.stop() if self._tracker is not None else set()
            self._worker_swept = self._worker_sweep(tracked)
            owner_clean = super().sweep()
            # The marker lives in the run root, which the worker account can
            # write, so its absence may excuse only a refused sweep (sudo
            # refuses the launch and the sweep alike: non-zero, no report
            # line), never the wrapper's own report that worker processes of
            # this run survived and never a sweep that errored or timed out.
            refused = self._worker_verdict == "UNCLEAN" and not self._worker_reported_unclean
            excused = not started and refused
            self._swept = bool(owner_clean and (self._worker_swept or excused))
        except BaseException:
            self._emit_sweep_receipt("error")  # a sweep that cannot finish is never clean
            raise
        self._emit_sweep_receipt(self._sweep_result(started))
        return self._swept

    def cleanup(self) -> None:
        if self._launched and self._swept is None:
            self.sweep()
        tracker, self._tracker = self._tracker, None
        if tracker is not None:
            tracker.stop()
        cli_worker.release_run(self.run_tag)
        try:
            if self._launched and not (self.run_root / WRAPPER_STARTED_MARKER).exists():
                self.worker_failure = f"{AGY_WORKER_LAUNCH_FAILED}:wrapper_did_not_start"
            elif self._launched and self._swept:
                # A clean sweep does not prove no worker process survived (one
                # that cleared its env, left the run cwd and escaped the
                # tracker is not found); copy_back therefore trusts nothing in
                # the run dir beyond the verified workdir fd and the plan hashes.
                copy_back(
                    self.manifest,
                    self.run_root,
                    self.target.name,
                    self.workdir_identity,
                    self.source_target,
                )
        except CopyBackRefused as exc:
            self.worker_failure = f"{AGY_WORKER_COPY_BACK_REFUSED}:{exc}"
        except CopyBackPartial as exc:
            self.worker_failure = f"{AGY_WORKER_COPY_BACK_FAILED}:{exc}"
        except OSError as exc:
            self.worker_failure = f"{AGY_WORKER_COPY_BACK_FAILED}:{type(exc).__name__}"
        finally:
            if os.environ.get(KEEP_RUN_ROOT_ENV) != "1":
                shutil.rmtree(self.run_root, ignore_errors=True)
                if os.path.lexists(self.run_root):
                    self.leftover_run_root = str(self.run_root)
                    sys.stderr.write(
                        f"nexus-agy-dispatch: worker run dir left behind: {self.run_root}\n"
                    )
            self._emit_cleanup_receipt()


def prepare_worker_account_boundary(
    *,
    source_env: Optional[Mapping[str, str]],
    target: str | Path,
    worker_user: str,
    source_agy: Optional[str],
    runs_dir: Path = WORKER_RUNS,
    wrapper: Path = WORKER_WRAPPER,
    worker_agy: Path = WORKER_AGY,
    run_group: str = WORKER_RUN_GROUP,
    repo_wrapper: Path = REPO_WRAPPER,
    run_command: Callable[..., Any] = subprocess.run,
) -> AgyWorkerAccountBoundary:
    """Build one run's worker-account boundary, or refuse before anything is launched."""
    if worker_user != WORKER_USER:
        raise _refuse("worker_user_not_allowed")
    if not boundary_available():
        raise _refuse("seatbelt_unavailable")
    try:
        pwd.getpwnam(worker_user)
    except KeyError as exc:
        raise _refuse("worker_user_missing") from exc
    try:
        gid = grp.getgrnam(run_group).gr_gid
    except KeyError as exc:
        raise _refuse("run_group_missing") from exc
    if gid not in os.getgroups():
        raise _refuse("owner_not_in_run_group")
    runs_dir = _check_runs_dir(Path(runs_dir), gid)
    _check_owner_executable(Path(wrapper), "wrapper")
    if not repo_wrapper.is_file():
        raise _refuse("wrapper_reference_missing")
    wrapper_sha256 = _sha256_file(repo_wrapper)
    if _sha256_file(Path(wrapper)) != wrapper_sha256:
        raise _refuse("wrapper_stale")
    _check_owner_executable(Path(worker_agy), "worker_agy")
    if not source_agy or _sha256_file(Path(worker_agy)) != _sha256_file(Path(source_agy)):
        raise _refuse("worker_agy_stale")
    source_target = Path(os.path.realpath(Path(target).expanduser()))
    if not source_target.is_dir():
        raise _refuse("target_missing")

    run_tag = secrets.token_hex(16)
    run_root = runs_dir / run_tag
    os.mkdir(run_root, 0o700)
    try:
        os.chmod(run_root, RUN_DIR_MODE)
        if run_root.stat().st_gid != gid:
            os.chown(run_root, -1, gid)
        workdir = run_root / WORKDIR_NAME
        manifest = _copy_in(source_target, workdir)
        _check_copy_caps(manifest, workdir)
        _git_snapshot(workdir)
        work_info = os.lstat(workdir)
        workdir_identity = (work_info.st_dev, work_info.st_ino)
        run_home = run_root / "home"
        run_tmp = run_root / "tmp"
        run_tmp.mkdir()
        source_home = worker_home(source_env)
        refusal, home_profile_sha256 = materialize_run_home(
            source_home, run_home, read_only=False, isolate_keychain=False
        )
        if refusal is not None:
            raise AgyWriteBoundaryError(f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:{refusal}")
        keychain_state = _prepare_run_home_keychain(run_home)
        try:
            profile = cross_run_profile(
                build_seatbelt_profile(
                    run_root=run_root,
                    writable_target=workdir,
                    run_home=run_home,
                    source_home=source_home,
                ),
                runs_dir=runs_dir,
                run_root=run_root,
                pinned_entries=(workdir, run_home, run_tmp, run_root / PROFILE_NAME),
            )
        except CredentialPathOverlapError as exc:
            raise AgyWriteBoundaryError(
                f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:target_inside_credential_path"
            ) from exc
        except ValueError as exc:
            raise AgyWriteBoundaryError(
                f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:profile_unrepresentable"
            ) from exc
        profile_path = run_root / PROFILE_NAME
        profile_path.write_text(profile, encoding="utf-8")
        # The env the dispatcher itself uses (permission install, transcript
        # lookup); the wrapper builds the worker's own fixed environment.
        env = agy_child_env(source_env, home=run_home, tmpdir=run_tmp)
        env[cli_worker.RUN_TAG_ENV] = run_tag
    except BaseException:
        shutil.rmtree(run_root, ignore_errors=True)
        raise
    return AgyWorkerAccountBoundary(
        target=workdir,
        run_root=run_root,
        run_home=run_home,
        run_tmp=run_tmp,
        env=env,
        profile=profile,
        profile_path=profile_path,
        run_tag=run_tag,
        home_profile_sha256=home_profile_sha256,
        keychain_state=keychain_state,
        source_target=source_target,
        worker_user=worker_user,
        runs_dir=runs_dir,
        wrapper=Path(wrapper),
        worker_agy=Path(worker_agy),
        run_gid=gid,
        manifest=manifest,
        workdir_identity=workdir_identity,
        run_command=run_command,
        wrapper_sha256=wrapper_sha256,
    )
