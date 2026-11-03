"""Run commands chosen or written by a local model inside an OS sandbox (#2936).

TacticalDrone's ``BASH`` action and the local_heal verifiers execute model output on the
host: a model-chosen command, or tests over a model-written patch. A ``cwd`` is not a
sandbox, so these runs go through ``sandbox-exec`` with the default-deny policy of
``nexus.engine.sandboxed_lane``:

* no network at all (``(deny network*)``), so cloud metadata and uploads are refused;
* writes only inside the work dir and a private ``home``/``tmp`` created for the run;
* reads limited to the work dir, the trusted interpreter, fixed system paths and the
  caller's ``readable`` roots; credential stores under ``$HOME`` (plus ``~/.config``,
  ``~/.local/state`` and the token stores in ``~/Library``) stay unreadable;
* an allowlisted environment (no tokens or provider keys) with ``HOME``/``TMPDIR`` in the
  private dir; ``extra_env`` is added on top by the caller.

Each writable root is bound when the call starts: a ``PinnedRoot`` work dir (a path with the
identity recorded for it) must still be that very directory at that path, checked in one
``lstat``. Once the profile is built, its write grants must name only the bound paths and each
root must still be the bound directory (#3197). Seatbelt grants by path, so a short window stays
between that last check and the start of the sandboxed process, and read grants are not checked
against the bound paths. The profile also keeps each
root's own ACL unchangeable, and after the run the host puts the root's own flags and mode back
as they were at the start (extended attributes are not restored); a root that is no longer the
bound directory then voids the run (``SandboxError``).

There is no unconfined fallback: without an OS barrier (non-macOS, or
``NEXUS_DISABLE_OS_SANDBOX=1``) ``SandboxError("no_os_barrier")`` is raised and nothing runs.
"""

from __future__ import annotations

import ctypes
import errno
import functools
import os
import re
import secrets
import shutil
import stat
import struct
import subprocess  # nosec B404 - argv lists only, never a shell
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from nexus.core.argv_command import (
    UnsupportedShellSyntax,
    run_command_string,
    run_reaping_process_group,
    split_command_chain,
)
from nexus.core.contained_write import HOST_RUN_SUBTREES, PinnedRoot
from nexus.engine.sandboxed_lane import (
    SANDBOX_EXEC,
    SBPL_SAFE_PATH,
    SandboxError,
    confinement,
    developer_toolchain_read_roots,
    in_tree,
    trusted_executable,
)

# Binaries here need no extra read root (system paths are already readable or not wanted).
_SYSTEM_PREFIXES = ("/usr/", "/bin/", "/sbin/", "/System/")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Under ``$HOME`` and holding tokens or session state, but not in sandboxed_lane's credential
# list (bot credentials live in ~/.config). Denied as whole subtrees by the profile's last rule,
# and a read root inside one is refused, whatever roots the caller grants.
_DENIED_HOME_SUBTREES = (
    ".config",
    ".local/state",
    "Library/Application Support",
    "Library/Cookies",
)

__all__ = [
    "SandboxError",
    "argument_file_roots",
    "denied_subtrees",
    "holds_host_code",
    "host_code_roots",
    "interpreter_readable_roots",
    "model_sandbox",
    "run_model_argv",
    "run_model_command_string",
]


def host_code_roots() -> tuple[Path, ...]:
    """Directories this host process imports Python from: the checkout or install holding the
    ``nexus`` package, and every directory on ``sys.path``. Model output may not be granted
    write access to one, to a directory containing one, or to an importable directory below
    one (``holds_host_code``): the host would later import, and run unconfined, what it wrote
    there."""

    roots = {Path(__file__).resolve().parents[2]}
    for entry in sys.path:
        if not entry:  # the empty entry imports from the current directory
            try:
                entry = os.getcwd()
            except OSError:
                continue
        if os.path.isdir(entry):
            roots.add(Path(entry).resolve())
    return tuple(sorted(roots))


