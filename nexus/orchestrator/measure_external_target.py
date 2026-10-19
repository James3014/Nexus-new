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
  external repository is refused here, before any planner or provider work.

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
from typing import Any, Iterable, Mapping, Optional

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


class ExternalTargetError(ValueError):
    """A refused external target; ``str(exc)`` is the stable code."""


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


def _git_environment() -> dict[str, str]:
    """Inherited env without any ``GIT_*`` variable; no system/global config, no prompt."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    })
    return environment


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


def _lexical_key(path: Path) -> tuple[str, ...]:
    # APFS/HFS+ are case-insensitive by default: compare case-folded on darwin (#2742).
    parts = path.parts
    return tuple(part.casefold() for part in parts) if sys.platform == "darwin" else parts


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
