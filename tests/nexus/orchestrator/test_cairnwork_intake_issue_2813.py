from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.measure_external_target import (
    SUBMODULE_PRESENT,
    filter_driver_finding,
)


def _git(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def _init_repo(repo_dir: Path) -> Path:
    repo_dir.mkdir(parents=True, exist_ok=True)
    _git(repo_dir, "init", "-q", "-b", "main")
    _git(repo_dir, "config", "user.name", "t")
    _git(repo_dir, "config", "user.email", "t@example.invalid")
    _git(repo_dir, "config", "commit.gpgSign", "false")
    return repo_dir


def test_empty_gitmodules_is_accepted(tmp_path: Path) -> None:
    repo = tmp_path / "repo-empty-gitmodules"
    _init_repo(repo)
    gitmodules = repo / ".gitmodules"
    gitmodules.write_bytes(b"")
    _git(repo, "add", ".gitmodules")
    _git(repo, "commit", "-q", "-m", "commit empty .gitmodules")
    head_sha = _git(repo, "rev-parse", "HEAD")

    assert filter_driver_finding(repo, head_sha) is None


def test_declared_submodule_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo-declared-submodule"
    _init_repo(repo)
    gitmodules = repo / ".gitmodules"
    gitmodules.write_text(
        '[submodule "x"]\n\tpath = x\n\turl = https://example.invalid/repo.git\n',
        encoding="utf-8",
    )
    _git(repo, "add", ".gitmodules")
    _git(repo, "commit", "-q", "-m", "commit declared submodule")
    head_sha = _git(repo, "rev-parse", "HEAD")

    assert filter_driver_finding(repo, head_sha) == SUBMODULE_PRESENT
