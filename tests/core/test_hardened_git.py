"""Restore and rollback paths run git only through nexus.core.hardened_git.

Each site runs git in a directory whose repository a candidate may have written: the
candidate restore, the action-protocol rollback, the transaction rollback and the heal
workspace reset. Every repo here is a fresh ``git init`` under ``tmp_path``; each test first
moves the cwd to a sentinel directory, and every hook or filter script only touches a marker
file under ``tmp_path``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import MagicMock

import pytest

from nexus.core import hardened_git
from nexus.core.engine.nexus_transaction import TransactionManager
from nexus.services.local_heal.action_protocol import ActionProtocol
from nexus.services.local_heal.candidate_search import CandidatePatchSearcher
from nexus.services.local_heal.orchestrator import HealOrchestrator

DIRTY_EDIT = "x = 2  # uncommitted edit\n"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _repo_with_local_work(root: Path) -> Path:
    """A git repo with one uncommitted edit (notes.py)."""
    root.mkdir(parents=True)
    (root / "notes.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    (root / "notes.py").write_text(DIRTY_EDIT, encoding="utf-8")
    return root


def _restore_candidate_files(repo: Path) -> Any:
    searcher = CandidatePatchSearcher(parser=MagicMock(), patch_applier=MagicMock())
    return searcher._restore_files(repo, [cast(Any, SimpleNamespace(file_path="notes.py"))])


def _roll_back_action_protocol(repo: Path) -> Any:
    protocol = ActionProtocol(
        protocol_id="p",
        protocol_type="MULTI_STEP_LOCAL_EDIT",
        task_id="t",
        files_involved=["notes.py"],
    )
    return protocol.rollback(repo)


def _roll_back_transaction(repo: Path) -> Any:
    return TransactionManager(str(repo)).audit_rollback("t")


def _reset_heal_workspace(repo: Path) -> Any:
    ctx = SimpleNamespace(op=SimpleNamespace(repo_dir=repo))
    return HealOrchestrator._reset_workspace(cast(Any, SimpleNamespace()), cast(Any, ctx))


SITES: dict[str, Callable[[Path], Any]] = {
    "candidate_restore": _restore_candidate_files,
    "action_protocol_rollback": _roll_back_action_protocol,
    "transaction_rollback": _roll_back_transaction,
}
# What each site returns when it restored nothing (the transaction reports failure).
REFUSED = {
    "candidate_restore": None,
    "action_protocol_rollback": None,
    "transaction_rollback": False,
    "heal_workspace_reset": None,
}
RESTORED = {
    "candidate_restore": None,
    "action_protocol_rollback": None,
    "transaction_rollback": True,
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "SENTINEL").write_text("cwd\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("NEXUS_ROOT", raising=False)
    yield tmp_path
    assert (cwd / "SENTINEL").read_text(encoding="utf-8") == "cwd\n"


def _marker_script(tmp_path: Path, name: str, marker: Path, *, passthrough: bool = False) -> Path:
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    script = tools / name
    script.write_text(f'#!/bin/sh\ntouch "{marker}"\n' + ("cat\n" if passthrough else ""))
    script.chmod(0o755)
    return script


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_do_not_run_a_post_checkout_hook_the_candidate_created(env, site):
    repo = _repo_with_local_work(env / "repo")
    marker = env / "hook-ran"
    # post-checkout fires on a path checkout; reset --hard fires the other two instead.
    for hook in ("post-checkout", "reference-transaction", "post-index-change"):
        path = repo / ".git" / "hooks" / hook
        path.write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding="utf-8")
        path.chmod(0o755)

    assert SITES[site](repo) == RESTORED[site]

    assert not marker.exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_refuse_a_repository_with_a_candidate_configured_filter(env, site):
    repo = _repo_with_local_work(env / "repo")
    (repo / ".gitattributes").write_text("*.py filter=mark\n", encoding="utf-8")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-qm", "attributes", "--", ".gitattributes")
    marker = env / "filter-ran"
    script = _marker_script(env, "filter.sh", marker, passthrough=True)
    with open(repo / ".git" / "config", "a", encoding="utf-8") as config:
        config.write(f'[filter "mark"]\n\tsmudge = {script}\n\tclean = {script}\n')

    assert SITES[site](repo) == REFUSED[site]

    assert not marker.exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_still_restore_the_candidate_edit(env, site):
    repo = _repo_with_local_work(env / "repo")
    (repo / "untracked.py").write_text("y\n", encoding="utf-8")

    assert SITES[site](repo) == RESTORED[site]

    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"
    # Only the transaction rollback cleans untracked files.
    assert (repo / "untracked.py").exists() == (site != "transaction_rollback")


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_leave_a_work_tree_named_elsewhere_untouched(env, site):
    repo = _repo_with_local_work(env / "repo")
    other = env / "other"
    other.mkdir()
    (other / "notes.py").write_text("other work\n", encoding="utf-8")
    (other / "keep.txt").write_text("keep\n", encoding="utf-8")
    _git(repo, "config", "core.worktree", str(other))

    assert SITES[site](repo) == REFUSED[site]

    assert (other / "notes.py").read_text(encoding="utf-8") == "other work\n"
    assert (other / "keep.txt").exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(REFUSED))
def test_every_restore_site_asks_the_shared_hardened_git_config_check(env, site, monkeypatch):
    repo = _repo_with_local_work(env / "repo")
    seen: list[list[str]] = []

    def refuse(names: list[str]) -> bool:
        seen.append(list(names))
        return True

    monkeypatch.setattr(hardened_git, "config_names_a_repository_program", refuse)
    run = {**SITES, "heal_workspace_reset": _reset_heal_workspace}[site]

    assert run(repo) == REFUSED[site]

    assert len(seen) == 1 and "core.bare" in seen[0]
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


ALL_SITES = {**SITES, "heal_workspace_reset": _reset_heal_workspace}


@pytest.mark.parametrize("site", sorted(ALL_SITES))
def test_restore_and_rollback_refuse_a_repository_with_a_config_defined_hook(env, site):
    repo = _repo_with_local_work(env / "repo")
    marker = env / "config-hook-ran"
    # core.hooksPath does not cover hooks named in config (hook.<name>.command).
    _git(repo, "config", "hook.mark.command", f'touch "{marker}"')
    for event in ("post-checkout", "reference-transaction", "post-index-change"):
        _git(repo, "config", "--add", "hook.mark.event", event)

    assert ALL_SITES[site](repo) == REFUSED[site]

    assert not marker.exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_leave_a_git_dir_kept_elsewhere_untouched(env, site):
    repo = _repo_with_local_work(env / "repo")
    outside = env / "outside.git"
    (repo / ".git").rename(outside)
    (repo / ".git").write_text(f"gitdir: {outside}\n", encoding="utf-8")
    index = (outside / "index").read_bytes()

    assert SITES[site](repo) == REFUSED[site]

    assert (outside / "index").read_bytes() == index
    assert not (outside / "ORIG_HEAD").exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_act_on_their_repo_under_a_foreign_git_environment(
    env, site, monkeypatch
):
    repo = _repo_with_local_work(env / "repo")
    elsewhere = _repo_with_local_work(env / "elsewhere")
    (elsewhere / "untracked.py").write_text("keep\n", encoding="utf-8")
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))

    assert SITES[site](repo) == RESTORED[site]

    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (elsewhere / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT
    assert (elsewhere / "untracked.py").exists()


@pytest.mark.parametrize("outcome", ["error", "timeout"])
def test_an_unreadable_repository_config_counts_as_naming_a_program(env, monkeypatch, outcome):
    def failing_git(repo_dir: Path, *args: str, **_: Any) -> subprocess.CompletedProcess[str]:
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(["git", *args], hardened_git.GIT_TIMEOUT_S)
        return subprocess.CompletedProcess(["git", *args], 1, "", "error")

    monkeypatch.setattr(hardened_git, "run_hardened_git", failing_git)

    assert hardened_git.repository_config_can_start_a_program(env) is True


def test_reset_clears_a_stale_index_lock_a_timed_out_step_left_and_the_next_reset_restores(
    env, monkeypatch, caplog
):
    from nexus.services.local_heal import orchestrator

    repo = _repo_with_local_work(env / "repo")
    lock = repo / ".git" / "index.lock"
    real_git = orchestrator.run_hardened_git

    def checkout_times_out(
        repo_dir: Path, *args: str, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if args[:1] == ("checkout",):
            lock.write_text("", encoding="utf-8")  # what a killed checkout leaves behind
            raise subprocess.TimeoutExpired(["git", *args], hardened_git.GIT_TIMEOUT_S)
        return real_git(repo_dir, *args, **kwargs)

    monkeypatch.setattr(orchestrator, "run_hardened_git", checkout_times_out)
    with caplog.at_level("WARNING", logger="nexus.services.local_heal.orchestrator"):
        _reset_heal_workspace(repo)

    assert not lock.exists()
    assert "removed a stale index.lock" in caplog.text
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT

    monkeypatch.setattr(orchestrator, "run_hardened_git", real_git)
    _reset_heal_workspace(repo)

    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"


def test_a_timed_out_git_call_no_longer_counts_as_running(env, monkeypatch):
    repo = _repo_with_local_work(env / "repo")
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")

    def timed_out(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert repo.resolve() in hardened_git._RUNNING
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(hardened_git.subprocess, "run", timed_out)
    with pytest.raises(subprocess.TimeoutExpired):
        hardened_git.run_hardened_git(repo, "checkout", "--", ".")

    assert repo.resolve() not in hardened_git._RUNNING
    assert hardened_git.clear_stale_index_lock(repo, repo / ".git") is True
    assert not (repo / ".git" / "index.lock").exists()


def test_an_index_lock_is_kept_while_a_git_call_still_runs_in_the_repo(env, monkeypatch):
    repo = _repo_with_local_work(env / "repo")
    lock = repo / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")
    monkeypatch.setitem(hardened_git._RUNNING, repo.resolve(), 1)

    assert hardened_git.clear_stale_index_lock(repo, repo / ".git") is False
    assert lock.exists()


def test_an_index_lock_in_a_git_dir_outside_the_repo_is_kept(env):
    repo = _repo_with_local_work(env / "repo")
    outside = env / "outside.git"
    outside.mkdir()
    lock = outside / "index.lock"
    lock.write_text("", encoding="utf-8")

    assert hardened_git.clear_stale_index_lock(repo, outside) is False
    assert lock.exists()


def test_hardened_git_runs_no_external_diff_or_textconv_driver_the_repository_names(env):
    repo = _repo_with_local_work(env / "repo")
    (repo / ".gitattributes").write_text("*.py diff=mark\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "edit")
    (repo / "notes.py").write_text(DIRTY_EDIT + "y = 3\n", encoding="utf-8")
    external_ran, textconv_ran = env / "external-diff-ran", env / "textconv-ran"
    _git(repo, "config", "diff.external", str(_marker_script(env, "ext.sh", external_ran)))
    textconv = _marker_script(env, "textconv.sh", textconv_ran, passthrough=True)
    _git(repo, "config", "diff.mark.textconv", str(textconv))

    for args in (("diff",), ("show", "HEAD"), ("log", "-p", "-1")):
        assert hardened_git.run_hardened_git(repo, *args).returncode == 0

    assert not external_ran.exists()
    assert not textconv_ran.exists()
    # The restore and rollback paths refuse such a repository outright.
    assert hardened_git.repository_config_can_start_a_program(repo) is True


def test_a_hardened_commit_runs_no_commit_hook_and_is_not_signed(env):
    repo = _repo_with_local_work(env / "repo")
    marker = env / "program-ran"
    script = _marker_script(env, "program.sh", marker)
    _git(repo, "config", "commit.gpgSign", "true")
    _git(repo, "config", "gpg.program", str(script))
    _git(repo, "config", "hook.mark.command", str(script))
    for event in ("pre-commit", "commit-msg"):
        _git(repo, "config", "--add", "hook.mark.event", event)

    result = hardened_git.run_hardened_git(repo, "commit", "-qam", "edit")

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert "gpgsig" not in hardened_git.run_hardened_git(repo, "cat-file", "commit", "HEAD").stdout


@pytest.mark.parametrize("site", sorted(ALL_SITES))
def test_restore_and_rollback_stay_on_the_probed_git_dir_when_dot_git_is_rewritten(
    env, site, monkeypatch
):
    repo = _repo_with_local_work(env / "repo")
    elsewhere = _repo_with_local_work(env / "elsewhere")
    index = (elsewhere / ".git" / "index").read_bytes()
    real_check = hardened_git.config_names_a_repository_program

    def rewrite_dot_git_after_the_probe(names: list[str]) -> bool:
        if (repo / ".git").is_dir():
            (repo / ".git").rename(env / "moved.git")
            (repo / ".git").write_text(f"gitdir: {elsewhere / '.git'}\n", encoding="utf-8")
        return real_check(names)

    monkeypatch.setattr(
        hardened_git, "config_names_a_repository_program", rewrite_dot_git_after_the_probe
    )

    assert ALL_SITES[site](repo) == REFUSED[site]

    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT
    assert (elsewhere / ".git" / "index").read_bytes() == index
    assert not (elsewhere / ".git" / "ORIG_HEAD").exists()


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_use_the_probed_git_dir_when_the_gitdir_pointer_is_rewritten(
    env, site, monkeypatch
):
    repo = _repo_with_local_work(env / "repo")
    (repo / ".git").rename(repo / ".gitstore")
    (repo / ".git").write_text("gitdir: .gitstore\n", encoding="utf-8")
    # git clean -fd would otherwise remove a git dir kept under another name.
    (repo / ".gitstore" / "info" / "exclude").write_text("/.gitstore/\n", encoding="utf-8")
    elsewhere = _repo_with_local_work(env / "elsewhere")
    index = (elsewhere / ".git" / "index").read_bytes()
    real_check = hardened_git.config_names_a_repository_program

    def point_dot_git_elsewhere_after_the_probe(names: list[str]) -> bool:
        (repo / ".git").write_text(f"gitdir: {elsewhere / '.git'}\n", encoding="utf-8")
        return real_check(names)

    monkeypatch.setattr(
        hardened_git, "config_names_a_repository_program", point_dot_git_elsewhere_after_the_probe
    )

    assert SITES[site](repo) == RESTORED[site]

    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (repo / ".gitstore" / "HEAD").is_file()
    assert (elsewhere / ".git" / "index").read_bytes() == index
    assert not (elsewhere / ".git" / "ORIG_HEAD").exists()


@pytest.mark.parametrize("site", sorted(ALL_SITES))
def test_the_config_check_reads_the_probed_git_dir_when_the_gitdir_pointer_is_rewritten(
    env, site, monkeypatch
):
    repo = _repo_with_local_work(env / "repo")
    (repo / ".gitattributes").write_text("*.py filter=mark\n", encoding="utf-8")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-qm", "attributes", "--", ".gitattributes")
    marker = env / "filter-ran"
    script = _marker_script(env, "filter.sh", marker, passthrough=True)
    _git(repo, "config", "filter.mark.smudge", str(script))
    (repo / ".git").rename(repo / ".gitstore")
    (repo / ".git").write_text("gitdir: .gitstore\n", encoding="utf-8")
    (repo / ".gitstore" / "info" / "exclude").write_text("/.gitstore/\n", encoding="utf-8")
    clean = _repo_with_local_work(env / "clean")
    real_env = hardened_git.hardened_git_env
    calls = 0

    def rewrite_after_the_probe(repo_dir: Path, *args: Any) -> dict[str, str]:
        nonlocal calls
        calls += 1
        if calls == 2:  # the probe has run; the config check is next
            (repo / ".git").write_text(f"gitdir: {clean / '.git'}\n", encoding="utf-8")
        return real_env(repo_dir, *args)

    monkeypatch.setattr(hardened_git, "hardened_git_env", rewrite_after_the_probe)

    assert ALL_SITES[site](repo) == REFUSED[site]

    assert not marker.exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


def test_hardened_log_and_show_verify_no_signature_with_a_repository_signing_program(env):
    repo = _repo_with_local_work(env / "repo")
    marker = env / "gpg-ran"
    _git(repo, "config", "log.showSignature", "true")
    _git(repo, "config", "gpg.program", str(_marker_script(env, "gpg.sh", marker)))
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    signed = (
        f"tree {tree}\nauthor t <t@example.invalid> 0 +0000\n"
        "committer t <t@example.invalid> 0 +0000\n"
        "gpgsig -----BEGIN PGP SIGNATURE-----\n \n AAAA\n -----END PGP SIGNATURE-----\n\nsigned\n"
    )
    commit = subprocess.run(
        ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
        cwd=repo,
        input=signed,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    for args in (("log", "-1", commit), ("show", commit)):
        assert hardened_git.run_hardened_git(repo, *args).returncode == 0

    assert not marker.exists()


@pytest.mark.parametrize(
    ("name", "refused"),
    [
        ("diff.external", True),
        ("diff.mark.textconv", True),
        ("diff.mark.command", True),
        ("gpg.program", True),
        ("gpg.ssh.program", True),
        ("filter.mark.smudge", True),
        ("hook.mark.command", True),
        ("include.path", True),
        ("includeIf.gitdir:/x/.path", True),
        ("remote.origin.promisor", True),
        ("extensions.partialClone", True),
        ("diff.algorithm", False),
        ("diff.renames", False),
        ("core.autocrlf", False),
        ("remote.origin.url", False),
    ],
)
def test_the_config_check_refuses_keys_that_name_a_program_and_keeps_harmless_ones(name, refused):
    assert hardened_git.config_names_a_repository_program([name]) is refused


def _repo_with_a_planted_submodule(env: Path) -> tuple[Path, Path]:
    """A repo whose gitlink ``sub`` is populated with a ``.git`` file pointing at a planted
    repository; that repository's config names a hook that only touches a marker."""
    planted = env / "planted"
    planted.mkdir()
    (planted / "f.txt").write_text("a\n", encoding="utf-8")
    _git(planted, "init", "-q")
    _git(planted, "add", ".")
    _git(planted, "commit", "-qm", "planted")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=planted, capture_output=True, text=True, check=True
    ).stdout.strip()
    marker = env / "submodule-hook-ran"
    _git(planted, "config", "hook.mark.command", str(_marker_script(env, "hook.sh", marker)))
    for event in ("post-index-change", "post-checkout", "reference-transaction"):
        _git(planted, "config", "--add", "hook.mark.event", event)
    (planted / "f.txt").write_text("dirty\n", encoding="utf-8")
    repo = _repo_with_local_work(env / "repo")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},sub")
    _git(repo, "commit", "-qm", "gitlink")
    (repo / "sub").mkdir()
    (repo / "sub" / ".git").write_text(f"gitdir: {planted / '.git'}\n", encoding="utf-8")
    return repo, marker


