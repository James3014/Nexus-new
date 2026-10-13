"""Shared executable/argv policy for governed no-shell CLI spawns (#1752, #1753).

Program identity is judged on both the name as given and the name of the
resolved real file, so renamed symlinks cannot dodge the rules.  Forwarders
(programs that run another program or a shell) are rejected outright; ``git``
and ``gh`` are allowlisted to read/stage-only forms; ``find`` loses its
command-executing and file-writing actions.
"""

from __future__ import annotations

import os
import subprocess
from typing import Iterable, Mapping, Sequence

FORWARDER_NAMES = frozenset(
    """sh bash zsh dash ash ksh csh tcsh fish busybox toybox env xargs nohup setsid
    timeout gtimeout command exec nice ionice time stdbuf unbuffer chrt taskset flock
    script watch sudo doas su runuser chroot caffeinate arch sandbox-exec osascript
    launchctl at batch parallel entr strace ltrace dtruss gdb lldb valgrind""".split()
)

GIT_ALLOWED_SUBCOMMANDS = frozenset(
    """status diff log show ls-files ls-tree rev-parse rev-list cat-file grep blame
    describe show-ref merge-base name-rev shortlog add rm mv restore apply
    check-ignore check-attr version""".split()
)
_GIT_FLAG_GLOBALS = frozenset({
    "--no-pager",
    "-P",
    "--no-optional-locks",
    "--literal-pathspecs",
    "--no-replace-objects",
})
_GIT_FORBIDDEN_ANYWHERE_PREFIXES = (
    "-O",
    "--open-files-in-pager",
    "--ext-diff",
    "--textconv",
    "--show-signature",
    "--upload-pack",
    "--receive-pack",
    "--exec",
)

_GH_GLOBAL_WITH_VALUE = frozenset({"--repo", "-R", "--hostname"})
_GH_ALLOWED = frozenset({
    ("pr", "view"),
    ("pr", "list"),
    ("pr", "diff"),
    ("pr", "checks"),
    ("pr", "status"),
    ("issue", "view"),
    ("issue", "list"),
    ("issue", "status"),
    ("repo", "view"),
    ("run", "view"),
    ("run", "list"),
})

FIND_FORBIDDEN_ARGS = frozenset({
    "-exec",
    "-execdir",
    "-ok",
    "-okdir",
    "-delete",
    "-fprint",
    "-fprint0",
    "-fprintf",
    "-fls",
})


def _normalise(name: str) -> str:
    name = os.path.basename(name).lower()
    return name[:-4] if name.endswith(".exe") else name


def program_names(executable: str) -> frozenset[str]:
    """Names under which ``executable`` may be recognised (as given and real)."""
    names = {_normalise(executable)}
    try:
        names.add(_normalise(os.path.realpath(executable)))
    except (OSError, ValueError):
        pass
    names.discard("")
    return frozenset(names)


def is_forwarder_name(name: str) -> bool:
    return _normalise(name) in FORWARDER_NAMES


def is_forwarder_executable(executable: str) -> bool:
    return bool(program_names(executable) & FORWARDER_NAMES)


def _check_git(args: Sequence[str]) -> None:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "-C":
            index += 2
            continue
        if token.startswith("-C") and len(token) > 2:
            index += 1
            continue
        if token in _GIT_FLAG_GLOBALS:
            index += 1
            continue
        break
    if index >= len(args):
        raise ValueError("worker command cannot invoke git without an allowed subcommand")
    sub = args[index]
    if sub.startswith("-"):
        raise ValueError(f"worker command cannot invoke git with global option {sub}")
    if sub not in GIT_ALLOWED_SUBCOMMANDS:
        raise ValueError(f"worker command cannot invoke git {sub}")
    for token in args[index + 1 :]:
        if token == "--":
            break
        if token.startswith(_GIT_FORBIDDEN_ANYWHERE_PREFIXES):
            raise ValueError(f"worker command cannot invoke git with option {token}")


