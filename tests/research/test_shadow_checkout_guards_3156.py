"""Each defensive check of ``_verified_persistent_shadow_git_dir`` is pinned on its own (#3156).

The gitfile, config and revision checks all end the reuse of a persistent shadow checkout.
Each test trips exactly one of them and matches that check's own error, so dropping one check
cannot hide behind another.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nexus.research import hybrid_replication_live as live


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgSign=false", *args],
        cwd=cwd,
        env=_env(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def shadow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Shadow Test")
    _git(repo, "config", "user.email", "shadow@test.invalid")
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-qm", "base")
    revision = _git(repo, "rev-parse", "HEAD")
    source = tmp_path / "task" / "source"
    source.parent.mkdir()
    live._prepare_shadow_checkout(repo=repo, revision=revision, source=source)
    return source, revision


def test_intact_shadow_checkout_is_accepted(shadow: tuple[Path, str]) -> None:
    source, revision = shadow
    assert live._verified_persistent_shadow_git_dir(source, revision) == (
        live._shadow_git_dir(source)
    )


def test_gitfile_pointing_at_another_git_dir_is_refused(
    shadow: tuple[Path, str], tmp_path: Path
) -> None:
    source, revision = shadow
    other = tmp_path / "other.git"
    _git(tmp_path, "init", "-q", "--bare", str(other))
    (source / ".git").write_text(f"gitdir: {other}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="persistent_shadow_gitfile_invalid"):
        live._verified_persistent_shadow_git_dir(source, revision)


def test_config_that_names_a_program_is_refused(shadow: tuple[Path, str]) -> None:
    source, revision = shadow
    git_dir = live._shadow_git_dir(source)
    _git(source, "config", "--file", str(git_dir / "config"), "diff.external", "touch planted")

    with pytest.raises(RuntimeError, match="persistent_shadow_config_refused"):
        live._verified_persistent_shadow_git_dir(source, revision)


def test_shadow_checkout_moved_off_its_revision_is_refused(shadow: tuple[Path, str]) -> None:
    source, revision = shadow
    (source / "f.txt").write_text("b\n", encoding="utf-8")
    _git(source, "-c", "user.name=T", "-c", "user.email=t@t.invalid", "commit", "-qam", "later")
    assert _git(source, "rev-parse", "HEAD") != revision

    with pytest.raises(RuntimeError, match="persistent_shadow_revision_mismatch"):
        live._verified_persistent_shadow_git_dir(source, revision)


@pytest.mark.parametrize("kind", ["symlink_to_intact_gitfile", "directory"])
def test_gitfile_that_is_not_a_plain_file_is_refused(
    shadow: tuple[Path, str], tmp_path: Path, kind: str
) -> None:
    source, revision = shadow
    gitfile = source / ".git"
    if kind == "symlink_to_intact_gitfile":
        real = tmp_path / "real-gitfile"
        gitfile.rename(real)
        gitfile.symlink_to(real)
    else:
        gitfile.unlink()
        gitfile.mkdir()

    with pytest.raises(RuntimeError, match="persistent_shadow_gitfile_invalid"):
        live._verified_persistent_shadow_git_dir(source, revision)
