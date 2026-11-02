import errno
import fcntl
import logging
import os
import secrets
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Optional

from nexus.core.hardened_git import (
    GIT_TIMEOUT_S,
    linked_worktree_git_dir,
    repository_config_can_start_a_program,
    run_hardened_git,
)

logger = logging.getLogger(__name__)

_LOCK_NAME = ".swarm_lock"
_SHARED_CACHE_DIRS = (".venv", "node_modules", ".ruff_cache")
_DIR_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_SOURCE_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
_NEW_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_LOCK_FILE_FLAGS = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
# Written into the lock by a release that left the swarm locked; only such a lock is recovered.
_RELEASE_FAILED_MARK = b"release_failed\n"
_STATE_RELEASE_FAILED = "release_failed"
# An index.lock this old cannot belong to a git started by the hardened runner (killed after
# GIT_TIMEOUT_S).
_STALE_INDEX_LOCK_SEC = 2 * GIT_TIMEOUT_S


class _SwarmDirSwapped(Exception):
    """The swarm path no longer names the directory that release() validated."""


class _RefusedTarget(OSError):
    """A link or non-directory stands where a directory inside the swarm is expected."""


def _real_dir_identity(path: Path) -> Optional[tuple[int, int]]:
    """(st_dev, st_ino) of `path` itself, without following a final symlink; None if not a directory."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        return None
    return (info.st_dev, info.st_ino)


def _open_real_dir(path, dir_fd: Optional[int] = None) -> int:
    """Open a directory without following a final symlink; raises OSError otherwise."""
    return os.open(path, _DIR_OPEN_FLAGS, dir_fd=dir_fd)


def _fd_identity(fd: int) -> tuple[int, int]:
    info = os.fstat(fd)
    return (info.st_dev, info.st_ino)


def _names_dir(path: Path, fd: int) -> bool:
    """True while `path` still names the directory open at `fd`."""
    return _real_dir_identity(path) == _fd_identity(fd)


def _open_child_dir(parent_fd: int, name: str, create: bool) -> int:
    """Open (and with `create`, make) directory `name` in `parent_fd` without following links."""
    if create:
        try:
            os.mkdir(name, dir_fd=parent_fd)
        except FileExistsError:
            pass
    try:
        return _open_real_dir(name, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise _RefusedTarget(exc.errno, "not a real directory", name) from exc
        raise


def _write_fresh_entry(
    parent_fd: int,
    name: str,
    write: Callable,
    mode: int,
    times_ns: Optional[tuple[int, int]] = None,
) -> None:
    """Write a new file beside `name` in `parent_fd` and rename it over `name`.

    Both the new file and the rename are relative to the open directory, so a parent swapped
    after it was opened is not followed, and the rename replaces the directory entry at `name`
    instead of opening it, so a file shared with a path outside is left as it was.
    """
    for _ in range(100):
        tmp_name = f".{name}.{secrets.token_hex(4)}.swarm-sync"
        try:
            fd = os.open(tmp_name, _NEW_FILE_FLAGS, 0o600, dir_fd=parent_fd)
            break
        except FileExistsError:
            continue
    else:
        raise FileExistsError(errno.EEXIST, "no free temporary name", name)
    try:
        with os.fdopen(fd, "wb") as out:
            write(out)
            out.flush()
            os.fchmod(out.fileno(), mode)
            if times_ns is not None:
                os.utime(out.fileno(), ns=times_ns)
        os.replace(tmp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    except BaseException:
        try:
            os.unlink(tmp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        raise


# What opening a socket, or a link with O_NOFOLLOW, fails with (Linux, macOS).
_NOT_A_FILE_ERRNOS = {errno.ELOOP, errno.ENXIO, errno.EOPNOTSUPP, getattr(errno, "ENOTSUP", -1)}


def _open_regular_file(path, dir_fd: Optional[int] = None) -> Optional[int]:
    """A read descriptor for `path` when it is a regular file, else None (nothing left open).

    A link, FIFO, socket, device or directory seen by an lstat is never opened. O_NONBLOCK
    keeps a FIFO swapped in after that lstat from blocking the open, and the type is checked
    again on the descriptor itself, so any entry swapped in after the lstat is refused too.
    """
    if not stat.S_ISREG(os.stat(path, dir_fd=dir_fd, follow_symlinks=False).st_mode):
        return None
    try:
        fd = os.open(path, _SOURCE_FILE_FLAGS, dir_fd=dir_fd)
    except OSError as exc:
        if exc.errno in _NOT_A_FILE_ERRNOS:
            return None
        raise
    try:
        is_regular = stat.S_ISREG(os.fstat(fd).st_mode)
    except BaseException:
        os.close(fd)
        raise
    if not is_regular:
        os.close(fd)
        return None
    return fd


def read_text_in_dir(root: Path, rel_path: str, encoding: str = "utf-8") -> Optional[str]:
    """The text of `root/rel_path`, or None when that entry is not a regular file.

    Every directory between `root` and the file is opened without following links (a link on
    the way raises OSError), and the file itself is opened through `_open_regular_file`, so a
    FIFO cannot block the read.
    """
    parts = Path(rel_path).parts
    if not parts or Path(rel_path).is_absolute() or ".." in parts:
        raise ValueError(f"path must stay inside {root}: {rel_path}")
    opened = [_open_real_dir(root)]
    try:
        for part in parts[:-1]:
            opened.append(_open_child_dir(opened[-1], part, create=False))
        fd = _open_regular_file(parts[-1], dir_fd=opened[-1])
        if fd is None:
            return None
        with open(fd, "rb") as handle:
            return handle.read().decode(encoding)
    finally:
        for dir_fd in opened:
            os.close(dir_fd)


def _drop_stale_copy(parent_fd: int, name: str) -> None:
    """Remove what an earlier sync left at `name`, so a refused source is not run as synced.

    Only a non-directory entry is removed, relative to the open directory."""
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(info.st_mode):
        _unlink_at(parent_fd, name)


def _copy_file_into(src: Path, parent_fd: int, name: str) -> None:
    source_fd = _open_regular_file(src)
    if source_fd is None:
        logger.warning("⚠️ [SwarmBroker] Refused scope source that is not a regular file: %s", src)
        _drop_stale_copy(parent_fd, name)
        return
    with open(source_fd, "rb") as fsrc:
        info = os.fstat(fsrc.fileno())
        _write_fresh_entry(
            parent_fd,
            name,
            lambda out: shutil.copyfileobj(fsrc, out),
            stat.S_IMODE(info.st_mode),
            (info.st_atime_ns, info.st_mtime_ns),
        )


def _copy_dir_into(src_dir: Path, dst_fd: int) -> None:
    """Copy the files and directories under `src_dir` into the open directory `dst_fd`.

    Links in the source tree are skipped: their targets are not part of the named scope and may
    lie outside the workspace (or loop back into it), and a link recreated in the swarm would be
    one a candidate could write through.
    """
    with os.scandir(src_dir) as entries:
        children = list(entries)
    for entry in children:
        if entry.is_dir(follow_symlinks=False):
            try:
                child_fd = _open_child_dir(dst_fd, entry.name, create=True)
            except _RefusedTarget:
                logger.warning(
                    "⚠️ [SwarmBroker] Refused scope target that is not a real directory: %s",
                    entry.path,
                )
                continue
            try:
                _copy_dir_into(Path(entry.path), child_fd)
            finally:
                os.close(child_fd)
        else:
            # Files; links, FIFOs, sockets and devices are refused there without being opened,
            # and an earlier copy of them is removed.
            _copy_file_into(Path(entry.path), dst_fd, entry.name)


def _unlink_link_at(dir_fd: int, name: str) -> None:
    try:
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        os.unlink(name, dir_fd=dir_fd)


def _unlink_at(dir_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        pass


def _entry_identity_at(dir_fd: int, name: str) -> Optional[tuple[int, int]]:
    try:
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    return (info.st_dev, info.st_ino)


def _open_lock(swarm_fd: int) -> Optional[int]:
    """A read-write descriptor for the swarm's lock when it is a regular file, else None."""
    try:
        if not stat.S_ISREG(os.stat(_LOCK_NAME, dir_fd=swarm_fd, follow_symlinks=False).st_mode):
            return None
        fd = os.open(_LOCK_NAME, _LOCK_FILE_FLAGS, dir_fd=swarm_fd)
    except OSError:
        return None
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        return None
    return fd


