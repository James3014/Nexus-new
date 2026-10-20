"""Task exclusions decided BEFORE any arm runs (#2721), identical for every arm.

A task is excluded -- from BARE, NEXUS and NOOP together, with its reason
recorded -- when it cannot be measured fairly:

* ``NO_TASK_VENV``: the manifest gives it no task venv (9 repos have none); the
  adapter would refuse the venv in one arm only by accident of paths.
* ``GIT_FILTER_DRIVER`` / ``GIT_SUBMODULE`` / ``GIT_LFS``: since #2807 the
  measurement Gateway's hardened git refuses a Controller whose base tree or
  config declares a filter (clean/smudge/process, git-lfs), a diff
  textconv/command driver, a non-empty ``info/attributes`` or a submodule
  (``.gitmodules`` / gitlink).  Such a task would fail in NEXUS only.

The checks read the materialized base checkout with hardened, read-only git
(no hooks, fsmonitor, attributes file or inherited ``GIT_*``); they never run
a filter.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

REASON_NO_VENV = "NO_TASK_VENV"
REASON_FILTER = "GIT_FILTER_DRIVER"
REASON_SUBMODULE = "GIT_SUBMODULE"
REASON_LFS = "GIT_LFS"
_DRIVER_CONFIG = r"^filter\.|^diff\..*\.(textconv|command)$"
_ATTR_FILTER = re.compile(rb"(?:^|\s)filter=", re.MULTILINE)
_ATTR_LFS = re.compile(rb"(?:^|\s)filter=lfs\b", re.MULTILINE)
_SAFE = ("-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never",
         "-c", "core.attributesFile=/dev/null", "-c", "submodule.recurse=false")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", *_SAFE, *args], cwd=str(repo), env=env, capture_output=True,
                          stdin=subprocess.DEVNULL, check=False)


def git_problems(repo: Path, base: str) -> list[str]:
    """Reasons the hardened measurement Gateway would refuse this base checkout."""
    reasons: list[str] = []
    config = _git(repo, "config", "--local", "--get-regexp", _DRIVER_CONFIG)
    if config.returncode == 0 and config.stdout.strip():
        reasons.append(REASON_FILTER)
    gitdir = _git(repo, "rev-parse", "--git-common-dir")
    if gitdir.returncode == 0:
        common = Path(gitdir.stdout.decode().strip())
        common = common if common.is_absolute() else Path(repo) / common
        info = common / "info" / "attributes"
        if info.is_file() and info.read_bytes().strip():
            reasons.append(REASON_FILTER)
        modules = common / "modules"
        if modules.is_dir() and any(modules.iterdir()):
            reasons.append(REASON_SUBMODULE)
    tree = _git(repo, "ls-tree", "-r", "-z", "--full-tree", base)
    if tree.returncode != 0:
        return [*reasons, f"BASE_TREE_UNREADABLE:{base[:12]}"]
    for entry in tree.stdout.split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        mode, kind, obj = (meta.split(b" ") + [b"", b""])[:3]
        name = path.rsplit(b"/", 1)[-1]
        if kind == b"commit" or mode == b"160000" or path == b".gitmodules":
            reasons.append(REASON_SUBMODULE)
        elif name == b".gitattributes":
            blob = _git(repo, "cat-file", "blob", obj.decode()).stdout
            if _ATTR_LFS.search(blob):
                reasons.append(REASON_LFS)
            elif _ATTR_FILTER.search(blob):
                reasons.append(REASON_FILTER)
    return sorted(set(reasons))


def exclusion_reasons(task: Mapping[str, Any]) -> list[str]:
    reasons = []
    if not task.get("venv"):
        reasons.append(REASON_NO_VENV)
    checkout = task.get("base_checkout")
    if checkout and Path(checkout).exists():
        reasons.extend(git_problems(Path(checkout), task["base_commit"]))
    else:
        reasons.append("BASE_CHECKOUT_MISSING")
    return reasons


def split(tasks: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(measured tasks, excluded tasks with reasons): the same split for every arm."""
    measured, excluded = [], []
    for task in tasks:
        reasons = exclusion_reasons(task)
        if reasons:
            excluded.append({"task_id": task["task_id"], "repo": task.get("repo"), "reasons": reasons})
        else:
            measured.append(dict(task))
    return measured, excluded
