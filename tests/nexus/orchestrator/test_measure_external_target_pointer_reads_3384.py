"""Refs #3384: the measurement-mode git discovery reads pointer files through the bounded reader."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from nexus.orchestrator import measure_external_target as met


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _linked(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "commit", "-q", "--allow-empty", "-m", "x")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", "--detach", str(wt))
    return main, wt


def test_plain_repo_and_linked_worktree_are_found(tmp_path: Path) -> None:
    main, wt = _linked(tmp_path)
    gd, common = met._discovered_git_dirs(main)
    assert gd == common == (main / ".git").resolve()
    gd, common = met._discovered_git_dirs(wt)
    assert gd.parent.name == "worktrees"
    assert common == (main / ".git").resolve()


def _run_isolated(code: str, timeout: float = 20) -> subprocess.CompletedProcess[str]:
    # A subprocess with a timeout: a regression that opens a FIFO blocking fails, not hangs CI.
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )


def test_fifo_commondir_does_not_hang_and_fails_closed(tmp_path: Path) -> None:
    main, wt = _linked(tmp_path)
    gd, _ = met._discovered_git_dirs(wt)
    (gd / "commondir").unlink()
    os.mkfifo(gd / "commondir")
    proc = _run_isolated(
        f"""
        from pathlib import Path
        from nexus.orchestrator import measure_external_target as met
        print(met._discovered_git_dirs(Path({str(wt)!r})))
        """
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "None"


def test_huge_commondir_and_dotgit_file_fail_closed(tmp_path: Path) -> None:
    main, wt = _linked(tmp_path)
    gd, _ = met._discovered_git_dirs(wt)
    (gd / "commondir").write_text("../.." + " " * 10000 + "\n", encoding="utf-8")
    assert met._discovered_git_dirs(wt) is None
    big = tmp_path / "big"
    big.mkdir()
    (big / ".git").write_text("gitdir: " + "a" * 10000, encoding="utf-8")
    assert met._discovered_git_dirs(big) is None


def test_missing_commondir_still_falls_back_to_gitdir(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    assert not (repo / ".git" / "commondir").exists()
    gd, common = met._discovered_git_dirs(repo)
    assert gd == common
