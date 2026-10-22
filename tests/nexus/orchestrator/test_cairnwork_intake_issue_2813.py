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


def _commit_gitmodules(repo: Path, content: bytes) -> str:
    (repo / ".gitmodules").write_bytes(content)
    _git(repo, "add", ".gitmodules")
    _git(repo, "commit", "-q", "-m", "commit .gitmodules")
    return _git(repo, "rev-parse", "HEAD")


def test_whitespace_only_gitmodules_is_accepted(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo-whitespace-gitmodules")
    assert filter_driver_finding(repo, _commit_gitmodules(repo, b" \n\t\r\n\n")) is None


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b'[submodule "x"] path = x\n', id="key-on-header-line"),
        pytest.param(b'\xef\xbb\xbf[submodule "x"]\n\tpath = x\n', id="utf8-bom"),
        pytest.param(b'[submodule "x"]\n\turl = a\\\n[other]\n\tpath = x\n', id="continuation"),
        pytest.param(b'[submodule "x"]\n\turl = a\r[other]\n\tpath = x\n', id="bare-cr"),
        pytest.param(b"[submodule.x]\n\tpath = x\n", id="legacy-subsection"),
        pytest.param(b"# only a comment\n", id="comment-only"),
    ],
)
def test_gitmodules_with_any_content_is_refused(tmp_path: Path, content: bytes) -> None:
    # Hand-parsing git config syntax diverges from git (#2856 review), so
    # anything but whitespace is refused rather than interpreted.
    repo = _init_repo(tmp_path / "repo-gitmodules-content")
    assert filter_driver_finding(repo, _commit_gitmodules(repo, content)) == SUBMODULE_PRESENT


def test_gitlink_without_gitmodules_is_refused(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo-gitlink")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "base")
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},sub")
    _git(repo, "commit", "-q", "-m", "add gitlink")
    assert filter_driver_finding(repo, _git(repo, "rev-parse", "HEAD")) == SUBMODULE_PRESENT
