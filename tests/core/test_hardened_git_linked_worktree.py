"""nexus.core.hardened_git: linked worktree check and diff refusal.

Every repo here is a fresh ``git init`` under ``tmp_path``; each test moves the cwd to a
sentinel directory first.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus.core import hardened_git


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    monkeypatch.chdir(sentinel)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return tmp_path


def _controller_and_worktree(env: Path) -> tuple[Path, Path]:
    repo = env / "controller"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.invalid")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-qm", "base")
    worktree = env / "wt"
    _git(repo, "worktree", "add", "-q", "--detach", str(worktree))
    return repo, worktree


def test_a_linked_worktree_resolves_to_its_registration_in_the_controller(env):
    repo, worktree = _controller_and_worktree(env)

    git_dir = hardened_git.linked_worktree_git_dir(worktree, repo)

    assert git_dir == (repo / ".git" / "worktrees" / "wt").resolve()
    assert hardened_git.linked_worktree_git_dir(worktree) == git_dir
    head = hardened_git.run_hardened_git(worktree, "rev-parse", "HEAD", git_dir=git_dir)
    assert head.stdout.strip() == _git(repo, "rev-parse", "HEAD")


def test_a_git_pointer_into_the_worktree_itself_is_not_a_registration(env):
    repo, worktree = _controller_and_worktree(env)
    planted = worktree / "planted" / "worktrees" / "wt"
    planted.mkdir(parents=True)
    (planted / "commondir").write_text("../..\n", encoding="utf-8")
    (planted / "gitdir").write_text(f"{worktree / '.git'}\n", encoding="utf-8")
    (worktree / ".git").write_text(f"gitdir: {planted}\n", encoding="utf-8")

    assert hardened_git.linked_worktree_git_dir(worktree) is None
    assert hardened_git.linked_worktree_git_dir(worktree, repo) is None


def test_a_registration_in_another_controller_or_not_pointing_back_is_refused(env):
    repo, worktree = _controller_and_worktree(env)
    other = env / "other"
    other.mkdir()
    _git(other, "init", "-q")
    assert hardened_git.linked_worktree_git_dir(worktree, other) is None

    registration = repo / ".git" / "worktrees" / "wt"
    (registration / "gitdir").write_text(f"{env / 'elsewhere' / '.git'}\n", encoding="utf-8")
    assert hardened_git.linked_worktree_git_dir(worktree, repo) is None


def test_a_symlinked_pointer_or_a_plain_repository_is_not_a_linked_worktree(env):
    repo, worktree = _controller_and_worktree(env)
    assert hardened_git.linked_worktree_git_dir(repo) is None

    pointer = env / "pointer"
    pointer.write_text((worktree / ".git").read_text(encoding="utf-8"), encoding="utf-8")
    (worktree / ".git").unlink()
    (worktree / ".git").symlink_to(pointer)
    assert hardened_git.linked_worktree_git_dir(worktree, repo) is None


def test_the_runner_honours_a_caller_timeout(env, monkeypatch):
    _repo, worktree = _controller_and_worktree(env)
    seen: dict[str, object] = {}
    real_run = subprocess.run

    def recording_run(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(hardened_git.subprocess, "run", recording_run)
    hardened_git.run_hardened_git(worktree, "rev-parse", "HEAD", timeout=7.5)
    assert seen["timeout"] == 7.5
    hardened_git.run_hardened_git(worktree, "rev-parse", "HEAD")
    assert seen["timeout"] == hardened_git.GIT_TIMEOUT_S


@pytest.mark.parametrize(
    ("name", "refused"),
    [
        ("diff.renames", False),
        ("diff.algorithm", False),
        ("diff.mark.cachetextconv", False),
        ("diff.external", True),
        ("diff.mark.textconv", True),
        ("diff.mark.command", True),
    ],
)
def test_only_diff_keys_that_name_a_program_are_refused(name, refused):
    assert hardened_git.config_names_a_repository_program([name]) is refused
