"""Git calls in a repository a candidate may have written.

Restore and rollback paths run git in a directory whose ``.git`` a candidate may control, so
no git call made through here may start a program that repository names, and a repository
that is not rooted at the directory acted on is left alone.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any, List, Optional, Tuple

GIT_TIMEOUT_S = 120.0
# Command-line config outranks repository config: hooks and fsmonitor are switched off,
# submodules (whose own config is not checked) are not recursed into, and a commit is not
# signed.
_GIT_OVERRIDES = (
    "-c",
    f"core.hooksPath={os.devnull}",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "submodule.recurse=false",
    "-c",
    "commit.gpgSign=false",
)
# Subcommand options that keep repository-named programs from running even if the config
# check below missed them: no external diff or textconv driver, no signature verification
# (log.showSignature runs gpg.program), no commit hooks, and no descent into a populated
# submodule (its .git, and so its config and hooks, may be planted).
_NO_DIFF_PROGRAMS = ("--no-ext-diff", "--no-textconv", "--ignore-submodules=all")
_SUBCOMMAND_FLAGS = {
    "diff": _NO_DIFF_PROGRAMS,
    "show": (*_NO_DIFF_PROGRAMS, "--no-show-signature"),
    "log": (*_NO_DIFF_PROGRAMS, "--no-show-signature"),
    "status": ("--ignore-submodules=all",),
    "commit": ("--no-verify",),
}
# Git processes started here and not yet reaped, per resolved repo_dir.
_RUNNING: dict[Path, int] = {}
_RUNNING_GUARD = threading.Lock()


def hardened_git_env(
    repo_dir: Path, git_dir: Optional[Path] = None, common_dir: Optional[Path] = None
) -> dict[str, str]:
    """The caller's environment without any GIT_* variable (GIT_DIR, GIT_WORK_TREE,
    GIT_CONFIG_*, GIT_EXEC_PATH ...); system and global config are not read, missing objects
    are never fetched, and discovery stops at ``repo_dir``. With ``git_dir`` (a probed git
    dir) GIT_DIR and GIT_WORK_TREE are pinned to it and ``repo_dir``, so a rewritten ``.git``
    pointer cannot redirect the call; ``common_dir`` (a verified linked worktree's) pins
    GIT_COMMON_DIR too."""
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_ATTR_NOSYSTEM="1",
        GIT_NO_LAZY_FETCH="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_CEILING_DIRECTORIES=str(repo_dir.parent),
    )
    if git_dir is not None:
        env.update(GIT_DIR=str(git_dir), GIT_WORK_TREE=str(repo_dir))
    if common_dir is not None:
        env["GIT_COMMON_DIR"] = str(common_dir)
    return env


def _with_subcommand_flags(args: Tuple[str, ...]) -> Tuple[str, ...]:
    """``args`` with the subcommand's flags inserted right after it, past any leading
    ``-c <name>=<value>`` pairs."""
    at = 0
    while at + 1 < len(args) and args[at] == "-c":
        at += 2
    if at < len(args) and args[at] in _SUBCOMMAND_FLAGS:
        return (*args[: at + 1], *_SUBCOMMAND_FLAGS[args[at]], *args[at + 1 :])
    return args


def run_hardened_git(
    repo_dir: Path,
    *args: str,
    git_dir: Optional[Path] = None,
    text: bool = True,
    index_file: Optional[Path] = None,
) -> subprocess.CompletedProcess[Any]:
    """Run ``git <args>`` in ``repo_dir`` (pinned to ``git_dir`` when given, on the index
    file ``index_file`` when given; output is bytes when ``text`` is False); raises
    ``subprocess.TimeoutExpired`` once the timed-out git has been killed and reaped."""
    args = _with_subcommand_flags(args)
    empty = "" if text else b""
    common_dir = None
    if git_dir is not None and (git_dir.is_symlink() or not git_dir.is_dir()):
        # Git follows a gitdir file even at a pinned GIT_DIR, so a replaced git dir fails here.
        message = f"fatal: pinned git dir is not a directory: {git_dir}\n"
        return subprocess.CompletedProcess(
            ["git", *args], 128, empty, message if text else message.encode()
        )
    if git_dir is not None and not git_dir.resolve().is_relative_to(Path(repo_dir).resolve()):
        # A linked worktree's admin dir: its registration is checked again and its common
        # dir pinned.
        if linked_worktree_git_dir(repo_dir) == git_dir.resolve():
            try:
                common_dir = _common_dir(git_dir.resolve())
            except (OSError, UnicodeDecodeError):
                common_dir = None
        if common_dir is None:
            message = f"fatal: pinned git dir is not a worktree: {git_dir}\n"
            return subprocess.CompletedProcess(
                ["git", *args], 128, empty, message if text else message.encode()
            )
    env = hardened_git_env(repo_dir, git_dir, common_dir)
    if index_file is not None:
        env["GIT_INDEX_FILE"] = str(index_file)
    key = Path(repo_dir).resolve()
    with _RUNNING_GUARD:
        _RUNNING[key] = _RUNNING.get(key, 0) + 1
    try:
        return subprocess.run(
            ["git", *_GIT_OVERRIDES, *args],
            cwd=str(repo_dir),
            env=env,
            capture_output=True,
            text=text,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    finally:
        with _RUNNING_GUARD:
            _RUNNING[key] -= 1
            if not _RUNNING[key]:
                del _RUNNING[key]


def clear_stale_index_lock(repo_dir: Path, git_dir: Path) -> bool:
    """Remove the ``index.lock`` a killed git left in ``git_dir``; True when one was removed.

    Only a git dir inside ``repo_dir`` is touched, and only while no git started through
    this module is still running in ``repo_dir``."""
    repo_dir = repo_dir.resolve()
    lock = git_dir / "index.lock"
    with _RUNNING_GUARD:
        if _RUNNING.get(repo_dir) or not git_dir.resolve().is_relative_to(repo_dir):
            return False
        if lock.is_symlink() or not lock.is_file():
            return False
        lock.unlink()
    return True


def config_names_a_repository_program(names: List[str]) -> bool:
    """Repository config the command line cannot switch off: filter drivers (smudge, clean,
    process), config-defined hooks (``hook.<name>.command``, which core.hooksPath does not
    cover), diff drivers (``diff.external``, ``diff.<driver>.textconv`` or ``.command``, which
    only some subcommands can switch off), signing programs (``gpg.program``,
    ``gpg.<format>.program``), includes (read from files outside this check) and promisor
    remotes (a missing object is fetched, which can start a transport program). Harmless keys
    such as ``diff.algorithm`` are not refused."""
    for name in (raw.lower() for raw in names):
        if name.startswith(("filter.", "gpg.", "hook.", "include.", "includeif.")):
            return True
        if name == "diff.external" or (
            name.startswith("diff.") and name.endswith((".command", ".textconv"))
        ):
            return True
        if name == "extensions.partialclone" or (
            name.startswith("remote.") and name.endswith(".promisor")
        ):
            return True
    return False


def repository_config_can_start_a_program(repo_dir: Path, git_dir: Optional[Path] = None) -> bool:
    """True when the config of the repository at ``repo_dir`` names such a program, or cannot
    be read."""
    try:
        config = run_hardened_git(
            repo_dir, "config", "--list", "--name-only", "--includes", git_dir=git_dir
        )
    except subprocess.TimeoutExpired:
        return True
    return config.returncode != 0 or config_names_a_repository_program(config.stdout.splitlines())


def repository_git_dir(repo_dir: Path) -> Optional[Path]:
    """The git dir when ``repo_dir`` is the work tree's top level and its git dir lies inside
    it, or when ``repo_dir`` is a linked worktree whose registration holds
    (``linked_worktree_git_dir``); else None.

    A copied gitdir may name another work tree (core.worktree) or live elsewhere (a gitdir
    file); checkout, reset and clean would then act outside ``repo_dir``."""
    repo_dir = repo_dir.resolve()
    try:
        probe = run_hardened_git(repo_dir, "rev-parse", "--show-toplevel", "--absolute-git-dir")
        found = probe.stdout.splitlines() if probe.returncode == 0 else []
    except subprocess.TimeoutExpired:
        found = []
    if len(found) != 2 or Path(found[0]).resolve() != repo_dir:
        return None
    git_dir = Path(found[1]).resolve()
    if git_dir.is_relative_to(repo_dir):
        return git_dir
    # A linked worktree: its registration is checked in Python and must be what git found.
    if linked_worktree_git_dir(repo_dir) == git_dir:
        return git_dir
    return None


def linked_worktree_git_dir(
    worktree: Path, controller_root: Optional[Path] = None
) -> Optional[Path]:
    """The git dir of ``worktree`` when it is a linked worktree whose registration nobody
    with write access to ``worktree`` alone could have made, else None.

    Checked in Python before any git call: ``worktree/.git`` is a regular file naming
    ``<common dir>/worktrees/<name>``, that registration's ``commondir`` is the same common
    dir and its ``gitdir`` points back at this ``.git`` file, and neither the registration
    nor the common dir lies inside ``worktree``. With ``controller_root`` the common dir must
    also be that repository's own. Pass the result as ``git_dir`` so a ``.git`` pointer
    rewritten later is never read."""
    try:
        root = Path(worktree)
        if root.is_symlink() or not root.is_dir():
            return None
        root = root.resolve()
        dotgit = root / ".git"
        if dotgit.is_symlink() or not dotgit.is_file():
            return None
        git_dir = _gitdir_pointer(dotgit)
        if git_dir is None or not git_dir.is_dir():
            return None
        common = _common_dir(git_dir)
        if (
            git_dir.parent != common / "worktrees"
            or common.is_relative_to(root)
            or _gitdir_pointer(git_dir / "gitdir", prefix="") != dotgit
        ):
            return None
        if controller_root is not None and common != _controller_common_dir(controller_root):
            return None
        return git_dir
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _gitdir_pointer(path: Path, prefix: str = "gitdir:") -> Optional[Path]:
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith(prefix) or not text[len(prefix) :].strip():
        return None
    return (path.parent / text[len(prefix) :].strip()).resolve()


def _common_dir(git_dir: Path) -> Path:
    try:
        text = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return git_dir
    return (git_dir / text).resolve()


def _controller_common_dir(controller_root: Path) -> Optional[Path]:
    dotgit = Path(controller_root).resolve() / ".git"
    if dotgit.is_dir() and not dotgit.is_symlink():
        return dotgit.resolve()
    if dotgit.is_file() and not dotgit.is_symlink():
        git_dir = _gitdir_pointer(dotgit)
        return _common_dir(git_dir) if git_dir is not None else None
    return None
