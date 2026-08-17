"""Resolve the process-owned canonical source root for Nexus runtime code."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Mapping, Optional

CANONICAL_SOURCE_ROOT_ENV = "NEXUS_CANONICAL_SOURCE_ROOT"
# Derive the repository root from this module's own location instead of a
# machine-specific developer path. parents: [0]=orchestrator, [1]=nexus,
# [2]=repository root.
DEFAULT_CANONICAL_SOURCE_ROOT = Path(__file__).resolve().parents[2]


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
    if resolved != loaded_source_root:
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
    if Path(git_root.stdout.strip()).resolve() != resolved:
        raise RuntimeError("NEXUS_CANONICAL_SOURCE_ROOT_NOT_GIT_WORKTREE")
    return resolved


CANONICAL_SOURCE_ROOT = resolve_canonical_source_root()
