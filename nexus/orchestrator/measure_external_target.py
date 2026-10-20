"""Measurement-only external target for the Gateway worker path (Issue #2721).

The live Gateway binds every ``nexus_worker_candidate`` task to the Nexus-new
Controller: the Target worktree is cut from Controller HEAD.  A frozen
measurement Gateway may instead cut the Target from a pinned commit of an
external repository, so a benchmark task runs against the external repository
as-is.  This is enabled ONLY when ``NEXUS_MEASURE_EXTERNAL_TARGET_ROOT`` is set
in the Gateway process environment at start (it is read once, at import); the
live Gateway never sets it, so for live the ``external_target`` argument stays
an unknown field and nothing here runs.

Validation fails closed with a stable ``EXTERNAL_TARGET_*`` code:

* ``repo_root`` is an absolute path whose resolved (symlink-free) location is
  strictly inside the resolved measurement root;
* it is the top level of a non-bare git work tree (not a subdirectory of
  another repository) and not a checkout of the Nexus-new repository itself;
* its git dir and git common dir also resolve strictly inside the measurement
  root (a linked worktree of an outside repository is refused);
* matching is case-insensitive on darwin and also by inode;
* git probes run without inherited ``GIT_*`` variables, system/global config,
  prompts, fsmonitor, hooks or transports;
* ``base_revision`` is a full lowercase 40-hex SHA equal to ``HEAD``;
* neither ``repo_root`` nor the measurement root overlaps a live location:
  the canonical (Controller) root, the loaded source root, the Nexus-new
  repository's main checkout, ``~/Library/Application Support/Nexus`` and an
  explicitly configured ``NEXUS_CANONICAL_SOURCE_ROOT``;
* the work tree is clean (tracked and untracked).  The Target lease refuses a
  dirty Controller anyway (``WorktreeManager._verify_controller``), so a dirty
  external repository is refused here, before any planner or provider work;
* no git filter can run (#2749): the repository config defines no
  ``filter.*`` driver (nor a ``diff.*.textconv``/``command`` driver), no
  ``.gitattributes`` in the base tree declares ``filter=`` and no
  ``info/attributes`` file is non-empty (``EXTERNAL_TARGET_FILTER_DRIVER_PRESENT``).
  This is checked before the first ``git status``, since status runs clean
  filters.

Every git call ``WorktreeManager`` makes for an accepted external Controller
(or one of its Target worktrees) goes through ``run_hardened_git`` (#2749):
the flags above plus ``core.attributesFile=/dev/null`` and
``commit.gpgSign=false``, the inherited ``GIT_*`` environment dropped, no
system/global config or system attributes, no prompt, stdin closed, and a
driver re-check before each call, so a filter planted after validation makes
the call refuse instead of running it.  ``external_git_context`` decides which
calls those are, from the start-time measurement root only; with the variable
unset it is always ``False`` and the live git calls are unchanged.

The Task Card still lives in the Nexus-new ``tasks/`` tree; only the Controller
(the repository the Target worktree is cut from) changes.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

MEASURE_EXTERNAL_TARGET_ROOT_ENV = "NEXUS_MEASURE_EXTERNAL_TARGET_ROOT"
EXTERNAL_TARGET_KEYS = frozenset({"repo_root", "base_revision"})
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
# Snapshot taken once at import (= Gateway start): the schema hash is computed
# at import too, so a variable set later must not enable anything (#2742).
MEASURE_EXTERNAL_TARGET_ROOT_AT_START = str(
    os.environ.get(MEASURE_EXTERNAL_TARGET_ROOT_ENV, "") or ""
).strip()
# Repository-local config must not run commands while we probe (#2742):
# fsmonitor and hooks are disabled and no transport is allowed.
_GIT_SAFE_CONFIG = (
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "protocol.allow=never",
)  # fmt: skip
# The lease/capture runner adds two more (#2749): no attributes file from the
# repository config and no signing program on a candidate commit.
HARDENED_GIT_CONFIG = (
    *_GIT_SAFE_CONFIG,
    "-c", "core.attributesFile=/dev/null",
    "-c", "commit.gpgSign=false",
)  # fmt: skip
# Config keys that name a command git runs on file content: filter drivers
# (clean/smudge/process) and diff textconv/external commands (#2749).
GIT_DRIVER_CONFIG_REGEX = r"^filter\.|^diff\..*\.(textconv|command)$"
FILTER_DRIVER_PRESENT = "EXTERNAL_TARGET_FILTER_DRIVER_PRESENT"
_ATTRIBUTE_FILTER = re.compile(rb"(?:^|\s)filter=", re.MULTILINE)


class ExternalTargetError(ValueError):
    """A refused external target; ``str(exc)`` is the stable code."""


class ExternalGitRefused(RuntimeError):
    """A hardened git call on an external Controller was refused (#2749).

    A ``RuntimeError`` like every other ``WorktreeManager`` git failure, so the
    lease's rollback paths still run; ``str(exc)`` is the stable code.
    """


@dataclass(frozen=True)
class ExternalTarget:
    """A validated external target: resolved repository root and its exact HEAD."""

    repo_root: Path
    base_revision: str


def _configured_root(env: Optional[Mapping[str, str]]) -> str:
    """The start-time snapshot; ``env`` is an explicit override for unit tests only."""
    if env is None:
        return MEASURE_EXTERNAL_TARGET_ROOT_AT_START
    return str(env.get(MEASURE_EXTERNAL_TARGET_ROOT_ENV, "") or "").strip()


def external_target_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """True only when the measurement root variable was set (non-blank) at start."""
    return bool(_configured_root(env))


def _measurement_root(env: Optional[Mapping[str, str]]) -> Path:
    raw = _configured_root(env)
    if not raw:
        raise ExternalTargetError("EXTERNAL_TARGET_DISABLED")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ExternalTargetError("EXTERNAL_TARGET_ROOT_UNCONFIGURED")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ExternalTargetError("EXTERNAL_TARGET_ROOT_UNCONFIGURED") from exc
    if not resolved.is_dir():
        raise ExternalTargetError("EXTERNAL_TARGET_ROOT_UNCONFIGURED")
    return resolved


def hardened_git_environment(base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """``base`` (default: the process env) without any ``GIT_*`` variable.

    No system/global config and no prompt.  A ``GIT_*`` value the caller put in
    ``base`` is dropped too: the hardened runner sets every git variable itself.
    """
    source = os.environ if base is None else base
    environment = {key: value for key, value in source.items() if not key.startswith("GIT_")}
    environment.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    })
    return environment


def _git_environment() -> dict[str, str]:
    """Inherited env without any ``GIT_*`` variable; no system/global config, no prompt."""
    return hardened_git_environment()


def _git(repo_root: Path, *args: str) -> str:
    environment = _git_environment()
    try:
        result = subprocess.run(
            ["git", *_GIT_SAFE_CONFIG, "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=environment,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExternalTargetError("EXTERNAL_TARGET_GIT_UNAVAILABLE") from exc
    if result.returncode != 0:
        raise ExternalTargetError("EXTERNAL_TARGET_NOT_GIT_WORKTREE")
    return result.stdout


def _same_directory(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


# APFS/HFS+ are case-insensitive by default: compare case-folded on darwin (#2742).
_CASE_INSENSITIVE_PATHS = sys.platform == "darwin"


def _lexical_key(path: Path) -> tuple[str, ...]:
    parts = path.parts
    return tuple(part.casefold() for part in parts) if _CASE_INSENSITIVE_PATHS else parts


def _same_or_ancestor(path: Path, other: Path) -> bool:
    """True when ``other`` is ``path`` or one of its ancestors (by spelling or by inode)."""
    key, other_key = _lexical_key(path), _lexical_key(other)
    if key[: len(other_key)] == other_key:
        return True
    return any(_same_directory(candidate, other) for candidate in (path, *path.parents))


def _overlaps(path: Path, other: Path) -> bool:
    """True when ``path`` equals, is inside, or contains ``other``."""
    return _same_or_ancestor(path, other) or _same_or_ancestor(other, path)


def _nexus_common_dir(nexus_root: Path) -> Path:
    """The Nexus-new git common dir; unreadable means refuse, never skip (#2742)."""
    try:
        common = _git(
            Path(nexus_root), "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).strip()
    except ExternalTargetError as exc:
        raise ExternalTargetError("EXTERNAL_TARGET_NEXUS_IDENTITY_UNREADABLE") from exc
    if not common:
        raise ExternalTargetError("EXTERNAL_TARGET_NEXUS_IDENTITY_UNREADABLE")
    return Path(common)


def live_forbidden_roots(
    nexus_root: Path,
    *,
    extra: Iterable[Path] = (),
    env: Optional[Mapping[str, str]] = None,
) -> tuple[Path, ...]:
    """Live locations an external target (or the measurement root) may never overlap."""
    environment = os.environ if env is None else env
    candidates: list[Path] = [
        Path(nexus_root),
        *extra,
        Path.home() / "Library" / "Application Support" / "Nexus",
    ]
    configured = str(environment.get("NEXUS_CANONICAL_SOURCE_ROOT", "") or "").strip()
    if configured:
        candidates.append(Path(configured))
    # The repository's main checkout (e.g. ~/workspace/Nexus-new) owns the common gitdir.
    candidates.append(_nexus_common_dir(Path(nexus_root)).parent)
    resolved: list[Path] = []
    for candidate in candidates:
        try:
            resolved.append(candidate.expanduser().resolve())
        except (OSError, RuntimeError):
            resolved.append(candidate.expanduser().absolute())
    return tuple(dict.fromkeys(resolved))


def _strictly_inside(path: Path, root: Path) -> bool:
    """``path`` (already resolved) is strictly below the resolved ``root``."""
    return path != root and root in path.parents


def external_target_head(repo_root: Path) -> str:
    """Current ``HEAD`` commit of a validated external repository (40-hex)."""
    head = _git(repo_root, "rev-parse", "--verify", "--end-of-options", "HEAD^{commit}").strip()
    if not _SHA40.fullmatch(head):
        raise ExternalTargetError("EXTERNAL_TARGET_HEAD_UNREADABLE")
    return head


def validate_external_target(
    raw: Any,
    *,
    nexus_root: Path,
    env: Optional[Mapping[str, str]] = None,
    forbidden_roots: Iterable[Path] = (),
) -> ExternalTarget:
    """Validate one ``external_target`` argument; raise ``ExternalTargetError``.

    ``forbidden_roots`` adds live locations (e.g. the loaded source root) to
    the ones derived by ``live_forbidden_roots``.
    """
    if not external_target_enabled(env):
        raise ExternalTargetError("EXTERNAL_TARGET_DISABLED")
    if not isinstance(raw, Mapping) or set(raw) != EXTERNAL_TARGET_KEYS:
        raise ExternalTargetError("EXTERNAL_TARGET_INVALID")
    measurement_root = _measurement_root(env)
    forbidden = live_forbidden_roots(nexus_root, extra=forbidden_roots, env=env)
    if any(_overlaps(measurement_root, live) for live in forbidden):
        raise ExternalTargetError("EXTERNAL_TARGET_ROOT_FORBIDDEN")
    raw_root = raw.get("repo_root")
    raw_revision = raw.get("base_revision")
    if not isinstance(raw_root, str) or not raw_root.strip() or "\x00" in raw_root:
        raise ExternalTargetError("EXTERNAL_TARGET_REPO_ROOT_INVALID")
    if not isinstance(raw_revision, str) or not _SHA40.fullmatch(raw_revision):
        raise ExternalTargetError("EXTERNAL_TARGET_BASE_REVISION_INVALID")
    candidate = Path(raw_root)
    if not candidate.is_absolute():
        raise ExternalTargetError("EXTERNAL_TARGET_REPO_ROOT_NOT_ABSOLUTE")
    try:
        repo_root = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ExternalTargetError("EXTERNAL_TARGET_REPO_ROOT_MISSING") from exc
    if not repo_root.is_dir():
        raise ExternalTargetError("EXTERNAL_TARGET_REPO_ROOT_MISSING")
    # Strictly inside the measurement root, judged on resolved paths so a
    # symlink planted under the root cannot point the Controller elsewhere.
    if not _strictly_inside(repo_root, measurement_root):
        raise ExternalTargetError("EXTERNAL_TARGET_OUTSIDE_ROOT")
    if any(_overlaps(repo_root, live) for live in forbidden):
        raise ExternalTargetError("EXTERNAL_TARGET_FORBIDDEN_PATH")
    toplevel = _git(repo_root, "rev-parse", "--show-toplevel").strip()
    if not toplevel or not _same_directory(Path(toplevel), repo_root):
        raise ExternalTargetError("EXTERNAL_TARGET_NOT_REPOSITORY_TOPLEVEL")
    git_dir = _git(repo_root, "rev-parse", "--absolute-git-dir").strip()
    common = _git(repo_root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    # Never the Nexus-new repository (any of its worktrees): that Controller is
    # governed by the bound-Controller checks, which this path does not run.
    nexus_common = _nexus_common_dir(nexus_root)
    if _same_directory(repo_root, nexus_root) or _same_directory(Path(common), nexus_common):
        raise ExternalTargetError("EXTERNAL_TARGET_IS_NEXUS_CONTROLLER")
    # The git metadata (this worktree's gitdir and the shared common dir) must
    # live under the measurement root too, so a linked worktree of an outside
    # repository cannot make it the Controller (#2742).
    for raw_meta in (git_dir, common):
        try:
            meta = Path(raw_meta).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ExternalTargetError("EXTERNAL_TARGET_GIT_METADATA_OUTSIDE_ROOT") from exc
        if not raw_meta or not _strictly_inside(meta, measurement_root):
            raise ExternalTargetError("EXTERNAL_TARGET_GIT_METADATA_OUTSIDE_ROOT")
        if any(_overlaps(meta, live) for live in forbidden):
            raise ExternalTargetError("EXTERNAL_TARGET_FORBIDDEN_PATH")
    if external_target_head(repo_root) != raw_revision:
        raise ExternalTargetError("EXTERNAL_TARGET_HEAD_MISMATCH")
    # Before the status probe below: ``git status`` runs clean filters (#2749).
    finding = filter_driver_finding(repo_root, raw_revision)
    if finding is not None:
        raise ExternalTargetError(finding)
    if _git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise ExternalTargetError("EXTERNAL_TARGET_DIRTY")
    return ExternalTarget(repo_root=repo_root, base_revision=raw_revision)


def accepted_external_controller(
    controller_repo_root: Any,
    expected_head: Any,
    *,
    nexus_root: Path,
    env: Optional[Mapping[str, str]] = None,
    forbidden_roots: Iterable[Path] = (),
) -> Optional[ExternalTarget]:
    """Service-side re-check: is this request's Controller an accepted external target?

    Returns ``None`` when the measurement mode is off or the Controller is the
    Nexus root (the unchanged live behaviour).  Otherwise the Controller is
    re-validated from scratch (never trusted from the request) with
    ``expected_head`` as its required ``HEAD``; any failure raises.
    """
    if not external_target_enabled(env) or not controller_repo_root:
        return None
    controller = Path(str(controller_repo_root)).expanduser()
    try:
        if controller.resolve() == Path(nexus_root).resolve():
            return None
    except (OSError, RuntimeError):
        pass
    return validate_external_target(
        {"repo_root": str(controller), "base_revision": str(expected_head or "")},
        nexus_root=nexus_root,
        env=env,
        forbidden_roots=forbidden_roots,
    )


# --------------------------------------------------------------------------
# Hardened git for the lease, capture and commit of an external Controller
# (#2749).  ``WorktreeManager`` routes a call here when
# ``external_git_context`` says git would read an external repository.
# --------------------------------------------------------------------------


def _measurement_root_at_start() -> Optional[Path]:
    """The start-time measurement root, resolved; ``None`` when the mode is off.

    Raises ``ExternalGitRefused`` when the mode is on but the root cannot be
    resolved: the caller must then treat every git call as external.
    """
    raw = MEASURE_EXTERNAL_TARGET_ROOT_AT_START
    if not raw:
        return None
    try:
        return Path(raw).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ExternalGitRefused("EXTERNAL_TARGET_ROOT_UNCONFIGURED") from exc


def _discovered_git_dirs(start: Path) -> Optional[tuple[Path, Path]]:
    """The ``(gitdir, common dir)`` git would use from ``start``, read in Python.

    ``None`` when it cannot be told (no ``.git`` found, an unreadable pointer).
    """
    for directory in (start, *start.parents):
        dotgit = directory / ".git"
        try:
            if dotgit.is_dir():
                gitdir = dotgit.resolve(strict=True)
            elif dotgit.is_file():
                text = dotgit.read_text(encoding="utf-8").strip()
                if not text.startswith("gitdir:"):
                    return None
                gitdir = (directory / text[len("gitdir:") :].strip()).resolve(strict=True)
            elif os.path.lexists(dotgit):
                return None
            else:
                continue
            try:
                pointer = (gitdir / "commondir").read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                return gitdir, gitdir
            return gitdir, (gitdir / pointer).resolve(strict=True)
        except (OSError, RuntimeError, UnicodeDecodeError):
            return None
    return None


def external_git_context(cwd: Any) -> bool:
    """Would a git call run in ``cwd`` read an external measurement repository?

    Always ``False`` when ``NEXUS_MEASURE_EXTERNAL_TARGET_ROOT`` was unset at
    start (the live Gateway): nothing is read, so live git calls are unchanged.
    In measurement mode it is ``True`` when ``cwd`` is under the measurement
    root, or the gitdir or common dir git would discover from ``cwd`` is (a
    Target worktree of an external Controller lives outside the root but its
    ``.git`` points into it), and it fails closed (``True``) whenever that
    cannot be told: an unresolvable root or path, no readable ``.git``, or an
    inherited variable that redirects git's repository discovery.
    """
    try:
        root = _measurement_root_at_start()
    except ExternalGitRefused:
        return True
    if root is None:
        return False
    if any(key in os.environ for key in ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE")):
        return True
    try:
        start = Path(cwd if cwd is not None else os.getcwd()).resolve(strict=True)
    except (OSError, RuntimeError):
        return True
    if _same_or_ancestor(start, root):
        return True
    discovered = _discovered_git_dirs(start)
    if discovered is None:
        return True
    return any(_same_or_ancestor(path, root) for path in discovered)


def hardened_git_argv(args: Sequence[str], *, attr_source: Optional[str] = None) -> list[str]:
    """``git [--attr-source=<base>] <caller -c pairs> <hardened -c> <command>``.

    Leading ``-c`` pairs of ``args`` (e.g. the candidate commit's author) stay,
    but the hardened values come after them, so they win (a caller's
    ``core.hooksPath`` is overridden by ``/dev/null``).
    """
    rest = list(args)
    leading: list[str] = []
    while len(rest) >= 2 and rest[0] == "-c":
        leading.extend(rest[:2])
        rest = rest[2:]
    prefix = [f"--attr-source={attr_source}"] if attr_source else []
    return ["git", *prefix, *leading, *HARDENED_GIT_CONFIG, *rest]


def _runner_environment(base: Optional[Mapping[str, str]]) -> dict[str, str]:
    environment = hardened_git_environment(base)
    environment["GIT_ATTR_NOSYSTEM"] = "1"
    return environment


def configured_driver_keys(cwd: Any, *, pin: Optional[Mapping[str, str]] = None) -> list[str]:
    """Config keys (local, worktree and included files) naming a content command.

    Read with the hardened flags and environment (plus ``pin``, the trusted
    ``GIT_DIR``/``GIT_WORK_TREE`` of a Target), so system and global config
    are not consulted and reading runs nothing.  Raises ``ExternalGitRefused``
    when the config cannot be read.
    """
    environment = _runner_environment(None)
    environment.update(pin or {})
    try:
        result = subprocess.run(
            [
                "git", *HARDENED_GIT_CONFIG,
                "config", "--name-only", "--get-regexp", GIT_DRIVER_CONFIG_REGEX,
            ],
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExternalGitRefused("EXTERNAL_TARGET_GIT_CONFIG_UNREADABLE") from exc
    if result.returncode == 1 and not result.stdout.strip():
        return []
    if result.returncode != 0:
        raise ExternalGitRefused("EXTERNAL_TARGET_GIT_CONFIG_UNREADABLE")
    return result.stdout.split()


def _info_attributes_present(directories: Iterable[Path]) -> bool:
    for directory in directories:
        try:
            if (Path(directory) / "info" / "attributes").stat().st_size > 0:
                return True
        except FileNotFoundError:
            continue
    return False


def run_hardened_git(
    args: Sequence[str],
    *,
    cwd: Any,
    env: Optional[Mapping[str, str]] = None,
    attr_source: Optional[str] = None,
    text: bool = True,
    pin: Optional[Mapping[str, str]] = None,
    metadata_dirs: Optional[Iterable[Path]] = None,
) -> subprocess.CompletedProcess:
    """Run one git command on an external Controller or its Target (#2749).

    Right before the command (not atomically) it refuses with
    ``EXTERNAL_TARGET_FILTER_DRIVER_PRESENT`` when a filter or textconv driver
    is configured or ``info/attributes`` is non-empty in the gitdir or common
    dir, so no clean/smudge filter runs even if one was planted after the
    lease.  ``pin`` (trusted ``GIT_DIR``/``GIT_WORK_TREE``/
    ``GIT_CEILING_DIRECTORIES`` of a verified Target) is set after the
    inherited ``GIT_*`` variables are dropped; ``metadata_dirs`` are the
    trusted gitdir and common dir (discovered from ``cwd`` when not given).
    The returned process is never checked here.
    """
    if metadata_dirs is None:
        start = Path(cwd if cwd is not None else os.getcwd())
        try:
            discovered = _discovered_git_dirs(start.resolve(strict=True))
        except (OSError, RuntimeError):
            discovered = None
        if discovered is None:
            raise ExternalGitRefused("EXTERNAL_TARGET_GIT_METADATA_UNREADABLE")
        metadata_dirs = discovered
    if _info_attributes_present(metadata_dirs):
        raise ExternalGitRefused(FILTER_DRIVER_PRESENT)
    if configured_driver_keys(cwd, pin=pin):
        raise ExternalGitRefused(FILTER_DRIVER_PRESENT)
    environment = _runner_environment(env)
    environment.update(pin or {})
    return subprocess.run(
        hardened_git_argv(args, attr_source=attr_source),
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=text,
        check=False,
    )


def measurement_mode_at_start() -> bool:
    """Whether the measurement root variable was set (non-blank) at start."""
    return bool(MEASURE_EXTERNAL_TARGET_ROOT_AT_START)


def discovered_git_dirs(path: Path) -> Optional[tuple[Path, Path]]:
    """Public form of the Python gitdir discovery (``None`` when unknown)."""
    try:
        return _discovered_git_dirs(Path(path).resolve(strict=True))
    except (OSError, RuntimeError):
        return None


def unscoped_git_needs_hardening(cwd: Any) -> bool:
    """For a git call made without a trusted Controller identity (#2749 r1).

    ``external_git_context``, and in measurement mode also any linked worktree
    (a ``.git`` file, i.e. a Target): its ``.git`` is worker-writable, so where
    it points proves nothing and the call is hardened.  ``False`` whenever the
    measurement mode is off.
    """
    if not measurement_mode_at_start():
        return False
    if external_git_context(cwd):
        return True
    try:
        start = Path(cwd if cwd is not None else os.getcwd()).resolve(strict=True)
    except (OSError, RuntimeError):
        return True
    for directory in (start, *start.parents):
        dotgit = directory / ".git"
        if dotgit.is_symlink() or dotgit.is_file():
            return True
        if dotgit.is_dir():
            return False
    return True


def _hardened_output(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *HARDENED_GIT_CONFIG, *args],
        cwd=repo_root,
        env=_runner_environment(None),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise ExternalGitRefused("EXTERNAL_TARGET_GIT_CONFIG_UNREADABLE")
    return result.stdout


def filter_driver_finding(repo_root: Path, base_revision: str) -> Optional[str]:
    """``EXTERNAL_TARGET_FILTER_DRIVER_PRESENT`` when a git filter could run, else ``None``.

    The repository refuses when its config defines a ``filter.*`` (or diff
    textconv/command) driver, a ``.gitattributes`` in ``base_revision``
    declares ``filter=``, or ``info/attributes`` in its gitdir or common dir is
    non-empty.  A probe failure is reported as the same refusal.  Only
    ``config``, ``rev-parse``, ``ls-tree`` and ``cat-file`` run: none of them
    run a filter.
    """
    try:
        if configured_driver_keys(repo_root):
            return FILTER_DRIVER_PRESENT
        for flag in ("--absolute-git-dir", "--git-common-dir"):
            raw = _hardened_output(repo_root, "rev-parse", "--path-format=absolute", flag)
            info = Path(raw.decode("utf-8").strip()) / "info" / "attributes"
            try:
                if info.stat().st_size > 0:
                    return FILTER_DRIVER_PRESENT
            except FileNotFoundError:
                pass
        listing = _hardened_output(
            repo_root, "ls-tree", "-r", "-z", "--full-tree", "--end-of-options", base_revision
        )
        for entry in listing.split(b"\0"):
            meta, _, name = entry.partition(b"\t")
            if name.rsplit(b"/", 1)[-1] != b".gitattributes":
                continue
            fields = meta.split()
            if len(fields) != 3 or fields[1] != b"blob":
                return FILTER_DRIVER_PRESENT
            blob = _hardened_output(repo_root, "cat-file", "blob", fields[2].decode("ascii"))
            if _ATTRIBUTE_FILTER.search(blob):
                return FILTER_DRIVER_PRESENT
    except (ExternalGitRefused, OSError, UnicodeDecodeError):
        return FILTER_DRIVER_PRESENT
    return None


def recheck_external_controller_at_lease(repo_root: Path, base_revision: str) -> None:
    """Lease-time re-check of an external Controller, just before git touches files.

    The Controller must still sit (with its gitdir and common dir) strictly
    inside the start-time measurement root and no git filter may be able to
    run (``filter_driver_finding``).  Raises ``ExternalGitRefused``.
    """
    root = _measurement_root_at_start()
    if root is None:
        raise ExternalGitRefused("EXTERNAL_TARGET_DISABLED")
    resolved = Path(repo_root).resolve()
    if not _strictly_inside(resolved, root):
        raise ExternalGitRefused("EXTERNAL_TARGET_OUTSIDE_ROOT")
    for flag in ("--absolute-git-dir", "--git-common-dir"):
        raw = _hardened_output(resolved, "rev-parse", "--path-format=absolute", flag)
        meta = Path(raw.decode("utf-8").strip()).resolve()
        if not _strictly_inside(meta, root):
            raise ExternalGitRefused("EXTERNAL_TARGET_GIT_METADATA_OUTSIDE_ROOT")
    finding = filter_driver_finding(resolved, base_revision)
    if finding is not None:
        raise ExternalGitRefused(finding)