def _lock_state(swarm_fd: int) -> Optional[str]:
    """None when the swarm open at `swarm_fd` has no lock, else `held` or `release_failed`."""
    if _entry_identity_at(swarm_fd, _LOCK_NAME) is None:
        return None
    fd = _open_lock(swarm_fd)
    if fd is None:
        return "held"
    try:
        mark = os.pread(fd, len(_RELEASE_FAILED_MARK) + 1, 0)
    finally:
        os.close(fd)
    return _STATE_RELEASE_FAILED if mark == _RELEASE_FAILED_MARK else "held"


def _entry_exists_at(dir_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def replace_text_in_dir(root: Path, rel_path: str, text: str, encoding: str = "utf-8") -> None:
    """Replace `root/rel_path` with a new file holding `text`, renamed into place.

    Every directory between `root` and the file is opened without following links, so the
    write stays inside `root`; the file's previous mode is kept.
    """
    parts = Path(rel_path).parts
    if not parts or Path(rel_path).is_absolute() or ".." in parts:
        raise ValueError(f"path must stay inside {root}: {rel_path}")
    opened = [_open_real_dir(root)]
    try:
        for part in parts[:-1]:
            opened.append(_open_child_dir(opened[-1], part, create=False))
        try:
            info = os.stat(parts[-1], dir_fd=opened[-1], follow_symlinks=False)
            mode = stat.S_IMODE(info.st_mode) if stat.S_ISREG(info.st_mode) else 0o644
        except FileNotFoundError:
            mode = 0o644
        data = text.encode(encoding)
        _write_fresh_entry(opened[-1], parts[-1], lambda out: out.write(data), mode)
    finally:
        for fd in opened:
            os.close(fd)


class SwarmBroker:
    """
    🐝 蜂群空間調度器 (Swarm Workspace Broker)
    管理實體 `.nexus-swarm-*` 目錄的租用、同步與釋放。
    提供真正的物理隔離平行測試環境，消滅高並行競爭。
    """
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        # Find all available swarm directories (e.g., .nexus-swarm-001 to 050)
        self.swarm_dirs = sorted([d for d in self.workspace.glob(".nexus-swarm-*") if self._is_swarm_child_dir(d)])
        if not self.swarm_dirs:
            logger.warning("⚠️ [SwarmBroker] No .nexus-swarm-* directories found. Parallel isolation may be degraded.")

    def _is_swarm_child_dir(self, swarm_dir: Path) -> bool:
        """A swarm workspace is a real `.nexus-swarm-*` directory directly under the workspace."""
        if ".." in Path(swarm_dir).parts:
            return False
        path = Path(os.path.abspath(swarm_dir))
        if path.is_symlink() or not path.is_dir():
            return False
        return path.name.startswith(".nexus-swarm-") and path.parent.resolve() == self.workspace

    def _git_output(self, args: List[str], cwd: Path) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    def _git_top_level(self, path: Path) -> Optional[Path]:
        output = self._git_output(["rev-parse", "--show-toplevel"], path)
        if not output:
            return None
        return Path(output).resolve()

    def _controller_git_top_level(self) -> Optional[Path]:
        return self._git_top_level(self.workspace)

    def _registered_worktree_paths(self) -> set[Path]:
        output = self._git_output(["worktree", "list", "--porcelain"], self.workspace)
        if output is None:
            return set()

        paths: set[Path] = set()
        for line in output.splitlines():
            key, _, value = line.partition(" ")
            if key == "worktree" and value:
                paths.add(Path(value).resolve())
        return paths

    def is_independently_registered_worktree(self, swarm_dir: Path) -> bool:
        """
        Validate that a swarm path is a separate Git worktree registered by the
        controller, not a normal child directory that resolves back to it.
        """
        if Path(swarm_dir).is_symlink():
            return False
        swarm_path = Path(swarm_dir).resolve()
        if not swarm_path.is_dir():
            return False
        controller_top_level = self._controller_git_top_level()
        if controller_top_level is None:
            return False

        top_level = self._git_top_level(swarm_path)
        if top_level != swarm_path or top_level == controller_top_level:
            return False
        if not self._git_metadata_points_to_own_admin_entry(swarm_path):
            return False
        return swarm_path in self._registered_worktree_paths()

    def _git_metadata_points_to_own_admin_entry(self, swarm_path: Path) -> bool:
        """
        The swarm's `.git` file must name an admin entry under the controller's
        `<common-dir>/worktrees/`, and that entry's `gitdir` must point back to it.
        """
        common_dir = self._git_output(
            ["rev-parse", "--path-format=absolute", "--git-common-dir"], self.workspace
        )
        git_dir = self._git_output(["rev-parse", "--absolute-git-dir"], swarm_path)
        if not common_dir or not git_dir:
            return False
        admin_dir = Path(git_dir).resolve()
        if admin_dir.parent != (Path(common_dir) / "worktrees").resolve():
            return False
        # The admin entry's `commondir` decides whose refs and objects the swarm uses.
        swarm_common_dir = self._git_output(
            ["rev-parse", "--path-format=absolute", "--git-common-dir"], swarm_path
        )
        if not swarm_common_dir or Path(swarm_common_dir).resolve() != Path(common_dir).resolve():
            return False
        try:
            back_pointer = (admin_dir / "gitdir").read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return False
        if not back_pointer:
            return False
        # Relative entries (worktree.useRelativePaths) are relative to the admin dir.
        return (admin_dir / back_pointer).resolve() == swarm_path / ".git"

    def acquire(self, timeout_sec: float = 60.0) -> Optional[Path]:
        """
        租用一個閒置的 Swarm 目錄。支援跨進程的原子鎖定。
        """
        if not self.swarm_dirs:
            return None
        # The timeout counts from here, so recovery and validation are part of it; every
        # eligible swarm is still tried once.
        start_time = time.time()
        self.recover_failed_releases()

        eligible_dirs = []
        for swarm_dir in self.swarm_dirs:
            # Taken before the check: a directory replaced during or after it fails to match
            # when the lock is attempted.
            identity = _real_dir_identity(swarm_dir)
            if identity is not None and self.is_independently_registered_worktree(swarm_dir):
                eligible_dirs.append((swarm_dir, identity))
        if not eligible_dirs:
            logger.warning("⚠️ [SwarmBroker] No independently registered swarm worktrees available.")
            return None

        while eligible_dirs:
            for entry in list(eligible_dirs):
                swarm_dir, identity = entry
                outcome = self._try_lock(swarm_dir, identity)
                if outcome is None:
                    eligible_dirs.remove(entry)
                elif outcome:
                    logger.debug(f"🐝 [SwarmBroker] Acquired swarm sandbox: {swarm_dir.name}")
                    return swarm_dir
            if not eligible_dirs or time.time() - start_time >= timeout_sec:
                break
            time.sleep(0.5)

        logger.error("❌ [SwarmBroker] Timeout waiting for an available Swarm directory.")
        return None

    def _try_lock(self, swarm_dir: Path, identity: tuple[int, int]) -> Optional[bool]:
        """True when locked, False when another holder has it, None when the path no longer
        names the directory that was validated (a lock taken here is then kept)."""
        try:
            pinned = _open_real_dir(swarm_dir)
        except OSError:
            logger.warning(
                "⚠️ [SwarmBroker] Swarm path is no longer a real directory: %s", swarm_dir
            )
            return None
        try:
            if _fd_identity(pinned) != identity:
                logger.warning(
                    "⚠️ [SwarmBroker] Swarm path was replaced after validation: %s", swarm_dir
                )
                return None
            try:
                # Exclusive create in the validated directory: cross-process lock.
                os.close(os.open(_LOCK_NAME, _NEW_FILE_FLAGS, 0o644, dir_fd=pinned))
            except FileExistsError:
                return False
            # 🚀 [Shared Cache] 加速啟動：掛載重型依賴
            self._mount_shared_cache(swarm_dir, pinned)
            if not _names_dir(swarm_dir, pinned):
                logger.warning(
                    "⚠️ [SwarmBroker] Swarm path was replaced while locking; lock kept: %s",
                    swarm_dir,
                )
                return None
            return True
        finally:
            os.close(pinned)

    def _mount_shared_cache(self, swarm_dir: Path, pinned: Optional[int] = None):
        """
        使用軟連結掛載 .venv 與 node_modules，避免磁碟 I/O 瓶頸。
        Links are created in the open directory `pinned` (opened here when not given).
        """
        if pinned is None:
            try:
                fd = _open_real_dir(swarm_dir)
            except OSError as e:
                logger.warning(f"⚠️ [SwarmBroker] Cache links skipped for {swarm_dir}: {e}")
                return
            try:
                self._mount_shared_cache(swarm_dir, fd)
            finally:
                os.close(fd)
            return
        for cache_dir in _SHARED_CACHE_DIRS:
            src = self.workspace / cache_dir
            if not src.exists():
                continue
            try:
                os.symlink(src, cache_dir, dir_fd=pinned)
            except FileExistsError:
                continue
            except OSError as e:
                logger.warning(f"⚠️ [SwarmBroker] Link failed for {cache_dir}: {e}")

    def sync_scope(self, swarm_dir: Path, scope_files: List[str], required_configs: List[str] = None):

        """
        將主工作區的 Scope 檔案與設定檔同步至 Swarm 目錄中。
        """
        if not required_configs:
            # Sync essential configuration files so testing works normally in the isolated dir
            required_configs = [
                "pytest.ini", 
                "pyproject.toml", 
                "uv.lock", 
                "tests/conftest.py"
            ]
            
        all_paths = list(scope_files) + required_configs
        if not self._is_swarm_child_dir(swarm_dir):
            logger.warning(
                "⚠️ [SwarmBroker] Refused to sync into a path that is not a swarm directory of this workspace: %s",
                swarm_dir,
            )
            return
        try:
            swarm_fd = _open_real_dir(swarm_dir)
        except OSError:
            logger.warning(
                "⚠️ [SwarmBroker] Refused to sync into a swarm path that is not a real directory: %s",
                swarm_dir,
            )
            return
        try:
            for rel_path in all_paths:
                dst_rel = self._scope_path_in_workspace(rel_path)
                if dst_rel is None or not dst_rel.parts:
                    # The workspace root itself holds the swarm, so copying it would recurse.
                    logger.warning(
                        "⚠️ [SwarmBroker] Refused scope path outside the workspace: %s", rel_path
                    )
                    continue
                src = self.workspace / dst_rel
                if not src.exists():
                    continue
                try:
                    self._sync_entry(src, swarm_fd, dst_rel.parts)
                except _RefusedTarget:
                    logger.warning(
                        "⚠️ [SwarmBroker] Refused scope target outside the swarm: %s",
                        Path(swarm_dir) / dst_rel,
                    )
        finally:
            os.close(swarm_fd)

    def _sync_entry(self, src: Path, swarm_fd: int, parts: tuple[str, ...]) -> None:
        """Copy `src` to `parts` under the open swarm directory, one no-follow open per level."""
        opened: list[int] = []
        try:
            parent = swarm_fd
            for part in parts[:-1]:
                parent = _open_child_dir(parent, part, create=True)
                opened.append(parent)
            if src.is_dir():
                opened.append(_open_child_dir(parent, parts[-1], create=True))
                _copy_dir_into(src, opened[-1])
            else:
                _copy_file_into(src, parent, parts[-1])
        finally:
            for fd in opened:
                os.close(fd)

    def _scope_path_in_workspace(self, rel_path: str) -> Optional[Path]:
        """A scope entry as a path relative to the workspace, or None if it leaves it."""
        raw_path = Path(rel_path)
        if ".." in raw_path.parts:
            return None
        src = raw_path if raw_path.is_absolute() else self.workspace / raw_path
        try:
            return src.resolve().relative_to(self.workspace)
        except (OSError, RuntimeError, ValueError):
            return None

    def release(self, swarm_dir: Path):
        """
        清空 Swarm 目錄內容（還原為初始狀態）並解除鎖定。
        實施重用 (Reuse) 策略：保留 .git 並使用 git reset/clean。
        """
        if not swarm_dir or not swarm_dir.exists():
            return
            
        if not self._is_swarm_child_dir(swarm_dir):
            logger.warning("⚠️ [SwarmBroker] Refused to release path that is not a swarm directory of this workspace: %s", swarm_dir)
            return

        try:
            pinned = _open_real_dir(swarm_dir)
        except OSError:
            logger.warning(
                "⚠️ [SwarmBroker] Refused to release swarm path that is not a real directory: %s",
                swarm_dir,
            )
            return
        try:
            self._release_holding_lock(swarm_dir, pinned, recovering=False)
        finally:
            os.close(pinned)

    def locked_swarms(self) -> List[tuple[Path, str]]:
        """Each swarm directory whose lock is present, with `release_failed` when its last
        release could not reset it (see `recover_failed_releases`), else `held`."""
        report = []
        for swarm_dir in self.swarm_dirs:
            try:
                pinned = _open_real_dir(swarm_dir)
            except OSError:
                continue
            try:
                state = _lock_state(pinned)
            finally:
                os.close(pinned)
            if state is not None:
                report.append((swarm_dir, state))
        return report

    def recover_failed_releases(
        self, stale_index_lock_after_sec: float = _STALE_INDEX_LOCK_SEC
    ) -> List[Path]:
        """Run the guarded release again on swarms whose last release failed; the swarms
        unlocked by it are returned and those still locked are logged.

        Only a lock marked by a failed release is taken up, so a swarm still leased is never
        touched. Before the release, an `index.lock` older than `stale_index_lock_after_sec`
        is removed from the swarm's own registration (a git killed mid-reset leaves one, and
        it fails every later reset). The swarm goes back to the pool only once its reset has
        succeeded, exactly as with `release`.
        """
        recovered = []
        for swarm_dir, state in self.locked_swarms():
            if state != _STATE_RELEASE_FAILED or not self._is_swarm_child_dir(swarm_dir):
                continue
            try:
                pinned = _open_real_dir(swarm_dir)
            except OSError:
                continue
            try:
                if self._release_holding_lock(
                    swarm_dir, pinned, recovering=True, stale_after=stale_index_lock_after_sec
                ):
                    recovered.append(swarm_dir)
            finally:
                os.close(pinned)
        stuck = [
            path.name for path, state in self.locked_swarms() if state == _STATE_RELEASE_FAILED
        ]
        if stuck:
            logger.warning(
                "⚠️ [SwarmBroker] Swarms left locked by a failed release: %s", ", ".join(stuck)
            )
        return recovered

    def _release_holding_lock(
        self,
        swarm_dir: Path,
        pinned: int,
        recovering: bool,
        stale_after: float = _STALE_INDEX_LOCK_SEC,
    ) -> bool:
        """The guarded release, holding an exclusive flock on the swarm's lock file so two
        releases or recoveries of one swarm never run at once; True once it is unlocked.

        A release that fails leaves the lock marked `release_failed` (written through the
        descriptor opened here, so a lock taken by a new holder in the meantime is never
        marked). With `recovering`, only a lock carrying that mark is taken up.
        """
        lock_fd = _open_lock(pinned)
        if lock_fd is None:
            # No lock (or not a regular file): released as before, nothing to mark.
            return False if recovering else self._release_guarded(swarm_dir, pinned) is True
        try:
            try:
                # A release waits for a recovery's check; a recovery never waits for a release.
                fcntl.flock(lock_fd, fcntl.LOCK_EX | (fcntl.LOCK_NB if recovering else 0))
            except BlockingIOError:
                logger.warning(
                    "⚠️ [SwarmBroker] A release of this swarm is running; recovery skipped: %s",
                    swarm_dir,
                )
                return False
            # The flock is on the file opened here: it must still be the swarm's lock.
            if _entry_identity_at(pinned, _LOCK_NAME) != _fd_identity(lock_fd):
                return False
            if recovering:
                if os.pread(lock_fd, len(_RELEASE_FAILED_MARK) + 1, 0) != _RELEASE_FAILED_MARK:
                    return False
                self._clear_stale_registration_lock(swarm_dir, stale_after)
            released = self._release_guarded(swarm_dir, pinned)
            if released is False:
                os.ftruncate(lock_fd, 0)
                os.pwrite(lock_fd, _RELEASE_FAILED_MARK, 0)
            return released is True
        except OSError as e:
            # Reading the mark, clearing the registration lock or writing the mark failed:
            # the swarm stays locked, as with any other failed release.
            logger.error(f"❌ [SwarmBroker] Lock handling failed for swarm {swarm_dir.name}: {e}")
            return False
        finally:
            os.close(lock_fd)

    def _release_guarded(self, swarm_dir: Path, pinned: int) -> Optional[bool]:
        """True when released, False when the swarm was left locked, None when its path was
        swapped (left untouched and not marked, for someone to look at)."""
        try:
            return self._release_pinned(swarm_dir, pinned)
        except _SwarmDirSwapped:
            logger.warning(
                "⚠️ [SwarmBroker] Swarm path was replaced during release; left untouched: %s",
                swarm_dir,
            )
            return None
        except Exception as e:
            logger.error(f"❌ [SwarmBroker] Error releasing swarm {swarm_dir.name}: {e}")
            return False

    def _clear_stale_registration_lock(self, swarm_dir: Path, stale_after: float) -> bool:
        """Remove an `index.lock` older than `stale_after` seconds from the swarm's own
        registration under the controller, relative to that opened directory.

        `hardened_git.clear_stale_index_lock` only clears a git dir inside the work tree, and a
        swarm's registration lies outside it. The age bound stands in for its running-git
        check: the hardened runner kills any git it started after GIT_TIMEOUT_S.
        """
        controller = self._controller_git_top_level()
        git_dir = linked_worktree_git_dir(swarm_dir, controller) if controller else None
        if git_dir is None:
            return False
        try:
            git_dir_fd = _open_real_dir(git_dir)
        except OSError:
            return False
        try:
            try:
                info = os.stat("index.lock", dir_fd=git_dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                return False
            if not stat.S_ISREG(info.st_mode) or time.time() - info.st_mtime < stale_after:
                return False
            _unlink_at(git_dir_fd, "index.lock")
        finally:
            os.close(git_dir_fd)
        logger.warning(
            "⚠️ [SwarmBroker] Removed a stale index.lock from the registration of %s", swarm_dir
        )
        return True

    def _release_pinned(self, swarm_dir: Path, pinned: int) -> bool:
        """Reset and unlock the swarm directory open at `pinned`; True once the lock is removed.

        Links and the lock are removed relative to `pinned`, so they come out of the directory
        that was opened whatever the path names by then. Git can only be given a path: the
        path is re-checked right before each git call and after the last one; the lock is kept
        whenever a check or a git call fails.
        """
        for cache_dir in _SHARED_CACHE_DIRS:
            _unlink_link_at(pinned, cache_dir)
        if not self.is_independently_registered_worktree(swarm_dir):
            _unlink_at(pinned, _LOCK_NAME)
            logger.warning("⚠️ [SwarmBroker] Refused to clean unregistered swarm placeholder: %s", swarm_dir)
            return True

        # 實施重用策略 (Reuse)
        if _entry_exists_at(pinned, ".git"):
            logger.debug(f"🐝 [SwarmBroker] Reusing git worktree in {swarm_dir.name}")
            if not self._reset_worktree(swarm_dir, pinned):
                return False
        else:
            # Fallback: clean up all contents except the lock file, relative to the opened
            # directory, so nothing is removed through a path swapped in meanwhile.
            for name in os.listdir(pinned):
                if name == _LOCK_NAME:
                    continue
                if not _names_dir(swarm_dir, pinned):
                    raise _SwarmDirSwapped(swarm_dir)
                info = os.stat(name, dir_fd=pinned, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    shutil.rmtree(name, dir_fd=pinned)
                else:
                    _unlink_at(pinned, name)

        # Finally remove the lock file to release it back to the pool
        if not _names_dir(swarm_dir, pinned):
            raise _SwarmDirSwapped(swarm_dir)
        _unlink_at(pinned, _LOCK_NAME)
        logger.debug(f"🐝 [SwarmBroker] Released and reset swarm sandbox: {swarm_dir.name}")
        return True

    def _reset_worktree(self, swarm_dir: Path, pinned: int) -> bool:
        """`git checkout` and `git clean` through the hardened runner, with the git dir pinned
        to the swarm's own registration under the controller; False leaves the swarm locked."""
        controller = self._controller_git_top_level()
        git_dir = linked_worktree_git_dir(swarm_dir, controller) if controller else None
        if git_dir is None:
            logger.warning(
                "⚠️ [SwarmBroker] Swarm git metadata does not name its registration; left locked: %s",
                swarm_dir,
            )
            return False
        if repository_config_can_start_a_program(swarm_dir, git_dir=git_dir):
            logger.warning(
                "⚠️ [SwarmBroker] Swarm repository config names a program; left locked: %s",
                swarm_dir,
            )
            return False
        # 快速重設 git 狀態; the lock stays until the reset has finished.
        for args in (("checkout", "--", "."), ("clean", "-f", "-d", "-e", f"/{_LOCK_NAME}")):
            if not _names_dir(swarm_dir, pinned):
                raise _SwarmDirSwapped(swarm_dir)
            result = run_hardened_git(swarm_dir, *args, git_dir=git_dir)
            if result.returncode != 0:
                logger.warning(
                    "⚠️ [SwarmBroker] git %s failed in %s; left locked: %s",
                    args[0],
                    swarm_dir,
                    result.stderr.strip(),
                )
                return False
        return True
