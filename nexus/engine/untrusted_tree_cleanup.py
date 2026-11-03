"""Remove a directory tree that an untrusted command wrote to (#3238, #3281).

``shutil.rmtree`` is not enough for such a tree: before Python 3.14 it recurses once per
directory level (a deep tree raises ``RecursionError``), and a command can lock entries
(macOS user flags, mode 0, ACL entries) so the plain removal is refused. ``remove_untrusted_tree``
walks the tree iteratively with a bounded number of open descriptors, never follows a link,
makes locked entries removable, and removes it. A tree that still cannot be removed is set
aside under ``<path>.stale-<pid>`` and reported by raising ``UntrustedTreeNotRemoved``.
"""

from __future__ import annotations

import ctypes
import functools
import os
import secrets
import shutil
import stat
import struct
import sys

__all__ = ["UntrustedTreeNotRemoved", "remove_untrusted_tree", "remove_untrusted_tree_quietly"]

# setattrlistat(2) on macOS: set one attribute of the entry ``name`` in an open directory,
# never following a link there (FSOPT_NOFOLLOW).
_ATTR_BIT_MAP_COUNT = 5
_ATTR_CMN_FLAGS = 0x00040000
_ATTR_CMN_EXTENDED_SECURITY = 0x00400000
_FSOPT_NOFOLLOW = 0x1
_KAUTH_FILESEC_MAGIC = 0x012CC16D
_KAUTH_FILESEC_NOACL = 0xFFFFFFFF
_DIR_NOFOLLOW = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


@functools.cache
def _libc() -> ctypes.CDLL:
    return ctypes.CDLL(None, use_errno=True)


def _setattr_at(dir_fd: int, name: str, attribute: int, payload: bytes) -> None:
    attrlist = struct.pack("=HHIIIII", _ATTR_BIT_MAP_COUNT, 0, attribute, 0, 0, 0, 0)
    _libc().setattrlistat(  # result ignored: removal is retried and raises if still refused
        ctypes.c_int(dir_fd),
        os.fsencode(name),
        ctypes.create_string_buffer(attrlist, len(attrlist)),
        ctypes.create_string_buffer(payload, len(payload)),
        ctypes.c_size_t(len(payload)),
        ctypes.c_uint32(_FSOPT_NOFOLLOW),
    )


