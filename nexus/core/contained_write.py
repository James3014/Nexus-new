"""Host-side reads and writes of files inside a directory that model output can also write.

local_heal applies model patches to, and writes repro scripts into, a work dir in which
sandboxed model code may already have run; the drone writes model-chosen files into its sandbox
dir. A plain ``path.write_text`` follows whatever is there by then: a symlink or a hard link to a
host file, a FIFO that blocks forever, or a path the model wrote as absolute or with ``..``.

These helpers open the file relative to ``root`` one component at a time with ``O_NOFOLLOW``,
so no link swapped in after a check is followed, and accept only a regular file with a single
link. A refusal raises ``PathContainmentError`` (an ``OSError``) and nothing is written.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePath

__all__ = [
    "PathContainmentError",
    "contained_relative_path",
    "read_text_in_root",
    "write_text_in_root",
]

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


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
    info = os.fstat(fd)
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
    """Write ``text`` (UTF-8) to ``root/relative``, created if missing, never through a link."""

    parts = _parts(relative)
    parent = _open_parent(root, parts, create_parents=create_parents)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        try:
            fd = os.open(parts[-1], flags, 0o644, dir_fd=parent)
        except OSError as exc:
            raise PathContainmentError(f"file_open_refused:{parts[-1]}:{exc}") from exc
    finally:
        os.close(parent)
    try:
        _check_regular(fd, parts[-1])
        os.ftruncate(fd, 0)
        data = memoryview(text.encode("utf-8"))
        while data:
            data = data[os.write(fd, data) :]
    finally:
        os.close(fd)


def read_text_in_root(root: Path | str, relative: PurePath | str) -> str:
    """Read ``root/relative`` as UTF-8 (undecodable bytes replaced), never through a link."""

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
        _check_regular(fd, parts[-1])
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read().decode("utf-8", errors="replace")
    finally:
        os.close(fd)
