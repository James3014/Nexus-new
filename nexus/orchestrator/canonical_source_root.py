"""Resolve the process-owned canonical source root for Nexus runtime code."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Mapping, Optional

CANONICAL_SOURCE_ROOT_ENV = "NEXUS_CANONICAL_SOURCE_ROOT"
# Derive the repository root from this module's own location instead of a
# machine-specific developer path. parents: [0]=orchestrator, [1]=nexus,
# [2]=repository root.
DEFAULT_CANONICAL_SOURCE_ROOT = Path(__file__).resolve().parents[2]

# Regex patterns for the supported GitHub remote URL forms.
_HTTPS_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_SCP_RE = re.compile(
    r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_SSH_RE = re.compile(
    r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_PLAIN_RE = re.compile(
    r"^(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def _normalize_github_identity(value: str, *, allow_plain: bool = False) -> str:
    """Return lowercased ``owner/repo`` for a supported GitHub remote form.

    Raises ``RuntimeError`` for any non-GitHub origin or malformed identity so
    that callers fail closed rather than silently accepting unknown forms.

    Parameters
    ----------
    value:
        A GitHub remote URL or, when *allow_plain* is ``True``, a plain
        ``OWNER/REPO`` slug.
    allow_plain:
        When ``True`` a bare ``OWNER/REPO`` (without a URL scheme) is also
        accepted.  This is appropriate for the *expected_repository* argument
        only; origin URLs must always carry an explicit scheme.
    """
    stripped = value.strip().rstrip("/")
    for pattern in (_HTTPS_RE, _SCP_RE, _SSH_RE):
        m = pattern.match(stripped)
        if m:
            return f"{m.group('owner').lower()}/{m.group('repo').lower()}"
    if allow_plain:
        m = _PLAIN_RE.match(stripped)
        if m:
            return f"{m.group('owner').lower()}/{m.group('repo').lower()}"
    raise RuntimeError(f"RDC_REPO_ROOT_IDENTITY_INVALID: {value!r}")


def _same_physical_directory(left: Path, right: Path) -> bool:
    """Return True when two path spellings identify the same physical directory."""
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def resolve_canonical_source_root(
    env: Optional[Mapping[str, str]] = None,
    *,
    source_root: Optional[Path] = None,
) -> Path:
    """Return the default root or a fail-closed, source-bound activation root."""
    environment = os.environ if env is None else env
    raw = str(environment.get(CANONICAL_SOURCE_ROOT_ENV, "") or "").strip()
    if not raw:
        return DEFAULT_CANONICAL_SOURCE_ROOT

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise RuntimeError("NEXUS_CANONICAL_SOURCE_ROOT_MUST_BE_ABSOLUTE")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("NEXUS_CANONICAL_SOURCE_ROOT_MISSING") from exc
    if not resolved.is_dir():
        raise RuntimeError("NEXUS_CANONICAL_SOURCE_ROOT_NOT_DIRECTORY")

    loaded_source_root = (source_root or Path(__file__).resolve().parents[2]).resolve()
    if not _same_physical_directory(resolved, loaded_source_root):
        raise RuntimeError("NEXUS_CANONICAL_SOURCE_ROOT_SOURCE_MISMATCH")

    try:
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=resolved,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("NEXUS_CANONICAL_SOURCE_ROOT_NOT_GIT_WORKTREE") from exc
    if git_root.returncode != 0 or not git_root.stdout.strip():
        raise RuntimeError("NEXUS_CANONICAL_SOURCE_ROOT_NOT_GIT_WORKTREE")
    if not _same_physical_directory(Path(git_root.stdout.strip()), resolved):
        raise RuntimeError("NEXUS_CANONICAL_SOURCE_ROOT_NOT_GIT_WORKTREE")
    return resolved


CANONICAL_SOURCE_ROOT = resolve_canonical_source_root()


def resolve_rdc_repo_root(
    *,
    expected_repository: str,
    canonical_root: Optional[Path] = None,
) -> Path:
    """Resolve and validate the RDC canonical repository root.

    Parameters
    ----------
    expected_repository:
        The repository identity to bind to.  Accepts plain ``OWNER/REPO``,
        HTTPS, SCP-style SSH, or ``ssh://`` GitHub URLs.
    canonical_root:
        The directory to validate.  When ``None`` the module-level
        ``CANONICAL_SOURCE_ROOT`` constant is used.  No filesystem search,
        no cwd fallback, no heuristics.

    Returns
    -------
    Path
        The resolved, validated repository root.

    Raises
    ------
    RuntimeError
        One of the ``RDC_REPO_ROOT_*`` sentinel strings depending on the
        failure mode, so that callers can fail closed.
    """
    root = canonical_root if canonical_root is not None else CANONICAL_SOURCE_ROOT

    # Expand and resolve — strict=True means the path must exist.
    try:
        resolved = Path(root).expanduser().resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("RDC_REPO_ROOT_MISSING") from exc

    if not resolved.is_dir():
        raise RuntimeError("RDC_REPO_ROOT_NOT_DIRECTORY")

    # Verify the path is the root of a git repository.
    try:
        git_top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=resolved,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("RDC_REPO_ROOT_NOT_GIT_REPO") from exc

    if git_top.returncode != 0 or not git_top.stdout.strip():
        raise RuntimeError("RDC_REPO_ROOT_NOT_GIT_REPO")
    if not _same_physical_directory(Path(git_top.stdout.strip()), resolved):
        raise RuntimeError("RDC_REPO_ROOT_NOT_GIT_REPO")

    # Read the origin remote URL.
    try:
        git_remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=resolved,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("RDC_REPO_ROOT_REMOTE_UNREADABLE") from exc

    if git_remote.returncode != 0 or not git_remote.stdout.strip():
        raise RuntimeError("RDC_REPO_ROOT_REMOTE_UNREADABLE")

    origin_url = git_remote.stdout.strip()

    # Normalize both sides and compare lower-case owner/repo.
    try:
        normalized_origin = _normalize_github_identity(origin_url, allow_plain=False)
    except RuntimeError as exc:
        raise RuntimeError("RDC_REPO_ROOT_REMOTE_UNREADABLE") from exc

    try:
        normalized_expected = _normalize_github_identity(expected_repository, allow_plain=True)
    except RuntimeError as exc:
        raise RuntimeError("RDC_REPO_ROOT_REMOTE_MISMATCH") from exc

    if normalized_origin != normalized_expected:
        raise RuntimeError("RDC_REPO_ROOT_REMOTE_MISMATCH")

    return resolved