def _chmod_at_by_handle(dir_fd: int, name: str, mode: int) -> None:
    """chmod the entry itself through an ``O_PATH | O_NOFOLLOW`` handle (Linux); a link there
    is left alone."""

    o_path = getattr(os, "O_PATH", 0)
    if not o_path or not os.path.isdir("/proc/self/fd"):
        return
    try:
        fd = os.open(name, o_path | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
    except OSError:
        return
    try:
        if not stat.S_ISLNK(os.fstat(fd).st_mode):
            os.chmod(f"/proc/self/fd/{fd}", mode)
    except OSError:
        pass
    finally:
        os.close(fd)


def _make_removable_at(dir_fd: int, name: str, *, is_dir: bool) -> None:
    """Undo what a confined command may have set on the entry ``name`` of the open directory
    ``dir_fd`` so the host can delete it: user flags first (they block the rest), then the
    mode, then any ACL. Every change names the entry relative to ``dir_fd`` and never follows a
    link there: a link swapped in after the caller looked is changed itself, not its target."""

    if sys.platform == "darwin":
        _setattr_at(dir_fd, name, _ATTR_CMN_FLAGS, struct.pack("=I", 0))
    mode = 0o700 if is_dir else 0o600
    try:
        os.chmod(name, mode, dir_fd=dir_fd, follow_symlinks=False)
    except (NotImplementedError, ValueError):
        # Linux: no fchmodat without following; CPython raises one or the other.
        _chmod_at_by_handle(dir_fd, name, mode)
    except OSError:
        pass
    if sys.platform == "darwin":
        no_acl = struct.pack(
            "=I16s16sII", _KAUTH_FILESEC_MAGIC, bytes(16), bytes(16), _KAUTH_FILESEC_NOACL, 0
        )
        # attrreference_t (data right after it), then a filesec that says "no ACL".
        _setattr_at(
            dir_fd,
            name,
            _ATTR_CMN_EXTENDED_SECURITY,
            struct.pack("=iI", 8, len(no_acl)) + no_acl,
        )


# Most directory descriptors the removal walk holds open at once; a deeper subtree is moved up to
# the top and walked from there, so nesting depth never costs recursion or descriptors (#3238).
_WALK_MAX_OPEN = 128
# A deep subtree is renamed up to the top of the private area under a name no command could
# have planned for (a per-call token) with a few numbered retries past a taken name.
_MOVE_NAME_TRIES = 8


def _move_token() -> str:
    return secrets.token_hex(4)


def _move_name(token: str, n: int) -> str:
    return f".up-{token}-{n}"


def _make_tree_removable(dir_fd: int) -> None:
    """``_make_removable_at`` for every entry below the open directory ``dir_fd``, top down.
    Directories are entered only by ``O_NOFOLLOW`` opens relative to their parent's descriptor,
    so no path through a component swapped in during the walk is ever used (#3197). The walk is
    iterative and holds at most ``_WALK_MAX_OPEN`` descriptors: a subtree nested deeper is
    renamed up into ``dir_fd`` and walked from there (#3238)."""

    # Each frame: (descriptor, names still to visit). The first frame is the caller's own.
    stack: list[tuple[int, list[str]]] = []

    def frame(fd: int) -> tuple[int, list[str]]:
        with os.scandir(fd) as entries:
            return fd, [entry.name for entry in entries]

    stack.append(frame(dir_fd))
    moved = 0
    token = _move_token()
    try:
        while stack:
            fd, names = stack[-1]
            if not names:
                stack.pop()
                if fd != dir_fd:
                    os.close(fd)
                continue
            name = names.pop()
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode):
                continue
            is_dir = stat.S_ISDIR(info.st_mode)
            _make_removable_at(fd, name, is_dir=is_dir)
            if not is_dir:
                continue
            if len(stack) >= _WALK_MAX_OPEN and fd != dir_fd:
                up = None
                for _try in range(_MOVE_NAME_TRIES):
                    moved += 1
                    candidate = _move_name(token, moved)
                    try:
                        os.stat(candidate, dir_fd=dir_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        continue  # the command left something under that name: next number
                    try:
                        os.rename(name, candidate, src_dir_fd=fd, dst_dir_fd=dir_fd)
                    except OSError:
                        continue
                    up = candidate
                    break
                if up is None:
                    continue  # removal below reports it
                stack[0][1].append(up)
                continue
            try:
                child = os.open(name, _DIR_NOFOLLOW, dir_fd=fd)
            except OSError:
                continue  # now a link, or still unreadable: removal below reports it
            try:
                stack.append(frame(child))
            except OSError:
                os.close(child)
    finally:
        for fd, _ in stack:
            if fd != dir_fd:
                os.close(fd)


class UntrustedTreeNotRemoved(OSError):
    """The tree could not be removed. ``aside_name`` is the final component of the name it was
    set aside under (``<name>.stale-<pid>``), or its own name when even that failed; only names,
    never full paths, go into messages because they end up in receipts."""

    def __init__(self, aside_name: str) -> None:
        super().__init__(f"tree_not_removed:{aside_name}")
        self.aside_name = aside_name


def remove_untrusted_tree(path: str | os.PathLike[str]) -> None:
    """Remove ``path``, a tree an untrusted command may have written to. Entries the plain
    removal refuses (flags, mode or ACL entries) are made removable entry by entry, top down,
    by directory descriptor and without following any link, and removal is tried again. A tree
    that still cannot be removed is renamed to ``<path>.stale-<pid>`` and
    ``UntrustedTreeNotRemoved`` is raised. A path that does not exist is not an error."""

    private = os.fspath(path)
    if not os.path.lexists(private):
        return
    # Before 3.14 ``rmtree`` recurses once per directory level, so a very deep tree raises
    # RecursionError here even when nothing is locked; the walk below flattens it.
    try:
        shutil.rmtree(private)
        return
    except (OSError, RecursionError):
        pass
    try:
        parent = os.open(os.path.dirname(private) or ".", _DIR_NOFOLLOW)
        try:
            _make_removable_at(parent, os.path.basename(private), is_dir=True)
            root = os.open(os.path.basename(private), _DIR_NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)
        try:
            _make_tree_removable(root)
        finally:
            os.close(root)
        shutil.rmtree(private)
    except (OSError, RecursionError) as exc:
        # Do not leave it quietly under its own name: set it aside and say so (#3238).
        aside = f"{private}.stale-{os.getpid()}"
        try:
            os.rename(private, aside)
        except OSError:
            aside = private
        raise UntrustedTreeNotRemoved(os.path.basename(aside)) from exc


def remove_untrusted_tree_quietly(path: str | os.PathLike[str]) -> str | None:
    """``remove_untrusted_tree`` for callers that must not raise (cleanup in a ``finally`` of a
    best-effort path): returns ``None`` when the tree is gone, else the error text
    (``tree_not_removed:<name>``) for the caller to log or put in its result."""

    try:
        remove_untrusted_tree(path)
    except UntrustedTreeNotRemoved as exc:
        return str(exc)
    except (OSError, RecursionError) as exc:
        return f"tree_not_removed:{type(exc).__name__}"
    return None
