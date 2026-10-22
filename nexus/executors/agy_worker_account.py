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
only Seatbelt separates them.
"""

from __future__ import annotations

import grp
import hashlib
import os
import pwd
import secrets
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from nexus.executors import cli_worker
from nexus.executors.agy_dispatch_boundary import (
    AGY_WRITE_BOUNDARY_UNAVAILABLE,
    KEEP_RUN_ROOT_ENV,
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
WORKER_ROOT = Path("/Users/Shared/cairnwork-worker")
WORKER_RUNS = WORKER_ROOT / "worker-runs"
WORKER_BIN = WORKER_ROOT / "bin"
WORKER_WRAPPER = WORKER_BIN / "agy-worker-exec"
WORKER_AGY = WORKER_BIN / "agy"
SUDO_PATH = "/usr/bin/sudo"
SWEEP_FLAG = "--sweep"
WRAPPER_STARTED_MARKER = ".worker-exec-started"
WORKER_RUNS_MODE = 0o2710
RUN_DIR_MODE = 0o2770
SWEEP_TIMEOUT_SECONDS = 30.0
# The sudo process itself gets only this; the wrapper discards it and builds its own.
LAUNCH_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"}

AGY_WORKER_ACCOUNT_REFUSED = "AGY_WORKER_ACCOUNT_REFUSED"
AGY_WORKER_LAUNCH_FAILED = "AGY_WORKER_LAUNCH_FAILED"
AGY_WORKER_COPY_BACK_FAILED = "AGY_WORKER_COPY_BACK_FAILED"

# The wrapper this module speaks to: the installed copy must equal this file.
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


def cross_run_profile(base_profile: str, *, runs_dir: Path, run_root: Path) -> str:
    """Add the cross-run rules to the normal profile.

    The read/write deny on ``runs_dir`` and the read re-allow of ``run_root``
    go right after ``(allow default)``: the normal profile's later
    ``(deny file-write*)``/``(allow file-write* run_root ...)`` lines then
    re-open writes only inside this run, and its write denies inside the run
    (``.git``, the run-HOME settings) still come last and win.  Signals are
    limited to this sandbox instance (separate ``sandbox-exec`` runs never
    share one, probed on macOS 27).
    """
    head = "(version 1)\n(allow default)\n"
    if not base_profile.startswith(head):
        raise ValueError("unexpected base profile shape")
    runs, root = _sbpl_path(runs_dir), _sbpl_path(run_root)
    cross_run = (
        ";; Cairnwork #19 Phase B: other runs share this uid; only this run's subpath is visible\n"
        f'(deny file-read* file-write* (subpath "{runs}"))\n'
        f'(allow file-read* (subpath "{root}"))\n'
    )
    signals = "(deny signal)\n(allow signal (target same-sandbox))\n"
    return head + cross_run + base_profile[len(head) :] + signals


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
    pids: Iterable[int],
    *,
    user: str = WORKER_USER,
    wrapper: Path = WORKER_WRAPPER,
) -> list[str]:
    """``sudo -n -u <user> <wrapper> --sweep <run_root> <pid>...``."""
    return [
        SUDO_PATH,
        "-n",
        "-u",
        user,
        str(wrapper),
        SWEEP_FLAG,
        str(run_root),
        *[str(pid) for pid in sorted({int(p) for p in pids if int(p) > 1})],
    ]


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

_SKIPPED_TOP_LEVEL = frozenset({".git", *TARGET_AGY_CUSTOMIZATION_PATHS})


def _walk_tree(root: Path) -> dict[str, tuple]:
    """``relpath -> ("dir",) | ("file", sha256, exec) | ("symlink", target) | ("other",)``.

    Never follows symlinks; skips the top-level ``.git`` and agy customization
    entries, which never cross into or out of the worker copy.
    """
    entries: dict[str, tuple] = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(current, root)
        if rel_dir == ".":
            dirs[:] = [d for d in dirs if d not in _SKIPPED_TOP_LEVEL]
            files = [f for f in files if f not in _SKIPPED_TOP_LEVEL]
        for name in list(dirs) + list(files):
            path = Path(current) / name
            rel = os.path.normpath(os.path.join(rel_dir, name))
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                entries[rel] = ("symlink", os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                entries[rel] = ("dir",)
            elif stat.S_ISREG(info.st_mode):
                entries[rel] = ("file", _sha256_file(path), bool(info.st_mode & 0o100))
            else:
                entries[rel] = ("other",)
        # os.walk lists symlinked directories in ``dirs``; never descend into them.
        dirs[:] = [d for d in dirs if not (Path(current) / d).is_symlink()]
    return entries


def _copy_in(source: Path, workdir: Path) -> dict[str, tuple]:
    """Copy ``source`` (without .git / customizations / special files) into ``workdir``."""
    manifest = _walk_tree(source)
    workdir.mkdir()
    for rel, entry in sorted(manifest.items()):
        src, dst = source / rel, workdir / rel
        kind = entry[0]
        if kind == "dir":
            dst.mkdir()
        elif kind == "symlink":
            os.symlink(entry[1], dst)
        elif kind == "file":
            shutil.copyfile(src, dst, follow_symlinks=False)
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


def plan_copy_back(
    manifest: Mapping[str, tuple], workdir: Path, target: Path
) -> tuple[list[tuple[str, str]], Optional[str]]:
    """Changes to apply to ``target``: ``[(op, relpath)]`` or a refusal reason.

    ``op`` is ``mkdir``, ``write`` or ``delete``.  A new or changed symlink, a
    special file, a type change, or a destination whose parent is not a real
    directory inside the target is refused (nothing is applied).
    """
    current = _walk_tree(workdir)
    ops: list[tuple[str, str]] = []
    for rel in sorted(current):
        entry, before = current[rel], manifest.get(rel)
        kind = entry[0]
        if kind == "other":
            return [], f"special_file:{rel}"
        if kind == "symlink":
            if before != entry:
                return [], f"symlink_created:{rel}"
            continue
        if before is not None and before[0] != kind:
            return [], f"type_changed:{rel}"
        if kind == "dir" and before is None:
            ops.append(("mkdir", rel))
        elif kind == "file" and before != entry:
            ops.append(("write", rel))
    for rel in sorted(set(manifest) - set(current), reverse=True):
        ops.append(("delete", rel))
    target_real = os.path.realpath(target)
    for _op, rel in ops:
        # ``rel`` comes from os.walk (no ``..``); any symlink on the way to the
        # destination's parent in the target would redirect the write.
        parent = os.path.dirname(os.path.join(target_real, rel))
        if os.path.realpath(parent) != parent:
            return [], f"destination_through_symlink:{rel}"
        if (Path(target_real) / rel).is_symlink():
            return [], f"destination_is_symlink:{rel}"
    return ops, None


def apply_copy_back(
    ops: list[tuple[str, str]], manifest: Mapping[str, tuple], workdir: Path, target: Path
) -> None:
    target_real = Path(os.path.realpath(target))
    for op, rel in ops:
        destination = target_real / rel
        if op == "mkdir":
            destination.mkdir(exist_ok=True)
        elif op == "write":
            source = workdir / rel
            executable = bool(os.lstat(source).st_mode & 0o100)
            mode = 0o755 if executable else 0o644
            if destination.exists() and not destination.is_symlink():
                mode = stat.S_IMODE(destination.stat().st_mode)
            temporary = destination.with_name(
                f".{destination.name}.agy-worker-{secrets.token_hex(4)}"
            )
            with open(source, "rb") as src_fh:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as dst_fh:
                    shutil.copyfileobj(src_fh, dst_fh)
            os.chmod(temporary, mode)
            os.replace(temporary, destination)
        elif op == "delete":
            if manifest.get(rel, ("",))[0] == "dir":
                try:
                    destination.rmdir()
                except OSError:
                    pass  # not empty in the target: leave it
            else:
                try:
                    destination.unlink()
                except FileNotFoundError:
                    pass


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
    worker_failure: Optional[str] = None
    run_command: Callable[..., Any] = field(default=subprocess.run, repr=False)
    _worker_swept: Optional[bool] = field(default=None, repr=False)

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

    def _worker_sweep(self, pids: Iterable[int]) -> bool:
        try:
            completed = self.run_command(
                sweep_argv(self.run_root, pids, user=self.worker_user, wrapper=self.wrapper),
                cwd="/",
                env=dict(LAUNCH_ENV),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=SWEEP_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        lines = (completed.stdout or "").strip().splitlines()
        return completed.returncode == 0 and bool(lines) and lines[-1] == "AGY_WORKER_SWEEP clean"

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
        # stop() takes a final snapshot; the Owner-side sweep below calls it again.
        tracked = self._tracker.stop() if self._tracker is not None else set()
        self._worker_swept = self._worker_sweep(tracked)
        owner_clean = super().sweep()
        self._swept = bool(owner_clean and (self._worker_swept or not started))
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
                ops, refusal = plan_copy_back(self.manifest, self.target, self.source_target)
                if refusal is not None:
                    self.worker_failure = f"{AGY_WORKER_COPY_BACK_FAILED}:{refusal}"
                else:
                    apply_copy_back(ops, self.manifest, self.target, self.source_target)
        except OSError as exc:
            self.worker_failure = f"{AGY_WORKER_COPY_BACK_FAILED}:{type(exc).__name__}"
        finally:
            if os.environ.get(KEEP_RUN_ROOT_ENV) != "1":
                shutil.rmtree(self.run_root, ignore_errors=True)


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
    if repo_wrapper.is_file() and _sha256_file(Path(wrapper)) != _sha256_file(repo_wrapper):
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
        workdir = run_root / "work"
        manifest = _copy_in(source_target, workdir)
        _git_snapshot(workdir)
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
            )
        except CredentialPathOverlapError as exc:
            raise AgyWriteBoundaryError(
                f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:target_inside_credential_path"
            ) from exc
        except ValueError as exc:
            raise AgyWriteBoundaryError(
                f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:profile_unrepresentable"
            ) from exc
        profile_path = run_root / "agy-dispatch.sb"
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
        run_command=run_command,
    )