def _check_gh(args: Sequence[str]) -> None:
    rest: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token in _GH_GLOBAL_WITH_VALUE:
            index += 2
            continue
        if token.startswith(("--repo=", "--hostname=")):
            index += 1
            continue
        rest.append(token)
        index += 1
    if rest and rest[0] in {"search", "status"}:
        return
    if tuple(rest[:2]) in _GH_ALLOWED:
        return
    raise ValueError(f"worker command cannot invoke gh {' '.join(rest[:2])}".rstrip())


def validate_exec(executable: str, argv: Iterable[str]) -> None:
    """Raise ValueError unless ``executable argv`` is permitted for a worker."""
    args = tuple(str(item) for item in argv)
    names = program_names(executable)
    if not names:
        raise ValueError("executable must be non-empty")
    if any(name.startswith("git-") for name in names):
        raise ValueError("dashed git builtins are not allowed")
    forwarders = sorted(names & FORWARDER_NAMES)
    if forwarders:
        raise ValueError(
            f"worker command cannot invoke forwarder or shell executable {forwarders[0]}"
        )
    if "git" in names:
        _check_git(args)
    if "gh" in names:
        _check_gh(args)
    if "find" in names:
        for token in args:
            if token in FIND_FORBIDDEN_ARGS:
                raise ValueError(f"worker command cannot invoke find {token}")


def is_git_executable(executable: str) -> bool:
    """True when ``executable`` is recognised as git by name or real path."""
    return "git" in program_names(executable)


def git_target_directory(args: Sequence[str], cwd: str) -> str:
    """Directory git will operate in: successive ``-C`` options applied to ``cwd``."""
    target = cwd
    index = 0
    while index < len(args):
        token = args[index]
        if token == "-C" and index + 1 < len(args):
            value, index = args[index + 1], index + 2
        elif token.startswith("-C") and len(token) > 2:
            value, index = token[2:], index + 1
        elif token in _GIT_FLAG_GLOBALS:
            index += 1
            continue
        else:
            break
        if value:
            target = os.path.normpath(os.path.join(target, value))
    return target


# Keys that make an otherwise allowlisted git verb execute repository-defined
# programs.  Git lowercases section and variable names; subsection names keep
# their case, hence ``.+`` there.
_GIT_EXECUTABLE_CONFIG_REGEX = (
    r"^(core\.(fsmonitor|pager|hookspath)"
    r"|diff\.external"
    r"|diff\..+\.(command|textconv)"
    r"|filter\..+\.(clean|smudge|process)"
    r"|merge\..+\.driver"
    r"|gpg\.program"
    r"|gpg\..+\.program"
    r"|log\.showsignature"
    r"|include\.path"
    r"|includeif\..+\.path)$"
)
_GIT_CONFIG_INSPECT_TIMEOUT_SECONDS = 5.0


def assert_git_repo_config_safe(
    target: str, env: Mapping[str, str], git_executable: str = "git"
) -> None:
    """Fail closed when ``target``'s git config defines executable drivers.

    Global/system config are neutralised by the caller's ``env``; the
    repository's own config (and anything it includes) is not.  Only key names
    are ever reported, never values.
    """
    refusal = "worker git command refused: "
    try:
        completed = subprocess.run(
            [
                git_executable,
                "-C",
                target,
                "config",
                "--includes",
                "-z",
                "--get-regexp",
                _GIT_EXECUTABLE_CONFIG_REGEX,
            ],
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_GIT_CONFIG_INSPECT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError(refusal + "repository config could not be inspected") from None
    if completed.returncode == 1:
        return
    if completed.returncode == 0:
        keys = set()
        for record in completed.stdout.split(b"\0"):
            if not record:
                continue
            key, _, value = record.partition(b"\n")
            # Hooks disabled outright (core.hooksPath=/dev/null) is hardening,
            # not an executable driver.
            if key == b"core.hookspath" and value == os.devnull.encode():
                continue
            keys.add(key.decode("utf-8", "replace"))
        if not keys:
            return
        keys = sorted(keys)
        raise ValueError(
            refusal + "repository config defines executable drivers: " + ", ".join(keys)
        )
    if completed.returncode == 128 and b"not a git repository" in completed.stderr.lower():
        return
    raise ValueError(refusal + "repository config could not be inspected")
