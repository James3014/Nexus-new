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
# The checkout whose code this process runs.  Identity reports (/health
# git_head, runtime source drift, loaded tree) always describe this root, even
# when the canonical (Controller) root is a separate bound worktree (#1939).
LOADED_SOURCE_ROOT = DEFAULT_CANONICAL_SOURCE_ROOT
# A separate Controller worktree may differ from the loaded commit only by
# Task Card bind commits under this prefix (#1939).
CONTROLLER_BIND_PREFIX = "tasks/"

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
        # #1939: only a separate Controller worktree bound to the loaded commit
        # (Task Card bind commits only) may differ from the loaded checkout.
        reason = bound_controller_problem(resolved, loaded_source_root)
        if reason is not None:
            raise RuntimeError(f"NEXUS_CANONICAL_SOURCE_ROOT_SOURCE_MISMATCH:{reason}")

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


def _git_text(root: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def bound_controller_problem(controller: Path, loaded: Path) -> Optional[str]:
    """Why ``controller`` is not a valid Controller for the loaded checkout, else None.

    Valid means (#1939): a different worktree of the same repository whose HEAD
    descends from the loaded commit and differs from it only under ``tasks/``,
    so the Controller runs the loaded code plus Task Card bind commits only.
    """
    controller_common = _git_text(
        controller, "rev-parse", "--path-format=absolute", "--git-common-dir"
    )
    loaded_common = _git_text(loaded, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not controller_common or not loaded_common:
        return "COMMON_DIR_UNREADABLE"
    if not _same_physical_directory(Path(controller_common), Path(loaded_common)):
        return "DIFFERENT_REPOSITORY"
    # Same repository is not enough: the Controller must be its own registered
    # worktree, never an alias of the loaded checkout's gitdir (gitfile or
    # symlinked .git), or a bind commit would move the loaded HEAD again.
    controller_gitdir = _git_text(controller, "rev-parse", "--absolute-git-dir")
    loaded_gitdir = _git_text(loaded, "rev-parse", "--absolute-git-dir")
    if not controller_gitdir or not loaded_gitdir:
        return "GITDIR_UNREADABLE"
    if _same_physical_directory(Path(controller_gitdir), Path(loaded_gitdir)):
        return "CONTROLLER_SHARES_LOADED_GITDIR"
    listing = _git_text(loaded, "worktree", "list", "--porcelain")
    registered = [
        Path(line[len("worktree ") :])
        for line in (listing or "").splitlines()
        if line.startswith("worktree ")
    ]
    if not any(_same_physical_directory(path, controller) for path in registered):
        return "CONTROLLER_NOT_A_REGISTERED_WORKTREE"
    # The gitdir the Controller's .git points at must point back at this very
    # Controller, so a .git repointed at a third worktree's gitdir is refused.
    dot_git = controller / ".git"
    if dot_git.is_dir() and not dot_git.is_symlink():
        # A primary worktree: its gitdir is its own real .git directory, and
        # that directory is the repository's common gitdir (not a copy).
        if not _same_physical_directory(Path(controller_gitdir), dot_git) or not (
            _same_physical_directory(dot_git, Path(controller_common))
        ):
            return "CONTROLLER_GITDIR_NOT_ITS_OWN"
    else:
        try:
            back = (Path(controller_gitdir) / "gitdir").read_text(encoding="utf-8").strip()
        except OSError:
            return "CONTROLLER_GITDIR_NOT_ITS_OWN"
        if not _same_physical_directory(Path(back), dot_git):
            return "CONTROLLER_GITDIR_NOT_ITS_OWN"
    loaded_head = _git_text(loaded, "rev-parse", "--verify", "HEAD^{commit}")
    controller_head = _git_text(controller, "rev-parse", "--verify", "HEAD^{commit}")
    if not loaded_head or not controller_head:
        return "HEAD_UNREADABLE"
    if loaded_head != controller_head:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", loaded_head, controller_head],
            cwd=controller,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if ancestor.returncode != 0:
            return "LOADED_COMMIT_NOT_ANCESTOR"
        raw = subprocess.run(
            [
                "git",
                "diff",
                "--raw",
                "-z",
                "--no-renames",
                "--no-abbrev",
                loaded_head,
                controller_head,
                "--",
            ],
            cwd=controller,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if raw.returncode != 0:
            return "DIFF_UNREADABLE"
        reason = _bind_only_diff_problem(raw.stdout)
        if reason is not None:
            return reason
    return _controller_worktree_problem(controller)


_BIND_FILE_MODES = {"000000", "100644", "100755"}
_GIT_META_NAMES = {".gitattributes", ".gitmodules", ".gitignore"}


def _bind_only_diff_problem(raw: bytes) -> Optional[str]:
    """Every changed entry is a regular file under ``tasks/``.

    No symlink, gitlink (submodule) or git metadata file may enter through a
    bind commit (#1939).
    """
    fields = raw.split(b"\0")
    index = 0
    while index < len(fields) - 1:
        header = fields[index].decode("utf-8", errors="replace")
        path = fields[index + 1].decode("utf-8", errors="replace")
        index += 2
        if not header.startswith(":"):
            return "DIFF_UNPARSEABLE"
        parts = header[1:].split()
        if len(parts) < 5:
            return "DIFF_UNPARSEABLE"
        old_mode, new_mode = parts[0], parts[1]
        reason = _bind_path_problem(path)
        if reason is not None:
            return reason
        if old_mode not in _BIND_FILE_MODES or new_mode not in _BIND_FILE_MODES:
            return "CONTROLLER_BIND_NOT_REGULAR_FILE"
    return None


def _bind_path_problem(path: str) -> Optional[str]:
    """``tasks/<...>`` with plain segments and no git metadata name (any case)."""
    if not path.startswith(CONTROLLER_BIND_PREFIX):
        return "CONTROLLER_CHANGES_OUTSIDE_TASKS"
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts[1:]):
        return "CONTROLLER_BIND_PATH_INVALID"
    if any(part.casefold() in _GIT_META_NAMES for part in parts):
        return "CONTROLLER_BIND_GIT_METADATA"
    return None


def _controller_worktree_problem(controller: Path) -> Optional[str]:
    """Tracked files match HEAD; only untracked pending cards under ``tasks/`` may exist."""
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=no"],
        cwd=controller,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if status.returncode != 0:
        return "STATUS_UNREADABLE"
    for entry in status.stdout.split(b"\0"):
        if not entry:
            continue
        text = entry.decode("utf-8", errors="replace")
        if not text.startswith("?? " + CONTROLLER_BIND_PREFIX):
            return "CONTROLLER_WORKTREE_DIRTY"
        reason = _bind_path_problem(text[3:])
        if reason is not None:
            return reason
        if os.path.islink(controller / text[3:]):
            return "CONTROLLER_BIND_NOT_REGULAR_FILE"
    # ``git status`` hides edits to entries flagged assume-unchanged (lowercase
    # tag) or skip-worktree (``S``); every tracked entry must be a plain ``H``.
    flagged = subprocess.run(
        ["git", "ls-files", "-v", "-z"],
        cwd=controller,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if flagged.returncode != 0:
        return "INDEX_UNREADABLE"
    for entry in flagged.stdout.split(b"\0"):
        if entry and not entry.startswith(b"H "):
            return "CONTROLLER_INDEX_FLAGGED"
    return None


CANONICAL_SOURCE_ROOT = resolve_canonical_source_root()
# True only when the deployer bound a separate Controller worktree (#1939).
CONTROLLER_IS_SEPARATE = not _same_physical_directory(CANONICAL_SOURCE_ROOT, LOADED_SOURCE_ROOT)


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
