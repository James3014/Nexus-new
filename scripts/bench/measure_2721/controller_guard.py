"""The measurement Gateway's Controller: where it may live and how a row resets it (#2721).

The Controller must be a *linked worktree* of a measurement repository (the
Gateway's ``bound_controller_problem`` requires it to share its git common dir
with the loaded source root; a separate clone is refused as SOURCE_MISMATCH).
So the reset must never touch anything else of that repository:

* ``guard_controller(...)`` (review B1/H1/M1/M2): the Controller worktree and
  its git common dir resolve under ONE measurement root (the outermost of
  ``--measurement-root``, ``--external-target-root`` and
  ``NEXUS_MEASURE_EXTERNAL_TARGET_ROOT``; the given roots must nest, else
  ``MEASUREMENT_ROOTS_DISAGREE``); the root itself is not ``/``, ``~``,
  ``~/workspace``, ``~/Workspace`` or an ancestor of them; the common dir is
  not a main clone (``~/workspace/<repo>/.git``, ``~/Workspace/<repo>/.git``);
  and neither overlaps a live Gateway location read from the live
  configuration (refused when that configuration cannot be read).  Paths are
  compared by inode, then case-insensitively (macOS realpath keeps case).
* ``ControllerReset.reset()``: only the Controller's own worktree is reset
  (``reset --hard <pin>``, ``clean -fdx`` in that worktree) and only
  measurement refs are deleted (``refs/heads/nexus/task/*``,
  ``refs/nexus-candidates/*``, ``refs/stash``); other branches, remotes and
  tags stay, and only worktrees created after the run started are removed.
"""

from __future__ import annotations

import os
import plistlib
import re
import shlex
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from scripts.bench.measure_2721.common import git

MEASUREMENT_REF_PREFIXES = ("refs/heads/nexus/task/", "refs/nexus-candidates/")
STASH_REF = "refs/stash"
LIVE_TREE = Path("Library") / "Application Support" / "Nexus"
_ROOT_KEY = re.compile(r"(ROOT|SOURCE|CONTROLLER)")
_CD = re.compile(r"""\bcd\s+("([^"]+)"|'([^']+)'|(\S+))""")


class ControllerGuardError(ValueError):
    """``str(exc)`` starts with a stable code."""


# -- path comparison ----------------------------------------------------------------


def _real(path: Path | str) -> Path:
    return Path(os.path.realpath(os.path.expanduser(str(path))))


def same_path(a: Path | str, b: Path | str) -> bool:
    ra, rb = _real(a), _real(b)
    try:
        sa, sb = os.stat(ra), os.stat(rb)
        if (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino):
            return True
    except OSError:
        pass
    return str(ra).casefold() == str(rb).casefold()


def is_within(child: Path | str, root: Path | str) -> bool:
    """``child`` is ``root`` or below it (inode or case-insensitive match)."""
    real = _real(child)
    return any(same_path(candidate, root) for candidate in (real, *real.parents))


def strictly_within(child: Path | str, root: Path | str) -> bool:
    return is_within(child, root) and not same_path(child, root)


# -- roots ---------------------------------------------------------------------------


def _home() -> Path:
    return _real(Path.home())


def broad_roots() -> list[Path]:
    home = _home()
    return [home, home / "workspace", home / "Workspace"]


def check_measurement_root(root: Path | str) -> Path:
    """Refuse a root that is ``/``, ``~``, ``~/workspace``, ``~/Workspace`` or an ancestor of them (H1)."""
    real = _real(root)
    if real == Path(real.anchor):
        raise ControllerGuardError(f"MEASUREMENT_ROOT_TOO_BROAD: {real}")
    for broad in broad_roots():
        if is_within(broad, real):  # real is broad itself or an ancestor of it
            raise ControllerGuardError(f"MEASUREMENT_ROOT_TOO_BROAD: {real}")
    return real


def measurement_root(sources: Mapping[str, Optional[Path | str]]) -> Path:
    """The ONE measurement root from every given source (M2).

    The given roots must nest (one inside the other); the outermost is the
    root.  Two disjoint roots mean the operator configured two measurements.
    """
    given = {name: _real(value) for name, value in sources.items() if value}
    if not given:
        raise ControllerGuardError("MEASUREMENT_ROOT_MISSING: give --measurement-root")
    ordered = sorted(given.items(), key=lambda item: len(item[1].parts))
    outer_name, outer = ordered[0]
    for name, value in ordered[1:]:
        if not is_within(value, outer):
            raise ControllerGuardError(f"MEASUREMENT_ROOTS_DISAGREE: {name} is not inside {outer_name}")
    return check_measurement_root(outer)


# -- live configuration (M1) ---------------------------------------------------------


def default_live_configs() -> list[Path]:
    home = _home()
    agents = home / "Library" / "LaunchAgents"
    plists = sorted(agents.glob("com.nexus.mcp.gateway*.plist*")) if agents.is_dir() else []
    return [*plists, home / LIVE_TREE / "mcp-gateway.env"]


def _paths_from_text(text: str) -> list[str]:
    found = [next(g for g in m.groups()[1:] if g) for m in _CD.finditer(text)]
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        name, sep, value = line.partition("=")
        if sep and _ROOT_KEY.search(name):
            try:
                parts = shlex.split(value)
            except ValueError:
                continue
            found.extend(p for p in parts if p.startswith("/"))
    return found