def holds_host_code(path: Path | str) -> bool:
    """True when granting writes to directory ``path`` would let model output change code the
    host imports: ``path`` is or contains a ``host_code_roots`` entry, or lies below one along
    names that are all importable (``<root>/nexus/core`` is the package ``nexus.core``). A dir
    below a root through a name no import can reach, such as ``<checkout>/.nexus/…``, is not."""

    target = Path(path).resolve()
    for root in host_code_roots():
        if in_tree(root, (target,)):
            return True
        # Below the filesystem root (cwd "/" with an empty sys.path entry) every path qualifies
        # by this rule, e.g. /tmp/tmpab12_x; only containing "/" itself counts there (#3023).
        if root.parent == root:
            continue
        if target.is_relative_to(root) and all(
            part.isidentifier() for part in target.relative_to(root).parts
        ):
            return True
        # On a case-insensitive filesystem (macOS default) ``<root>/NEXUS/core`` is the package
        # ``nexus.core`` too. Compare case-folded on every filesystem: a false hit needs two
        # directories that differ only by case and it only refuses a grant (#3099).
        folded_root = Path(str(root).casefold())
        folded_target = Path(str(target).casefold())
        if folded_target == folded_root or folded_target in folded_root.parents:
            return True
        if folded_target.is_relative_to(folded_root) and all(
            part.isidentifier() for part in folded_target.relative_to(folded_root).parts
        ):
            return True
    return False


def denied_subtrees() -> tuple[Path, ...]:
    """The ``$HOME`` subtrees model output may never read, resolved against the current home.
    local_heal keeps its work dirs out of them: a read root inside one is refused (#2966)."""

    home = Path(os.path.expanduser("~")).resolve()
    return tuple(home / rel for rel in _DENIED_HOME_SUBTREES)


def interpreter_readable_roots(executable: str, *, allow_absolute: bool = True) -> list[Path]:
    """Read-only roots the command's own interpreter needs to start (#2936).

    ``executable`` is looked up on PATH when it is a bare name. For ``<venv>/bin/<tool>`` the
    venv and the base installation named by its ``pyvenv.cfg`` ``home`` are added; for a Python
    interpreter whose real path is ``<prefix>/bin/python*`` outside the system trees,
    ``<prefix>`` (e.g. a Homebrew ``python3`` and its framework). These roots are read-only;
    ``confinement`` still refuses any that is or contains ``$HOME``, ``/Users`` or a temp root.

    ``allow_absolute=False`` is for model-chosen commands: only a bare name resolved on the
    trusted PATH may widen reads, never a path the model wrote."""

    if os.path.isabs(executable):
        found = executable if allow_absolute else None
    elif os.sep in executable:
        found = None
    else:
        found = shutil.which(executable)
    if not found or not os.path.isfile(found):
        return []
    path = Path(found)
    roots: list[Path] = []
    venv = path.parent.parent
    cfg = venv / "pyvenv.cfg"
    if path.parent.name == "bin" and cfg.is_file():
        roots.append(venv.resolve())
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "home" and value.strip():
                roots.append(Path(value.strip()).resolve().parent)
    real = path.resolve()
    if (
        real.name.startswith("python")
        and real.parent.name == "bin"
        and not str(real).startswith(_SYSTEM_PREFIXES)
    ):
        roots.append(real.parent.parent)
    return list(dict.fromkeys(roots))


def argument_file_roots(argv: Iterable[str]) -> list[Path]:
    """Read-only grants for the existing regular files a trusted verifier command names by
    absolute path (an oracle or verify script kept outside the work dir): the files only, never
    their directories. Not for model-chosen commands."""

    roots = [
        Path(arg).resolve() for arg in list(argv)[1:] if os.path.isabs(arg) and os.path.isfile(arg)
    ]
    return list(dict.fromkeys(roots))


def _sandbox_which(program: str, work_dir: Path, writable: Iterable[Path] = ()) -> str:
    """Absolute path of a bare ``program`` as the sandboxed run finds it: on this process's
    PATH without the entries inside the work dir or another writable root (``scrubbed_env``
    drops them). Granting reads for a host lookup that kept them could name a different
    interpreter than the one that starts, which then cannot load (exit -6, #2970)."""

    try:
        return trusted_executable(program, untrusted_roots=(work_dir, *writable))
    except SandboxError:
        return ""


