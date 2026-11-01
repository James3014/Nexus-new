"""Git reads of the heal source repository start no program that repository names.

The reproduction phase binds its evidence to a workspace identity read from ``repo_dir`` after
the repro script ran there, and the C6BD pre-image fallback reads history from the same
repository. Both read it through the shared hardened runner: repository hooks, fsmonitor,
external diff, textconv and signature programs never start, a repository whose config names a
program the command line cannot switch off is not read, and neither is one not rooted at
``repo_dir``. For an ordinary repository the identity is unchanged.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

from nexus.experimental.c6bd_preimage_retry import (
    resolve_anchor_from_preimage,
    run_c6bd_preimage_retry,
)
from nexus.services.local_heal.reproduction import ReproductionRunner

_HOOKS = ("post-checkout", "post-commit", "post-index-change", "reference-transaction")


def _clean_git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"core.hooksPath={os.devnull}", *args],
        cwd=repo,
        env=_clean_git_env(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    monkeypatch.chdir(sentinel)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return tmp_path


def _repo(root: Path, name: str = "repo") -> Path:
    repo = root / name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Heal Test")
    _git(repo, "config", "user.email", "heal@example.com")
    _git(repo, "config", "commit.gpgSign", "false")
    (repo / "src.py").write_text("a = 0\nb = 0\nvalue = 1\n", encoding="utf-8")
    (repo / "other.py").write_text("other = 1\n", encoding="utf-8")
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "one")
    (repo / "src.py").write_text("a = 0\nb = 0\nvalue = 2\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "two")
    return repo


def _dirty(repo: Path) -> None:
    (repo / "src.py").write_text("value = 3\n", encoding="utf-8")
    (repo / "other.py").write_text("other = 2\n", encoding="utf-8")
    _git(repo, "add", "other.py")
    (repo / "blob.bin").write_bytes(b"\x00\x09\x02\xff")
    (repo / "new.txt").write_text("untracked\n", encoding="utf-8")


def _plant_programs(repo: Path, markers: Path) -> Path:
    """Hooks, fsmonitor, an external diff, a textconv driver and a signature program, each
    of which only touches a marker under tmp."""
    markers.mkdir()
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    for hook in _HOOKS:
        script = hooks / hook
        script.write_text(f"#!/bin/sh\ntouch '{markers}/hook.{hook}'\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    gpg = markers.parent / "gpg-program"
    gpg.write_text(f"#!/bin/sh\ntouch '{markers}/gpg'\nexit 1\n", encoding="utf-8")
    gpg.chmod(gpg.stat().st_mode | stat.S_IXUSR)
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("*.py diff=planted\n", encoding="utf-8")
    for key, value in (
        ("core.fsmonitor", f"touch '{markers}/fsmonitor'; true"),
        ("diff.external", f"sh -c \"touch '{markers}/diff.external'\" --"),
        ("diff.planted.textconv", f'sh -c "touch \'{markers}/textconv\'; cat \\"\\$1\\"" --'),
        ("log.showSignature", "true"),
        ("gpg.program", str(gpg)),
    ):
        _git(repo, "config", key, value)
    return markers


def _forge_signed_commit(repo: Path) -> None:
    """A commit carrying a signature header that rewrites src.py, so log shows it."""
    tree = _git(repo, "rev-parse", "HEAD^{tree}").strip()
    parent = _git(repo, "rev-parse", "HEAD~1").strip()
    body = (
        f"tree {tree}\nparent {parent}\nauthor a <a@a> 1 +0000\ncommitter a <a@a> 1 +0000\n"
        "gpgsig -----BEGIN PGP SIGNATURE-----\n x\n -----END PGP SIGNATURE-----\n\nsigned\n"
    )
    commit = subprocess.run(
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        cwd=repo,
        env=_clean_git_env(),
        input=body,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(repo, "update-ref", "refs/heads/signed", commit)


def _fired(markers: Path) -> list[str]:
    return sorted(path.name for path in markers.iterdir())


# --- workspace identity -------------------------------------------------------------------


def test_identity_of_an_ordinary_repository_is_unchanged(sandbox):
    repo = _repo(sandbox)
    _dirty(repo)
    head = _git(repo, "rev-parse", "HEAD").strip()
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    tracked = _git(repo, "diff", "--binary")
    staged = _git(repo, "diff", "--cached", "--binary")
    untracked = [("new.txt", "file:" + hashlib.sha256(b"untracked\n").hexdigest())]
    digest = hashlib.sha256(
        repr((head, status, tracked, staged, untracked)).encode("utf-8")
    ).hexdigest()

    assert ReproductionRunner(repo).workspace_identity() == (
        f"HEAD={head};WORKSPACE_SHA256={digest}",
        True,
    )


def test_identity_read_starts_no_hook_fsmonitor_external_diff_or_textconv(sandbox):
    repo = _repo(sandbox)
    _dirty(repo)
    markers = _plant_programs(repo, sandbox / "markers")

    ReproductionRunner(repo).workspace_identity()

    assert _fired(markers) == []


def test_identity_ignores_git_variables_in_the_environment(sandbox, monkeypatch):
    repo = _repo(sandbox)
    _dirty(repo)
    expected = ReproductionRunner(repo).workspace_identity()
    elsewhere = _repo(sandbox, "elsewhere")
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))

    assert ReproductionRunner(repo).workspace_identity() == expected


@pytest.mark.parametrize(
    ("key", "value", "attributes"),
    [
        ("hook.planted.command", "touch '{markers}/config-hook'", None),
        ("filter.planted.clean", "sh -c \"touch '{markers}/clean'; cat\"", "*.py filter=planted\n"),
    ],
    ids=["config-hook", "clean-filter"],
)
def test_identity_is_unbound_when_config_names_a_program(sandbox, key, value, attributes):
    repo = _repo(sandbox)
    _dirty(repo)
    markers = sandbox / "markers"
    markers.mkdir()
    _git(repo, "config", key, value.format(markers=markers))
    if key.startswith("hook."):
        _git(repo, "config", "hook.planted.event", "post-index-change")
    if attributes:
        (repo / ".git" / "info").mkdir(exist_ok=True)
        (repo / ".git" / "info" / "attributes").write_text(attributes, encoding="utf-8")

    assert ReproductionRunner(repo).workspace_identity() == ("", False)
    assert _fired(markers) == []


def test_identity_is_unbound_before_the_first_commit(sandbox):
    repo = sandbox / "empty"
    repo.mkdir()
    _git(repo, "init", "-q")

    assert ReproductionRunner(repo).workspace_identity() == ("", False)


def test_identity_is_unbound_below_the_repository_root(sandbox):
    repo = _repo(sandbox)
    (repo / "pkg").mkdir()

    assert ReproductionRunner(repo / "pkg").workspace_identity() == ("", False)


def test_identity_is_unbound_when_the_git_dir_lies_elsewhere(sandbox):
    repo = _repo(sandbox)
    moved = sandbox / "moved.git"
    (repo / ".git").rename(moved)
    (repo / ".git").write_text(f"gitdir: {moved}\n", encoding="utf-8")

    assert ReproductionRunner(repo).workspace_identity() == ("", False)


# --- C6BD pre-image history reads -----------------------------------------------------------


def test_preimage_anchor_is_found_in_an_ordinary_repository(sandbox):
    repo = _repo(sandbox)

    assert (
        resolve_anchor_from_preimage(
            repo_root=str(repo), target_file="src.py", search_text="value = 1", current_anchor=1
        )
        == 3
    )


def test_preimage_anchor_read_starts_no_textconv_or_signature_program(sandbox):
    repo = _repo(sandbox)
    _forge_signed_commit(repo)
    markers = _plant_programs(repo, sandbox / "markers")

    resolve_anchor_from_preimage(
        repo_root=str(repo), target_file="src.py", search_text="value = 1", current_anchor=1
    )

    assert _fired(markers) == []


def _apply_dir(root: Path) -> tuple[Path, Path]:
    work = root / "apply"
    work.mkdir()
    _git(work, "init", "-q")
    _git(work, "config", "user.name", "Heal Test")
    _git(work, "config", "user.email", "heal@example.com")
    patch = work / "candidate.patch"
    patch.write_text(
        "--- a/src.py\n+++ b/src.py\n@@ -3 +3 @@\n-value = 1\n+value = 9\n", encoding="utf-8"
    )
    return work, patch


def test_preimage_retry_applies_on_the_preimage_of_an_ordinary_repository(sandbox):
    repo = _repo(sandbox)
    work, patch = _apply_dir(sandbox)

    receipt = run_c6bd_preimage_retry(
        source_root=str(repo),
        target_file="src.py",
        search_text="value = 1",
        tmpdir=str(work),
        patch_file=str(patch),
        selected_candidate_hash="",
        task_id="t",
    )

    assert receipt is not None and receipt.patch_apply_status == "applied"
    assert (work / "src.py").read_text(encoding="utf-8") == "a = 0\nb = 0\nvalue = 9\n"


def test_preimage_retry_history_read_starts_no_textconv_or_signature_program(sandbox):
    repo = _repo(sandbox)
    _forge_signed_commit(repo)
    markers = _plant_programs(repo, sandbox / "markers")
    work, patch = _apply_dir(sandbox)

    run_c6bd_preimage_retry(
        source_root=str(repo),
        target_file="src.py",
        search_text="value = 1",
        tmpdir=str(work),
        patch_file=str(patch),
        selected_candidate_hash="",
        task_id="t",
    )

    assert _fired(markers) == []


def test_preimage_reads_skip_a_repository_whose_config_names_a_hook(sandbox):
    repo = _repo(sandbox)
    markers = sandbox / "markers"
    markers.mkdir()
    _git(repo, "config", "hook.planted.command", f"touch '{markers}/config-hook'")
    _git(repo, "config", "hook.planted.event", "post-index-change")
    work, patch = _apply_dir(sandbox)

    assert (
        resolve_anchor_from_preimage(
            repo_root=str(repo), target_file="src.py", search_text="value = 1", current_anchor=1
        )
        == 1
    )
    assert (
        run_c6bd_preimage_retry(
            source_root=str(repo),
            target_file="src.py",
            search_text="value = 1",
            tmpdir=str(work),
            patch_file=str(patch),
            selected_candidate_hash="",
            task_id="t",
        )
        is None
    )
    assert _fired(markers) == []


def test_preimage_reads_skip_a_repository_whose_git_dir_lies_elsewhere(sandbox):
    repo = _repo(sandbox)
    moved = sandbox / "moved.git"
    (repo / ".git").rename(moved)
    (repo / ".git").write_text(f"gitdir: {moved}\n", encoding="utf-8")
    work, patch = _apply_dir(sandbox)

    assert (
        resolve_anchor_from_preimage(
            repo_root=str(repo), target_file="src.py", search_text="value = 1", current_anchor=1
        )
        == 1
    )
    assert (
        run_c6bd_preimage_retry(
            source_root=str(repo),
            target_file="src.py",
            search_text="value = 1",
            tmpdir=str(work),
            patch_file=str(patch),
            selected_candidate_hash="",
            task_id="t",
        )
        is None
    )