def live_locations(configs: Optional[Sequence[Path | str]] = None) -> list[Path]:
    """Live Gateway Controller/source locations, read from the live configuration.

    Raises LIVE_CONFIG_UNREADABLE when not one configuration file can be read:
    the driver then refuses to start instead of guessing (M1).
    """
    read_any = False
    paths: list[str] = [str(_home() / LIVE_TREE)]
    for config in (default_live_configs() if configs is None else [Path(c) for c in configs]):
        try:
            raw = Path(config).read_bytes()
        except OSError:
            continue
        read_any = True
        try:
            plist = plistlib.loads(raw)
        except Exception:  # noqa: BLE001 - not a plist: an env file
            paths.extend(_paths_from_text(raw.decode("utf-8", errors="replace")))
            continue
        if isinstance(plist, dict):
            if plist.get("WorkingDirectory"):
                paths.append(str(plist["WorkingDirectory"]))
            for name, value in (plist.get("EnvironmentVariables") or {}).items():
                if _ROOT_KEY.search(str(name)) and str(value).startswith("/"):
                    paths.append(str(value))
            for arg in plist.get("ProgramArguments") or []:
                paths.extend(_paths_from_text(str(arg)))
    if not read_any:
        raise ControllerGuardError("LIVE_CONFIG_UNREADABLE: cannot read any live Gateway configuration")
    return [Path(p) for p in dict.fromkeys(paths)]


# -- the guard -----------------------------------------------------------------------


def git_common_dir(worktree: Path) -> Path:
    raw = git(worktree, "rev-parse", "--git-common-dir").strip()
    path = Path(raw)
    return _real(path if path.is_absolute() else Path(worktree) / path)


def guard_controller(controller: Path | str, root: Path | str, live: Iterable[Path]) -> dict[str, Path]:
    real = _real(controller)
    if not (real / ".git").exists():
        raise ControllerGuardError(f"CONTROLLER_NOT_A_CHECKOUT: {real}")
    top = _real(git(real, "rev-parse", "--show-toplevel").strip())
    if not same_path(top, real):
        raise ControllerGuardError(f"CONTROLLER_NOT_A_WORKTREE_TOP: {real}")
    common = git_common_dir(real)
    home = _home()
    for parent in (home / "workspace", home / "Workspace"):
        # A main clone (~/workspace/<repo>), anything inside one, or a linked
        # worktree whose common dir is one.
        for candidate in (real, common):
            for ancestor in (candidate, *candidate.parents):
                if same_path(ancestor.parent, parent) and (ancestor / ".git").exists():
                    raise ControllerGuardError(f"CONTROLLER_IN_MAIN_CLONE: {ancestor}")
    for name, path in (("CONTROLLER", real), ("CONTROLLER_COMMON_DIR", common)):
        if not strictly_within(path, root):
            raise ControllerGuardError(f"{name}_OUTSIDE_MEASUREMENT_ROOT: {path}")
    for location in live:
        for path in (real, common):
            if is_within(path, location) or is_within(location, path):
                raise ControllerGuardError(f"CONTROLLER_OVERLAPS_LIVE_GATEWAY: {path}")
    return {"controller": real, "common_dir": common, "root": _real(root)}


# -- the reset -----------------------------------------------------------------------


def _worktrees(repo: Path) -> list[str]:
    return [str(_real(line[len("worktree "):])) for line in git(repo, "worktree", "list", "--porcelain").splitlines()
            if line.startswith("worktree ")]


def _measurement_refs(repo: Path) -> list[str]:
    refs = git(repo, "for-each-ref", "--format=%(refname)").splitlines()
    return [ref for ref in refs if ref.startswith(MEASUREMENT_REF_PREFIXES)] + (
        [STASH_REF] if git(repo, "rev-parse", "-q", "--verify", STASH_REF, check=False).strip() else [])


def _dirty(repo: Path, preserved: Sequence[str]) -> list[str]:
    entries = git(repo, "status", "--porcelain", "--untracked-files=all", "--ignored").splitlines()
    return [e for e in entries if not any(e[3:].startswith(prefix) for prefix in preserved)]


class ControllerReset:
    """Per-row reset of the Controller worktree to its pin (B1)."""

    def __init__(self, controller: Path, pin: str, *, preserved_prefixes: Sequence[str] = ()):
        self.controller = _real(controller)
        self.pin = pin
        self.preserved = tuple(p for p in preserved_prefixes if p)
        # Worktrees that existed when the run started are never removed.
        self.start_worktrees = frozenset(_worktrees(self.controller))

    def reset(self) -> dict[str, Any]:
        repo = self.controller
        removed: list[str] = []
        try:
            removed.extend(f"untracked {e[3:]}" for e in _dirty(repo, self.preserved))
            for path in _worktrees(repo):
                if path not in self.start_worktrees:
                    git(repo, "worktree", "remove", "--force", path, check=False)
                    removed.append(f"worktree {path}")
            git(repo, "worktree", "prune")
            git(repo, "reset", "-q", "--hard", self.pin)
            excludes = [arg for prefix in self.preserved for arg in ("-e", prefix)]
            git(repo, "clean", "-q", "-fdx", *excludes)
            for ref in _measurement_refs(repo):
                git(repo, "update-ref", "-d", ref)
                removed.append(ref)
            head = git(repo, "rev-parse", "HEAD").strip()
            pin = git(repo, "rev-parse", f"{self.pin}^{{commit}}").strip()
            dirty = _dirty(repo, self.preserved)
            refs = _measurement_refs(repo)
            extra = sorted(set(_worktrees(repo)) - self.start_worktrees)
        except RuntimeError as exc:
            return {"ok": False, "error": str(exc)[-300:], "removed": removed}
        return {"ok": head == pin and not dirty and not refs and not extra, "head": head, "pin": pin,
                "dirty": dirty[:20], "measurement_refs": refs, "extra_worktrees": extra,
                "removed": [r for r in removed if not r.startswith("untracked ")],
                "removed_untracked": [r[len("untracked "):] for r in removed if r.startswith("untracked ")][:50]}
