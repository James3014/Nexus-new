"""Direct-failure NO_MUTATION probes: directory boundaries and unseen changes (#2727).

``_reconcile_direct_failure`` may close a failed Direct canonical action as FINAL_BLOCK
(NO_MUTATION_OBSERVED) only when no allowed path moved.  These tests pin, on real
temporary git repositories, that:

* an allowed entry covers the exact path and everything strictly below it as a
  directory (``docs/`` and ``docs`` both cover ``docs/x.md``), but never a sibling
  that merely shares a prefix (``docs2/x.md``, ``src/a.py.bak``);
* an untracked (not ignored) file at or below an allowed path counts as a change;
* a rename of an allowed path is seen on both sides, and a non-ASCII path is compared
  unquoted;
* an allowed entry that is not a normalized repository-relative path, or a listing
  probe that exits non-zero, keeps the task retained for review.

Only ``git`` runs, on repositories under ``tmp_path`` with a local git identity.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

NOW = "2026-10-19T00:00:00+00:00"


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SelfHostedTaskService:
    monkeypatch.setattr(service_module, "_utc_now", lambda: NOW)
    return SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> SimpleNamespace:
    path = (tmp_path / "repo").resolve()
    (path / "src").mkdir(parents=True)
    (path / "docs").mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Nexus Test")
    _git(path, "config", "user.email", "nexus-test@example.invalid")
    _git(path, "config", "commit.gpgsign", "false")
    (path / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
    (path / "src" / "a.py.bak").write_text("b\n", encoding="utf-8")
    (path / "docs" / "x.md").write_text("x\n", encoding="utf-8")
    (path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return SimpleNamespace(path=path, head=_git(path, "rev-parse", "HEAD"))


def _reconcile(service: SelfHostedTaskService, repo: SimpleNamespace, allowed: list[Any]) -> dict:
    service._write_state(
        "t",
        {
            "task_id": "t",
            "attempt_id": "a1",
            "status": "DIRECT_RECONCILE_REQUIRED",
            "request": {
                "controller_repo_root": str(repo.path),
                "controller_revision": repo.head,
                "allowed_files": allowed,
            },
            "status_history": [],
        },
    )
    result = service._reconcile_direct_failure("t")
    assert result is not None
    return result


def _assert_retained(result: dict, touched: list[str] | None = None) -> None:
    assert result["status"] == "DIRECT_RECONCILE_REQUIRED"
    assert result["reconciliation_decision"] == "RETAINED_FOR_REVIEW"
    assert result["reconciliation_required"] is True
    if touched is not None:
        assert result["reconciliation_evidence"]["allowed_paths_touched"] == touched


def _assert_closed(result: dict) -> None:
    assert result["status"] == "FINAL_BLOCK"
    assert result["reconciliation_decision"] == "NO_MUTATION_OBSERVED"
    assert result["reconciliation_evidence"]["allowed_paths_touched"] == []


def test_clean_repository_closes(service, repo) -> None:
    _assert_closed(_reconcile(service, repo, ["src/a.py", "docs/"]))


@pytest.mark.parametrize("entry", ["docs/", "docs", "docs//"])
@pytest.mark.parametrize("where", ["working_tree", "staged", "committed"])
def test_change_below_an_allowed_directory_is_retained(service, repo, entry, where) -> None:
    (repo.path / "docs" / "x.md").write_text("changed\n", encoding="utf-8")
    if where != "working_tree":
        _git(repo.path, "add", "docs/x.md")
    if where == "committed":
        _git(repo.path, "commit", "-q", "-m", "c")
    _assert_retained(_reconcile(service, repo, [entry]), ["docs/x.md"])


def test_change_deep_below_an_allowed_directory_is_retained(service, repo) -> None:
    (repo.path / "docs" / "deep").mkdir()
    (repo.path / "docs" / "deep" / "y.md").write_text("y\n", encoding="utf-8")
    _git(repo.path, "add", "docs/deep/y.md")
    _assert_retained(_reconcile(service, repo, ["docs/"]), ["docs/deep/y.md"])


def test_a_shared_prefix_is_not_a_directory_boundary(service, repo) -> None:
    (repo.path / "docs2").mkdir()
    (repo.path / "docs2" / "x.md").write_text("d2\n", encoding="utf-8")
    (repo.path / "src" / "a.py.bak").write_text("changed\n", encoding="utf-8")
    _git(repo.path, "add", "docs2/x.md", "src/a.py.bak")
    _git(repo.path, "commit", "-q", "-m", "siblings")
    result = _reconcile(service, repo, ["docs/", "docs", "src/a.py"])
    _assert_closed(result)
    assert result["reconciliation_evidence"]["commits_since_base"] == ["docs2/x.md", "src/a.py.bak"]


@pytest.mark.parametrize(
    "relative, allowed",
    [
        ("src/new.py", ["src/new.py"]),
        ("docs/new.md", ["docs/"]),
        ("docs/sub/new.md", ["docs"]),
    ],
)
def test_untracked_file_at_an_allowed_path_is_retained(service, repo, relative, allowed) -> None:
    target = repo.path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("n\n", encoding="utf-8")
    result = _reconcile(service, repo, allowed)
    _assert_retained(result, [relative])
    assert result["reconciliation_evidence"]["untracked_changes"] == [relative]


def test_untracked_file_outside_the_allowed_paths_still_closes(service, repo) -> None:
    (repo.path / "notes.txt").write_text("n\n", encoding="utf-8")
    (repo.path / "docs2").mkdir()
    (repo.path / "docs2" / "n.md").write_text("n\n", encoding="utf-8")
    result = _reconcile(service, repo, ["docs/", "src/a.py"])
    _assert_closed(result)
    assert result["reconciliation_evidence"]["untracked_changes"] == ["docs2/n.md", "notes.txt"]


def test_untracked_files_are_listed_from_the_repository_root(service, repo, tmp_path) -> None:
    # git ls-files lists relative to the cwd; the probe must use repository-root names
    # like git diff does, so the boundary comparison sees the same path space.
    (repo.path / "src" / "new.py").write_text("n\n", encoding="utf-8")
    service._write_state(
        "t",
        {
            "task_id": "t",
            "attempt_id": "a1",
            "status": "DIRECT_RECONCILE_REQUIRED",
            "request": {
                "controller_repo_root": str(repo.path / "docs"),
                "controller_revision": repo.head,
                "allowed_files": ["src/new.py"],
            },
            "status_history": [],
        },
    )
    result = service._reconcile_direct_failure("t")
    assert result is not None
    _assert_retained(result, ["src/new.py"])


def test_staged_rename_of_an_allowed_file_is_retained(service, repo) -> None:
    _git(repo.path, "mv", "src/a.py", "moved.py")
    _assert_retained(_reconcile(service, repo, ["src/a.py"]), ["src/a.py"])


def test_committed_rename_of_an_allowed_file_is_retained(service, repo) -> None:
    _git(repo.path, "mv", "src/a.py", "moved.py")
    _git(repo.path, "commit", "-q", "-m", "rename")
    _assert_retained(_reconcile(service, repo, ["src/a.py"]), ["src/a.py"])


@pytest.mark.parametrize("tracked", [True, False])
def test_non_ascii_path_below_an_allowed_directory_is_retained(service, repo, tracked) -> None:
    (repo.path / "docs" / "café.md").write_text("c\n", encoding="utf-8")
    if tracked:
        _git(repo.path, "add", "docs")
    _assert_retained(_reconcile(service, repo, ["docs/"]), ["docs/café.md"])


@pytest.mark.parametrize(
    "entry", ["/", "/abs/path", "../x", "a/../src/a.py", "./src/a.py", "a\\b", "a//b"]
)
def test_an_unnormalized_allowed_entry_is_retained(service, repo, entry) -> None:
    result = _reconcile(service, repo, ["src/a.py", entry])
    _assert_retained(result, [])
    assert result["reconciliation_evidence"]["invalid_allowed_paths"] == [entry]


@pytest.mark.parametrize("failing", ["diff", "ls-files"])
def test_a_failing_listing_probe_is_retained(service, repo, monkeypatch, failing) -> None:
    real_run = subprocess.run

    def run(argv: Any, **kwargs: Any) -> Any:
        if failing in argv:
            return SimpleNamespace(returncode=128, stdout="", stderr="boom")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(service_module, "subprocess", SimpleNamespace(run=run))
    result = _reconcile(service, repo, ["src/a.py"])
    _assert_retained(result)
    assert "exited 128" in result["reconciliation_evidence"]["probe_error"]


def test_ignored_files_are_not_a_mutation(service, repo) -> None:
    # git's own notion of untracked (--exclude-standard): an ignored build output under an
    # allowed directory is not a Direct mutation.
    (repo.path / "docs" / "build.log").write_text("l\n", encoding="utf-8")
    _assert_closed(_reconcile(service, repo, ["docs/"]))
