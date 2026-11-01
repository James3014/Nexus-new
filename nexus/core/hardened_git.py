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
from typing import List, Optional

GIT_TIMEOUT_S = 120.0
# Command-line config outranks repository config: hooks and fsmonitor are switched off, and
# submodules (whose own config is not checked) are not entered.
_GIT_OVERRIDES = (
    "-c",
    f"core.hooksPath={os.devnull}",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "submodule.recurse=false",
)
# Git processes started here and not yet reaped, per resolved repo_dir.
_RUNNING: dict[Path, int] = {}
_RUNNING_GUARD = threading.Lock()


def hardened_git_env(repo_dir: Path) -> dict[str, str]:
    """The caller's environment without any GIT_* variable (GIT_DIR, GIT_WORK_TREE,
    GIT_CONFIG_*, GIT_EXEC_PATH ...); system and global config are not read, missing objects
    are never fetched, and discovery stops at ``repo_dir``."""
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_ATTR_NOSYSTEM="1",
        GIT_NO_LAZY_FETCH="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_CEILING_DIRECTORIES=str(repo_dir.parent),
    )
    return env


def run_hardened_git(repo_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` in ``repo_dir``; raises ``subprocess.TimeoutExpired`` once the
    timed-out git has been killed and reaped."""
    key = Path(repo_dir).resolve()
    with _RUNNING_GUARD:
        _RUNNING[key] = _RUNNING.get(key, 0) + 1
    try:
        return subprocess.run(
            ["git", *_GIT_OVERRIDES, *args],
            cwd=str(repo_dir),
            env=hardened_git_env(repo_dir),
            capture_output=True,
            text=True,
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
    cover), includes (read from files outside this check) and promisor remotes (a missing
    object is fetched, which can start a transport program)."""
    for name in (raw.lower() for raw in names):
        if name.startswith(("filter.", "hook.", "include.", "includeif.")):
            return True
        if name == "extensions.partialclone" or (
            name.startswith("remote.") and name.endswith(".promisor")
        ):
            return True
    return False


def repository_config_can_start_a_program(repo_dir: Path) -> bool:
    """True when the config of the repository at ``repo_dir`` names such a program, or cannot
    be read."""
    try:
        config = run_hardened_git(repo_dir, "config", "--list", "--name-only", "--includes")
    except subprocess.TimeoutExpired:
        return True
    return config.returncode != 0 or config_names_a_repository_program(config.stdout.splitlines())


def repository_git_dir(repo_dir: Path) -> Optional[Path]:
    """The git dir when ``repo_dir`` is the work tree's top level and its git dir lies inside
    it, else None.

    A copied gitdir may name another work tree (core.worktree) or live elsewhere (a gitdir
    file); checkout, reset and clean would then act outside ``repo_dir``."""
    repo_dir = repo_dir.resolve()
    try:
        probe = run_hardened_git(repo_dir, "rev-parse", "--show-toplevel", "--absolute-git-dir")
        found = probe.stdout.splitlines() if probe.returncode == 0 else []
    except subprocess.TimeoutExpired:
        found = []
    if (
        len(found) == 2
        and Path(found[0]).resolve() == repo_dir
        and Path(found[1]).resolve().is_relative_to(repo_dir)
    ):
        return Path(found[1]).resolve()
    return None


def repository_is_rooted_at(repo_dir: Path) -> bool:
    """True when ``repo_dir`` is the work tree's top level and its git dir lies inside it."""
    return repository_git_dir(repo_dir) is not None