def _command_readable_roots(command: str, work_dir: Path) -> list[Path]:
    """``interpreter_readable_roots`` for the program of every ``&&`` segment of ``command``.
    Only a bare name, resolved as the sandbox resolves it, widens reads; a path the model wrote
    never does."""

    try:
        segments = split_command_chain(command)
    except UnsupportedShellSyntax:
        return []  # run_command_string refuses it before anything runs
    roots: list[Path] = []
    for words in segments:
        program = next((word for word in words if not _ASSIGNMENT.match(word)), None)
        if program and os.sep not in program:
            found = _sandbox_which(program, work_dir)
            if found:
                roots.extend(interpreter_readable_roots(found))
    return list(dict.fromkeys(roots))


def _root_entry(path: Path) -> os.stat_result | None:
    """``lstat`` of ``path`` when it names a directory itself and resolves to itself."""

    try:
        if os.path.realpath(path) != str(path):
            return None
        info = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    return info if stat.S_ISDIR(info.st_mode) else None


def _same_dir(info: os.stat_result | None, recorded: os.stat_result) -> bool:
    return info is not None and (info.st_dev, info.st_ino) == (recorded.st_dev, recorded.st_ino)


def _bind_root(root: Path | str | PinnedRoot, reason: str) -> tuple[Path, os.stat_result]:
    """The path to grant for ``root`` and the root's entry as it is now.

    A ``PinnedRoot`` is taken as given (it must already resolve to itself) and must still be
    the directory recorded for it: path and identity are checked in one ``lstat``, never by
    resolving the path first and checking whatever that names (#3197)."""

    if isinstance(root, PinnedRoot):
        path = Path(os.fspath(root))
        info = _root_entry(path) if path.is_absolute() else None
        if info is None or (info.st_dev, info.st_ino) != tuple(root.identity):
            raise SandboxError(f"{reason}_replaced")
        return path, info
    path = Path(root).resolve()
    info = _root_entry(path)
    if info is None:
        raise SandboxError(f"{reason}_missing")
    return path, info


def _restore_root_metadata(path: Path, recorded: os.stat_result) -> bool:
    """Put the root's own flags and mode back as recorded; False when ``path`` is no
    longer that directory or they cannot be restored. A confined command may change them (the
    profile only keeps the entry itself in place, #3177), which would make later host reads,
    git calls or cleanup of the root fail."""

    info = _root_entry(path)
    if info is None or not _same_dir(info, recorded):
        return False
    try:
        flags = getattr(recorded, "st_flags", None)
        if flags is not None and getattr(info, "st_flags", flags) != flags:
            chflags = getattr(os, "chflags", None)  # BSD/macOS only
            if chflags is None:
                return False
            chflags(path, flags, follow_symlinks=False)  # first: uchg also blocks chmod
        if stat.S_IMODE(info.st_mode) != stat.S_IMODE(recorded.st_mode):
            no_follow = os.chmod in os.supports_follow_symlinks
            os.chmod(path, stat.S_IMODE(recorded.st_mode), follow_symlinks=not no_follow)
    except OSError:
        return False
    return _same_dir(_root_entry(path), recorded)


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


