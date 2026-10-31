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

There is no unconfined fallback: without an OS barrier (non-macOS, or
``NEXUS_DISABLE_OS_SANDBOX=1``) ``SandboxError("no_os_barrier")`` is raised and nothing runs.
"""

from __future__ import annotations

import errno
import os
import re
import shutil
import subprocess  # nosec B404 - argv lists only, never a shell
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from nexus.core.argv_command import (
    UnsupportedShellSyntax,
    run_command_string,
    split_command_chain,
)
from nexus.core.contained_write import HOST_RUN_SUBTREES
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


@contextmanager
def model_sandbox(
    work_dir: Path | str,
    *,
    readable: Iterable[Path | str] = (),
    writable: Iterable[Path | str] = (),
) -> Iterator[tuple[list[str], dict[str, str]]]:
    """Yield ``(argv_prefix, env)`` for commands confined to ``work_dir``.

    Prepend ``argv_prefix`` to each argv and run it with ``env``. ``writable`` adds existing
    directories the caller created for the run (e.g. a result-record dir); they get the same
    root checks as ``work_dir``. Raises SandboxError when no OS barrier exists or a root is
    unsafe (fail closed)."""

    work = Path(work_dir).resolve()
    if not work.is_dir():
        raise SandboxError("work_dir_missing")
    extra = tuple(Path(path).resolve() for path in writable)
    if not all(path.is_dir() for path in extra):
        raise SandboxError("writable_dir_missing")
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
    with tempfile.TemporaryDirectory(prefix="nexus-model-exec-") as private:
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
        yield [SANDBOX_EXEC, "-p", bound.profile], dict(bound.env)


def run_model_argv(
    argv: list[str] | tuple[str, ...],
    *,
    work_dir: Path | str,
    timeout: float,
    extra_env: Mapping[str, str] | None = None,
    readable: Iterable[Path | str] = (),
    writable: Iterable[Path | str] = (),
    text: bool = True,
) -> subprocess.CompletedProcess:
    """``subprocess.run(argv, cwd=work_dir)`` inside the model sandbox (no shell).

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
        return subprocess.run(  # noqa: S603 - argv list, no shell
            [*prefix, *command],
            cwd=str(Path(work_dir).resolve()),
            env=run_env,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=False,
        )


def run_model_command_string(
    command: str, *, work_dir: Path | str, timeout: float
) -> subprocess.CompletedProcess[str]:
    """``run_command_string`` (no shell, ``&&`` chains only) with every segment confined."""

    readable = _command_readable_roots(command, Path(work_dir).resolve())
    with model_sandbox(work_dir, readable=readable) as (prefix, env):
        return run_command_string(
            command, cwd=Path(work_dir).resolve(), env=env, timeout=timeout, argv_prefix=prefix
        )