@pytest.mark.parametrize(
    "args", [("status",), ("status", "--porcelain"), ("diff",), ("diff", "HEAD")]
)
def test_hardened_status_and_diff_do_not_enter_a_planted_submodule(env, args):
    repo, marker = _repo_with_a_planted_submodule(env)
    git_dir = hardened_git.repository_git_dir(repo)
    assert git_dir is not None

    assert hardened_git.run_hardened_git(repo, *args, git_dir=git_dir).returncode == 0

    assert not marker.exists()


@pytest.mark.parametrize("site", sorted(ALL_SITES))
def test_restore_and_rollback_still_restore_beside_a_planted_submodule(env, site):
    repo, marker = _repo_with_a_planted_submodule(env)

    ALL_SITES[site](repo)

    assert not marker.exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"


# --- Linked worktrees -------------------------------------------------------------------
# A directory made by ``git worktree add`` keeps its git dir in the main repository's
# ``worktrees/<name>`` admin entry; it is accepted only while that registration holds.

RESTORED_ALL = {**RESTORED, "heal_workspace_reset": None}


def _linked_worktree(env: Path, *, attributes: str = "") -> tuple[Path, Path, Path]:
    """A main repo and a linked worktree ``wt`` of it with notes.py dirty; returns
    (main, worktree, admin dir)."""
    main = _repo_with_local_work(env / "main")
    if attributes:
        (main / ".gitattributes").write_text(attributes, encoding="utf-8")
        _git(main, "add", ".gitattributes")
        _git(main, "commit", "-qm", "attributes", "--", ".gitattributes")
    worktree = env / "wt"
    _git(main, "worktree", "add", "-q", str(worktree))
    (worktree / "notes.py").write_text(DIRTY_EDIT, encoding="utf-8")
    return main, worktree, (main / ".git" / "worktrees" / "wt").resolve()