def _remove_private_dir(private: str) -> None:
    """Remove the run's private ``home``/``tmp``. Model code wrote there and may have left
    entries the plain removal refuses (flags, mode or ACL entries); those are made removable
    entry by entry, top down, by directory descriptor and without following any link, and
    removal is tried again. A dir that still cannot be removed raises."""

    try:
        shutil.rmtree(private)
        return
    except OSError:
        pass
    parent = os.open(os.path.dirname(private), _DIR_NOFOLLOW)
    try:
        _make_removable_at(parent, os.path.basename(private), is_dir=True)
        root = os.open(os.path.basename(private), _DIR_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        _make_tree_removable(root)
    finally:
        os.close(root)
    try:
        shutil.rmtree(private)
    except OSError as exc:
        # Do not leave it quietly under its own name: set it aside and say so (#3238). Only
        # the name goes into the error: it ends up in receipts.
        aside = f"{private}.stale-{os.getpid()}"
        try:
            os.rename(private, aside)
        except OSError:
            aside = private
        raise SandboxError(f"private_area_not_removed:{os.path.basename(aside)}") from exc


# The device files every profile lets a command write besides its roots.
_DEVICE_WRITES = frozenset({"/dev/null", "/dev/tty", "/dev/dtracehelper"})
_WRITE_GRANT = re.compile(r'\(allow file-write\S*((?: \((?:subpath|literal) "[^"]*"\))+)\)')
_PINNED_ENTRY = re.compile(r'\(deny file-write-unlink file-write-create \(literal "([^"]*)"\)\)')


def _writes_stay_bound(profile: str, bound: Iterable[Path]) -> bool:
    """True when every write grant in ``profile`` and every pinned entry names only a bound
    root (or a device file). The profile resolves the roots once more while it is built: a
    link swapped in only then would name its target here (#3197)."""

    roots = {str(path) for path in bound}
    for line in profile.splitlines():
        if line.startswith("(allow file-write"):
            grant = _WRITE_GRANT.fullmatch(line)
            if grant is None:
                return False
            if not set(re.findall(r'"([^"]*)"', grant.group(1))) <= roots | _DEVICE_WRITES:
                return False
        elif line.startswith("(deny file-write-unlink"):
            pinned = _PINNED_ENTRY.fullmatch(line)
            if pinned is None or pinned.group(1) not in roots:
                return False
    return True


def _granted_work_dir(work_dir: Path | str | PinnedRoot) -> Path:
    """The work dir path ``model_sandbox`` grants: a ``PinnedRoot`` as given (it checks that the
    path resolves to itself and is the recorded directory), any other path resolved."""

    if isinstance(work_dir, PinnedRoot):
        return Path(os.fspath(work_dir))
    return Path(work_dir).resolve()


@contextmanager
def model_sandbox(
    work_dir: Path | str | PinnedRoot,
    *,
    readable: Iterable[Path | str] = (),
    writable: Iterable[Path | str] = (),
) -> Iterator[tuple[list[str], dict[str, str]]]:
    """Yield ``(argv_prefix, env)`` for commands confined to ``work_dir``.

    Prepend ``argv_prefix`` to each argv and run it with ``env``. ``writable`` adds existing
    directories the caller created for the run (e.g. a result-record dir); they get the same
    root checks as ``work_dir``. A ``PinnedRoot`` work dir must still be its recorded directory
    (``SandboxError("work_dir_replaced")`` otherwise). When the block ends, each root's own flags
    and mode are put back (its extended attributes are not); a root that is no longer the bound
    directory raises ``SandboxError(…_replaced)``. Raises SandboxError when no OS barrier exists
    or a root is unsafe (fail closed)."""

    work, work_info = _bind_root(work_dir, "work_dir")
    bound_extra = [_bind_root(path, "writable_dir") for path in writable]
    extra = tuple(path for path, _ in bound_extra)
    # Checked before the barrier, so it fails the same way on every host.
    if any(holds_host_code(path) for path in (work, *extra)):
        raise SandboxError("work_dir_holds_host_code")
    # The host runs git and the task interpreter in work_dir after the model's command (#2945):
    # a planted hook, git config (core.fsmonitor, diff.external) or venv file would run there,
    # unconfined. Both the path and, for a symlink, its target stay unwritable.
    read_only = sorted({
        str(path) for name in HOST_RUN_SUBTREES for path in (work / name, (work / name).resolve())
    })
    if not all(SBPL_SAFE_PATH.fullmatch(path) for path in read_only):
        raise SandboxError("sandbox_path_unsafe")
    roots = [(work, work_info, "work_dir"), *((p, i, "writable_dir") for p, i in bound_extra)]
    private = tempfile.mkdtemp(prefix="nexus-model-exec-")
    try:
        bound = confinement(
            sandbox=Path(private).resolve(),
            extra_writable=(work, *extra),
            # /usr/bin/python3, git, make… are xcrun shims that load the active developer dir.
            extra_readable=(*readable, *developer_toolchain_read_roots()),
            forbidden_subtrees=denied_subtrees(),
            read_only_paths=read_only,
            # Model output never runs host code; its interpreter is granted via ``readable``. The
            # Gateway venv sits under a denied subtree, so granting it refused every run (#2956).
            host_interpreter_readable=False,
        )
        # confinement() and its profile resolved each root again: both must name only the bound
        # paths, and each root must still be the bound directory after that (#3197).
        if tuple(bound.roots[1:]) != (work, *extra):
            raise SandboxError("work_dir_replaced")
        if not _writes_stay_bound(bound.profile, (bound.roots[0], work, *extra)):
            raise SandboxError("work_dir_replaced")
        for path, info, reason in roots:
            if not _same_dir(_root_entry(path), info):
                raise SandboxError(f"{reason}_replaced")
        # A root's ACL is the one part of its own metadata the host cannot easily read back:
        # it stays as it is (each path is a granted one, so SBPL-safe). cp -p and archives
        # extracting ./ into the root still work (#3197).
        profile = "\n".join([
            bound.profile,
            *(f'(deny file-write-acl (literal "{path}"))' for path, _, _ in roots),
        ])
        try:
            yield [SANDBOX_EXEC, "-p", profile], dict(bound.env)
        finally:
            unbound = [r for path, info, r in roots if not _restore_root_metadata(path, info)]
        if unbound:
            raise SandboxError(f"{unbound[0]}_replaced")
    finally:
        _remove_private_dir(private)


def run_model_argv(
    argv: list[str] | tuple[str, ...],
    *,
    work_dir: Path | str | PinnedRoot,
    timeout: float,
    extra_env: Mapping[str, str] | None = None,
    readable: Iterable[Path | str] = (),
    writable: Iterable[Path | str] = (),
    text: bool = True,
) -> subprocess.CompletedProcess:
    """``subprocess.run(argv, cwd=work_dir)`` inside the model sandbox (no shell), its process
    group killed afterwards.

    ``subprocess.TimeoutExpired`` propagates; SandboxError means nothing ran. A program that
    does not exist raises FileNotFoundError, as ``subprocess.run`` would, rather than surfacing
    as sandbox-exec's own exit status."""

    if not argv:
        raise SandboxError("empty_command")
    program = argv[0]
    writable = tuple(Path(path).resolve() for path in writable)
    command = list(argv)
    grant: list[Path] = []
    if os.sep in program:
        found = program if os.path.isabs(program) else str(Path(work_dir) / program)
    else:
        # Resolved once, as the sandboxed run would, and run by that path, so the read grant
        # names the interpreter that actually starts (#2970).
        found = _sandbox_which(program, Path(work_dir).resolve(), writable)
        if found:
            command[0] = found
            grant = interpreter_readable_roots(found)
    with model_sandbox(work_dir, readable=(*readable, *grant), writable=writable) as (prefix, env):
        run_env = {**env, **(extra_env or {})}
        # Raised after the barrier check, so a missing barrier is reported first.
        if not found or not os.path.exists(found):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), program)
        # Nothing the command started outlives it in its process group (#3017).
        return run_reaping_process_group(
            [*prefix, *command],
            cwd=str(_granted_work_dir(work_dir)),
            env=run_env,
            capture_output=True,
            text=text,
            timeout=timeout,
        )


def run_model_command_string(
    command: str, *, work_dir: Path | str | PinnedRoot, timeout: float
) -> subprocess.CompletedProcess[str]:
    """``run_command_string`` (no shell, ``&&`` chains only) with every segment confined, in
    the work dir path the sandbox granted."""

    readable = _command_readable_roots(command, Path(work_dir).resolve())
    with model_sandbox(work_dir, readable=readable) as (prefix, env):
        return run_command_string(
            command,
            cwd=_granted_work_dir(work_dir),
            env=env,
            timeout=timeout,
            argv_prefix=prefix,
            reap_process_group=True,
        )
