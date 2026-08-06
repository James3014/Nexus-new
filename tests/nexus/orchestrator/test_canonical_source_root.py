from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.canonical_source_root import (
    DEFAULT_CANONICAL_SOURCE_ROOT,
    resolve_canonical_source_root,
)


def test_unset_override_preserves_daily_canonical_default():
    assert resolve_canonical_source_root({}) == DEFAULT_CANONICAL_SOURCE_ROOT


def test_relative_override_fails_closed(tmp_path: Path):
    with pytest.raises(RuntimeError, match="NEXUS_CANONICAL_SOURCE_ROOT_MUST_BE_ABSOLUTE"):
        resolve_canonical_source_root({"NEXUS_CANONICAL_SOURCE_ROOT": "relative/root"}, source_root=tmp_path)


def test_missing_override_fails_closed(tmp_path: Path):
    missing = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="NEXUS_CANONICAL_SOURCE_ROOT_MISSING"):
        resolve_canonical_source_root({"NEXUS_CANONICAL_SOURCE_ROOT": str(missing)}, source_root=missing)


def test_override_cannot_rebind_loaded_code_to_another_directory(tmp_path: Path):
    loaded_root = tmp_path / "loaded"
    requested_root = tmp_path / "requested"
    loaded_root.mkdir()
    requested_root.mkdir()

    with pytest.raises(RuntimeError, match="NEXUS_CANONICAL_SOURCE_ROOT_SOURCE_MISMATCH"):
        resolve_canonical_source_root(
            {"NEXUS_CANONICAL_SOURCE_ROOT": str(requested_root)},
            source_root=loaded_root,
        )


def test_override_must_be_a_git_worktree_root(tmp_path: Path):
    with pytest.raises(RuntimeError, match="NEXUS_CANONICAL_SOURCE_ROOT_NOT_GIT_WORKTREE"):
        resolve_canonical_source_root(
            {"NEXUS_CANONICAL_SOURCE_ROOT": str(tmp_path)},
            source_root=tmp_path,
        )


def test_matching_git_worktree_root_is_accepted(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    assert resolve_canonical_source_root(
        {"NEXUS_CANONICAL_SOURCE_ROOT": str(tmp_path)},
        source_root=tmp_path,
    ) == tmp_path.resolve()