@pytest.mark.parametrize("site", sorted(ALL_SITES))
def test_restore_and_rollback_restore_a_registered_linked_worktree(env, site):
    main, worktree, admin = _linked_worktree(env)
    (worktree / "untracked.py").write_text("y\n", encoding="utf-8")

    assert hardened_git.repository_git_dir(worktree) == admin
    assert ALL_SITES[site](worktree) == RESTORED_ALL[site]

    assert (worktree / "notes.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (main / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


def _foreign_admin_entry(env: Path, worktree: Path, admin: Path) -> Path:
    repo = env / "repo"
    repo.mkdir()
    (repo / "notes.py").write_text(DIRTY_EDIT, encoding="utf-8")
    (repo / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    return repo


def _admin_entry_not_pointing_back(env: Path, worktree: Path, admin: Path) -> Path:
    (admin / "gitdir").write_text(f"{env / 'elsewhere' / '.git'}\n", encoding="utf-8")
    return worktree


def _tampered_commondir(env: Path, worktree: Path, admin: Path) -> Path:
    other = _repo_with_local_work(env / "other")
    (admin / "commondir").write_text(f"{(other / '.git').resolve()}\n", encoding="utf-8")
    return worktree


UNREGISTERED = {
    "gitfile_names_another_worktrees_admin_entry": _foreign_admin_entry,
    "admin_entry_does_not_point_back": _admin_entry_not_pointing_back,
    "commondir_names_another_repository": _tampered_commondir,
}


@pytest.mark.parametrize("site", sorted(ALL_SITES))
@pytest.mark.parametrize("kind", sorted(UNREGISTERED))
def test_restore_and_rollback_refuse_a_worktree_its_common_dir_does_not_register(env, site, kind):
    main, worktree, admin = _linked_worktree(env)
    index = (admin / "index").read_bytes()
    target = UNREGISTERED[kind](env, worktree, admin)

    assert hardened_git.repository_git_dir(target) is None
    assert ALL_SITES[site](target) == REFUSED[site]

    assert (target / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT
    assert (worktree / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT
    assert (admin / "index").read_bytes() == index
    if (env / "other").exists():
        assert (env / "other" / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(ALL_SITES))
@pytest.mark.parametrize("scope", ["common", "worktree"])
def test_restore_and_rollback_refuse_a_linked_worktree_whose_config_names_a_filter(
    env, site, scope
):
    main, worktree, admin = _linked_worktree(env, attributes="*.py filter=mark\n")
    marker = env / "filter-ran"
    script = _marker_script(env, "filter.sh", marker, passthrough=True)
    if scope == "common":
        _git(main, "config", "filter.mark.smudge", str(script))
    else:  # config.worktree, read once extensions.worktreeConfig is set
        _git(main, "config", "extensions.worktreeConfig", "true")
        (admin / "config.worktree").write_text(
            f'[filter "mark"]\n\tsmudge = {script}\n', encoding="utf-8"
        )

    assert ALL_SITES[site](worktree) == REFUSED[site]

    assert not marker.exists()
    assert (worktree / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(ALL_SITES))
def test_restore_and_rollback_stop_when_commondir_is_rewritten_after_the_probe(
    env, site, monkeypatch
):
    main, worktree, admin = _linked_worktree(env)
    other = _repo_with_local_work(env / "other")
    other_index = (other / ".git" / "index").read_bytes()
    real_check = hardened_git.config_names_a_repository_program

    def rewrite_commondir_after_the_config_check(names: list[str]) -> bool:
        (admin / "commondir").write_text(f"{(other / '.git').resolve()}\n", encoding="utf-8")
        return real_check(names)

    monkeypatch.setattr(
        hardened_git, "config_names_a_repository_program", rewrite_commondir_after_the_config_check
    )

    assert ALL_SITES[site](worktree) == REFUSED[site]

    assert (worktree / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT
    assert (other / ".git" / "index").read_bytes() == other_index
    assert (other / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


def test_a_linked_worktree_runs_with_its_verified_common_dir_pinned(env, monkeypatch):
    main, worktree, admin = _linked_worktree(env)
    real_env = hardened_git.hardened_git_env
    seen: list[dict[str, str]] = []

    def recording_env(*args: Any) -> dict[str, str]:
        seen.append(real_env(*args))
        return seen[-1]

    monkeypatch.setattr(hardened_git, "hardened_git_env", recording_env)

    result = hardened_git.run_hardened_git(worktree, "rev-parse", "HEAD", git_dir=admin)

    assert result.returncode == 0
    assert seen[-1]["GIT_DIR"] == str(admin)
    assert seen[-1]["GIT_COMMON_DIR"] == str((main / ".git").resolve())


def test_a_stale_index_lock_in_a_linked_worktrees_admin_entry_is_kept(env):
    main, worktree, admin = _linked_worktree(env)
    lock = admin / "index.lock"
    lock.write_text("", encoding="utf-8")

    assert hardened_git.clear_stale_index_lock(worktree, admin) is False
    assert lock.exists()


def test_a_symlink_to_a_linked_worktree_is_not_accepted_as_one(env):
    main, worktree, admin = _linked_worktree(env)
    link = env / "link"
    link.symlink_to(worktree)

    assert hardened_git.linked_worktree_git_dir(worktree) == admin
    assert hardened_git.linked_worktree_git_dir(link) is None
