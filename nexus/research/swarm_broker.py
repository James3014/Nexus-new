import errno
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


def _copy_file_into(src: Path, parent_fd: int, name: str) -> None:
    # O_NONBLOCK: opening a FIFO with no writer would otherwise block; the type is checked on
    # the opened file, so an entry swapped after the directory scan is caught too.
    with open(os.open(src, _SOURCE_FILE_FLAGS), "rb") as fsrc:
        info = os.fstat(fsrc.fileno())
        if not stat.S_ISREG(info.st_mode):
            logger.warning(
                "⚠️ [SwarmBroker] Refused scope source that is not a regular file: %s", src
            )
            return
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
        elif entry.is_file(follow_symlinks=False):
            _copy_file_into(Path(entry.path), dst_fd, entry.name)
        else:
            logger.info(
                "[SwarmBroker] Skipped scope entry that is not a file or directory: %s", entry.path
            )


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

        start_time = time.time()
        while eligible_dirs and time.time() - start_time < timeout_sec:
            for entry in list(eligible_dirs):
                swarm_dir, identity = entry
                outcome = self._try_lock(swarm_dir, identity)
                if outcome is None:
                    eligible_dirs.remove(entry)
                elif outcome:
                    logger.debug(f"🐝 [SwarmBroker] Acquired swarm sandbox: {swarm_dir.name}")
                    return swarm_dir
            if eligible_dirs:
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
            self._release_pinned(swarm_dir, pinned)
        except _SwarmDirSwapped:
            logger.warning(
                "⚠️ [SwarmBroker] Swarm path was replaced during release; left untouched: %s",
                swarm_dir,
            )
        except Exception as e:
            logger.error(f"❌ [SwarmBroker] Error releasing swarm {swarm_dir.name}: {e}")
        finally:
            os.close(pinned)

    def _release_pinned(self, swarm_dir: Path, pinned: int) -> None:
        """Reset and unlock the swarm directory open at `pinned`.

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
            return

        # 實施重用策略 (Reuse)
        if _entry_exists_at(pinned, ".git"):
            logger.debug(f"🐝 [SwarmBroker] Reusing git worktree in {swarm_dir.name}")
            if not self._reset_worktree(swarm_dir, pinned):
                return
        else:
            # Fallback: Clean up all contents EXCEPT the lock file
            for item in swarm_dir.iterdir():
                if item.name == _LOCK_NAME:
                    continue
                if not _names_dir(swarm_dir, pinned):
                    raise _SwarmDirSwapped(swarm_dir)
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        # Finally remove the lock file to release it back to the pool
        if not _names_dir(swarm_dir, pinned):
            raise _SwarmDirSwapped(swarm_dir)
        _unlink_at(pinned, _LOCK_NAME)
        logger.debug(f"🐝 [SwarmBroker] Released and reset swarm sandbox: {swarm_dir.name}")

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
