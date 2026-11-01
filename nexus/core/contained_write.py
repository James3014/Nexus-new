"""Host-side reads and writes of files inside a directory that model output can also write.

local_heal applies model patches to, and writes repro scripts into, a work dir in which
sandboxed model code may already have run; the drone writes model-chosen files into its sandbox
dir. A plain ``path.write_text`` follows whatever is there by then: a symlink or a hard link to a
host file, a FIFO that blocks forever, or a path the model wrote as absolute or with ``..``.

These helpers walk to the file relative to ``root`` one component at a time with ``O_NOFOLLOW``,
so no link swapped in after a check is followed. A write never opens the existing file: it fills
a new file created in the same directory and renames it over the name, which replaces the
directory entry and leaves whatever inode was there untouched (a hard link to a host file, made
or unlinked at any moment, is never written through). An existing entry that is not a regular
single-link file is refused up front, and reads accept only such a file. A write into a
directory the host itself runs from later (``HOST_RUN_SUBTREES``) is refused too. A refusal
raises ``PathContainmentError`` (an ``OSError``) and nothing is written.
"""

from __future__ import annotations

import errno
import os
import secrets
import shutil
import stat
import unicodedata
from pathlib import Path, PurePath

__all__ = [
    "HOST_RUN_SUBTREES",
    "PathContainmentError",
    "contained_relative_path",
    "copy_file_in_root",
    "copy_tree_in_root",
    "read_bytes_in_root",
    "read_text_in_root",
    "write_text_in_root",
]

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
# Work-dir entries the host itself runs from after model code has run there (#2945): git reads
# its config and hooks from .git, and the task interpreter starts from .venv. The model sandbox
# keeps them read-only, and model-driven writes here refuse them at any depth (#3024).
HOST_RUN_SUBTREES = (".git", ".venv")


class PathContainmentError(OSError):
    """The path leaves the root, crosses a link, or is not a regular single-link file."""


def contained_relative_path(root: Path | str, path: Path | str) -> PurePath:
    """``path`` (relative to ``root``, or absolute) as a relative path inside ``root``.

    Symlinks that exist now are resolved; the result must lie inside ``root``'s real path.
    Raises PathContainmentError otherwise."""

    root_real = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(root) / candidate
    real = candidate.resolve()
    if real == root_real or not real.is_relative_to(root_real):
        raise PathContainmentError(f"path_outside_root:{path}")
    return real.relative_to(root_real)


def _parts(relative: PurePath | str) -> tuple[str, ...]:
    text = os.fspath(relative)
    if not text or "\x00" in text:
        raise PathContainmentError(f"path_invalid:{text!r}")
    parts = PurePath(text).parts
    if PurePath(text).is_absolute() or not parts or any(p in ("", ".", "..") for p in parts):
        raise PathContainmentError(f"path_not_relative:{text}")
    return parts


def _is_host_run_name(name: str) -> bool:
    # APFS and HFS+ match names without case, and HFS+ also skips format characters (U+200C…).
    folded = "".join(c for c in name if unicodedata.category(c) != "Cf").casefold()
    return folded in HOST_RUN_SUBTREES


def _open_parent(root: Path | str, parts: tuple[str, ...], *, create_parents: bool) -> int:
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for name in parts[:-1]:
            if create_parents:
                try:
                    os.mkdir(name, 0o777, dir_fd=fd)
                except FileExistsError:
                    pass
            try:
                next_fd = os.open(name, _DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                raise PathContainmentError(f"path_component_refused:{name}:{exc}") from exc
            os.close(fd)
            fd = next_fd
    except BaseException:
        os.close(fd)
        raise
    return fd


def _check_regular(fd: int, name: str) -> None:
    _check_regular_info(os.fstat(fd), name)


def _check_regular_info(info: os.stat_result, name: str) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise PathContainmentError(f"not_a_regular_file:{name}")
    if info.st_nlink != 1:
        raise PathContainmentError(f"file_has_other_links:{name}")


def write_text_in_root(
    root: Path | str,
    relative: PurePath | str,
    text: str,
    *,
    create_parents: bool = False,
) -> None:
    """Write ``text`` (UTF-8) to ``root/relative``, created if missing, never through a link.

    The text goes to a new file in the same directory, which is then renamed over the name; an
    existing regular file keeps its permission bits, a new one gets 0o666 less the umask."""

    parts = _parts(relative)
    if any(_is_host_run_name(part) for part in parts):
        raise PathContainmentError(f"path_in_host_run_subtree:{os.fspath(relative)}")
    name = parts[-1]
    parent = _open_parent(root, parts, create_parents=create_parents)
    try:
        try:
            existing = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise PathContainmentError(f"file_stat_refused:{name}:{exc}") from exc
        if existing is not None:
            _check_regular_info(existing, name)
        temp = f".nexus-write-{secrets.token_hex(8)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = os.open(temp, flags, 0o666, dir_fd=parent)  # umask applies, as for a plain create
        except OSError as exc:
            raise PathContainmentError(f"file_open_refused:{name}:{exc}") from exc
        try:
            try:
                data = memoryview(text.encode("utf-8"))
                while data:
                    data = data[os.write(fd, data) :]
                if existing is not None:
                    os.fchmod(fd, stat.S_IMODE(existing.st_mode) & 0o777)
            finally:
                os.close(fd)
            try:
                os.rename(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
            except OSError as exc:
                raise PathContainmentError(f"file_replace_refused:{name}:{exc}") from exc
        except BaseException:
            try:
                os.unlink(temp, dir_fd=parent)
            except OSError:
                pass
            raise
    finally:
        os.close(parent)


def read_bytes_in_root(
    root: Path | str, relative: PurePath | str, *, max_bytes: int | None = None
) -> bytes:
    """Read the bytes of ``root/relative``, never through a link.

    With ``max_bytes``, a file larger than that raises ``PathContainmentError`` and is not read
    beyond ``max_bytes + 1`` bytes (it may still be growing)."""

    parts = _parts(relative)
    parent = _open_parent(root, parts, create_parents=False)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        try:
            fd = os.open(parts[-1], flags, dir_fd=parent)
        except OSError as exc:
            raise PathContainmentError(f"file_open_refused:{parts[-1]}:{exc}") from exc
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        _check_regular_info(info, parts[-1])
        if max_bytes is not None and info.st_size > max_bytes:
            raise PathContainmentError(f"file_too_large:{parts[-1]}:{info.st_size}")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
        if max_bytes is not None and len(data) > max_bytes:
            raise PathContainmentError(f"file_too_large:{parts[-1]}:{len(data)}")
        return data
    finally:
        os.close(fd)


def read_text_in_root(
    root: Path | str,
    relative: PurePath | str,
    *,
    max_bytes: int | None = None,
    strict: bool = False,
) -> str:
    """Read ``root/relative`` as UTF-8 (undecodable bytes replaced), never through a link.

    With ``strict=True`` content that is not UTF-8 raises ``PathContainmentError`` with
    ``not_utf8:<name>`` instead, so a caller that rewrites the file cannot change bytes it never
    saw. The default stays lenient: callers such as local_model_executor snapshot and hash
    whatever is there and look for U+FFFD themselves (#3099).

    With ``max_bytes``, a file larger than that raises ``PathContainmentError`` and is not read
    beyond ``max_bytes + 1`` bytes (it may still be growing)."""

    data = read_bytes_in_root(root, relative, max_bytes=max_bytes)
    if not strict:
        return data.decode("utf-8", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PathContainmentError(f"not_utf8:{PurePath(relative).name}") from exc


def _copy_open_file(src_fd: int, info: os.stat_result, destination: Path) -> None:
    """Copy the already checked open file ``src_fd`` to a new ``destination`` (mode, times)."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    dst_fd = os.open(destination, flags, 0o600)
    try:
        with (
            os.fdopen(src_fd, "rb", closefd=False) as source,
            os.fdopen(dst_fd, "wb", closefd=False) as target,
        ):
            shutil.copyfileobj(source, target)
        os.fchmod(dst_fd, stat.S_IMODE(info.st_mode) & 0o777)
    finally:
        os.close(dst_fd)
    os.utime(destination, ns=(info.st_atime_ns, info.st_mtime_ns), follow_symlinks=False)


def _open_regular(name: str, dir_fd: int) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise PathContainmentError(f"file_open_refused:{name}:{exc}") from exc
    try:
        info = os.fstat(fd)
        _check_regular_info(info, name)
    except BaseException:
        os.close(fd)
        raise
    return fd, info


def _names_nothing(error: BaseException | None) -> bool:
    """The path cannot name an existing entry: missing, or a component too long to exist."""

    return isinstance(error, FileNotFoundError) or (
        isinstance(error, OSError) and error.errno == errno.ENAMETOOLONG
    )


def copy_file_in_root(src_root: Path | str, relative: PurePath | str, dst_root: Path | str) -> bool:
    """Copy ``src_root/relative`` to ``dst_root/relative``, never reading through a link.

    Only a regular single-link file is copied (the same rule as ``read_text_in_root``); a link at
    the file or on the way to it, a hard link and a FIFO or other special file raise
    ``PathContainmentError`` and nothing is copied. Returns False when the file does not exist,
    including a name too long to exist (ENAMETOOLONG).
    ``dst_root`` is a fresh directory only the host writes; missing parents are created there."""

    parts = _parts(relative)
    try:
        parent = _open_parent(src_root, parts, create_parents=False)
    except PathContainmentError as exc:
        if _names_nothing(exc.__cause__):
            return False
        raise
    try:
        try:
            fd, info = _open_regular(parts[-1], parent)
        except FileNotFoundError:
            return False
        except PathContainmentError as exc:
            if _names_nothing(exc.__cause__):
                return False
            raise
    finally:
        os.close(parent)
    try:
        destination = Path(dst_root).joinpath(*parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_open_file(fd, info, destination)
    finally:
        os.close(fd)
    return True


def copy_tree_in_root(
    src_root: Path | str,
    dst_root: Path | str,
    *,
    ignore_names: frozenset[str] | set[str] = frozenset(),
) -> tuple[str, ...]:
    """Copy the tree under ``src_root`` into the existing directory ``dst_root``, link-safe.

    Directories are walked by descriptor with ``O_NOFOLLOW``, so no file outside ``src_root`` is
    read. Regular single-link files are copied; a hard link, FIFO, socket or device raises
    ``PathContainmentError`` and the caller must treat the copy as failed. A symlink is recreated
    as a link only if it resolves inside ``dst_root`` once everything is copied; any other
    symlink is left out. Entries named in ``ignore_names`` are skipped at every depth, under any
    letter case (``.Git`` is ``.git`` on a case-insensitive file system). Returns the relative
    paths of the symlinks left out."""

    dst_path = Path(dst_root)
    ignored = {name.casefold() for name in ignore_names}
    links: list[tuple[PurePath, str]] = []

    def walk(src_fd: int, relative: PurePath) -> None:
        with os.scandir(src_fd) as entries:
            names = sorted(entry.name for entry in entries)
        for name in names:
            if name.casefold() in ignored:
                continue
            child = relative / name
            info = os.stat(name, dir_fd=src_fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                links.append((child, os.readlink(name, dir_fd=src_fd)))
            elif stat.S_ISDIR(info.st_mode):
                try:
                    child_fd = os.open(name, _DIR_FLAGS, dir_fd=src_fd)
                except OSError as exc:
                    raise PathContainmentError(f"path_component_refused:{child}:{exc}") from exc
                try:
                    (dst_path / child).mkdir(exist_ok=True)
                    walk(child_fd, child)
                finally:
                    os.close(child_fd)
            else:
                try:
                    fd, opened = _open_regular(name, src_fd)
                except FileNotFoundError:
                    continue
                except PathContainmentError as exc:
                    raise PathContainmentError(f"{exc}:{child}") from exc
                try:
                    _copy_open_file(fd, opened, dst_path / child)
                finally:
                    os.close(fd)

    root_fd = os.open(src_root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        walk(root_fd, PurePath())
    finally:
        os.close(root_fd)

    for child, target in links:
        os.symlink(target, dst_path / child)
    dst_real = dst_path.resolve()
    dropped: list[str] = []
    for child, _target in links:
        link = dst_path / child
        real = Path(os.path.realpath(link))
        if real != dst_real and not real.is_relative_to(dst_real):
            link.unlink()
            dropped.append(os.fspath(child))
    return tuple(dropped)
