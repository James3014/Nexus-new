"""Ultra review keeps its host-side cleanup and writes on the entries the review itself created.

Every "outside" directory or file here lives in ``tmp_path`` and carries sentinel content; the
tests check that the review leaves it exactly as it was.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import nexus.engine.ultra_review_service as ultra_mod
from nexus.engine.ultra_review_service import ULTRA_SKIP_GHOST_ENV, UltraReviewService


@pytest.fixture(autouse=True)
def _contained_cwd(tmp_path, monkeypatch):
    sentinel_cwd = tmp_path / "sentinel-cwd"
    sentinel_cwd.mkdir()
    monkeypatch.chdir(sentinel_cwd)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _init_app_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / ".gitignore").write_text(".nexus/\nreports/\n", encoding="utf-8")
    (path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n", encoding="utf-8"
    )
    (path / "tests").mkdir()
    (path / "tests" / "test_app.py").write_text(
        "from app import handler\n\n\ndef test_handler_strips():\n    assert handler('  a ') == 'a'\n",
        encoding="utf-8",
    )
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "init")
    (path / "app.py").write_text(
        "def handler(value):\n    return value.strip()  # tweak\n", encoding="utf-8"
    )


def _outside_repo(base: Path) -> Path:
    """A directory outside every review tree that looks like someone's checkout."""

    outside = base / "outside_repo"
    (outside / ".git").mkdir(parents=True)
    (outside / ".git" / "MARKER").write_text("outside git dir\n", encoding="utf-8")
    (outside / "important.txt").write_text("outside data\n", encoding="utf-8")
    return outside


def _assert_outside_intact(outside: Path) -> None:
    assert (outside / ".git").is_dir() and not (outside / ".git").is_symlink()
    assert (outside / ".git" / "MARKER").read_text(encoding="utf-8") == "outside git dir\n"
    assert (outside / "important.txt").read_text(encoding="utf-8") == "outside data\n"
    assert sorted(p.name for p in outside.iterdir()) == [".git", "important.txt"]


def _swap_for_link(entry: Path, target: Path) -> Path:
    """Move ``entry`` aside and leave a link to ``target`` under its name."""

    moved = entry.with_name(entry.name + ".moved")
    os.rename(entry, moved)
    os.symlink(target, entry)
    return moved


# --- the sandbox policy ---------------------------------------------------------------------


def _bound_service(tmp_path: Path) -> tuple[UltraReviewService, Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    service = UltraReviewService(root)
    sandbox = root / ".nexus" / "sandbox"
    execution_root = sandbox / "worktree"
    execution_root.mkdir(parents=True)
    service._bind_sandbox(sandbox_path=sandbox, execution_root=execution_root)
    return service, sandbox.resolve(), execution_root.resolve()


def _write_rule(profile: str) -> str:
    return next(line for line in profile.splitlines() if line.startswith("(allow file-write* "))


def test_review_sandbox_writes_only_its_working_dirs_and_keeps_their_entries_fixed(tmp_path):
    service, sandbox, execution_root = _bound_service(tmp_path)
    profile = service._sandbox_profile()
    writes = _write_rule(profile)

    for writable in (execution_root, sandbox / "home", sandbox / "tmp"):
        assert f'(subpath "{writable}")' in writes
        # The directory may be written into, but its own entry cannot be removed or replaced.
        assert f'(deny file-write* (literal "{writable}"))' in profile.splitlines()
    # The sandbox dir itself (progress log, captured diff, git home) is not writable.
    assert f'(subpath "{sandbox}")' not in writes
    assert f'(deny file-write* (literal "{sandbox}"))' in profile.splitlines()


def test_review_sandbox_grants_a_witnessed_run_its_report_dir_and_cwd_for_that_run_only(
    tmp_path, monkeypatch
):
    service, sandbox, execution_root = _bound_service(tmp_path)
    report = UltraReviewService._new_ghost_report(sandbox, "head")
    seen: dict[str, str] = {}

    def fake_sandboxed_run(cmd, *, cwd, timeout, stdin_text=None, kill_process_group=False):
        seen["profile"] = service._sandbox_profile()
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(service, "_sandboxed_run", fake_sandboxed_run)
    service._run_witnessed(["true"], report, cwd=execution_root, timeout=5)

    report_dir = Path(report["dir"]).resolve()
    assert f'(subpath "{report_dir}")' in _write_rule(seen["profile"])
    assert f'(deny file-write* (literal "{report_dir}"))' in seen["profile"].splitlines()
    assert f'(subpath "{report_dir}")' not in _write_rule(service._sandbox_profile())


# --- host-side restore and cleanup ----------------------------------------------------------


def test_git_dir_restore_leaves_a_directory_swapped_in_for_the_checkout_untouched(tmp_path):
    project = tmp_path / "project"
    _init_app_repo(project)
    outside = _outside_repo(tmp_path)
    service = UltraReviewService(project)
    service._git_home = (tmp_path / "git-home").resolve()
    service._git_home.mkdir()
    checkout = tmp_path / "wt"
    _git(project, "worktree", "add", "--detach", str(checkout), "HEAD")

    swap = service._give_checkout_sandbox_git_dir(checkout, rev="HEAD")
    assert swap["ok"] is True, swap
    git_dir = Path(swap["git_dir"])
    _swap_for_link(checkout, outside)

    result = service._restore_checkout_git_file(checkout, swap)

    _assert_outside_intact(outside)
    assert result["restored"] is False
    assert "replaced" in result["detail"]
    # The reviewer's own git dir is still removed.
    assert not git_dir.exists()
    assert service._integrity_violations


def test_worktree_cleanup_leaves_a_directory_swapped_in_for_the_worktree_untouched(tmp_path):
    project = tmp_path / "project"
    _init_app_repo(project)
    service = UltraReviewService(project)
    sandbox = service._prepare_sandbox(Path("reports/sandboxes"), "run-1")
    execution_root = sandbox / "worktree"
    _git(project, "worktree", "add", "--detach", str(execution_root), "HEAD")
    service._bind_sandbox(sandbox_path=sandbox, execution_root=execution_root)
    # The outside directory carries the worktree's own .git pointer, as a restore that followed
    # the link would have left it.
    pointer = (execution_root / ".git").read_text(encoding="utf-8")
    other = tmp_path / "outside_with_pointer"
    other.mkdir()
    (other / ".git").write_text(pointer, encoding="utf-8")
    (other / "important.txt").write_text("outside data\n", encoding="utf-8")
    _swap_for_link(execution_root, other)

    cleanup = service._cleanup_execution_worktree(execution_root, {"strategy": "git_worktree"})

    assert (other / "important.txt").read_text(encoding="utf-8") == "outside data\n"
    assert (other / ".git").read_text(encoding="utf-8") == pointer
    assert cleanup["removed"] is False
    assert "replaced" in cleanup["detail"]
    assert service._integrity_violations


def test_base_checkout_cleanup_leaves_a_directory_swapped_in_for_the_base_checkout_untouched(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    _init_app_repo(project)
    outside = _outside_repo(tmp_path)
    service = UltraReviewService(project)
    sandbox = service._prepare_sandbox(Path("reports/sandboxes"), "run-1")
    execution_root = sandbox / "worktree"
    execution_root.mkdir()
    service._bind_sandbox(sandbox_path=sandbox, execution_root=execution_root)

    def swapping_run(cmd, report, *, cwd, timeout):
        # What code under review could do to the base checkout while it runs.
        _swap_for_link(Path(cwd), outside)
        return subprocess.CompletedProcess(cmd, 1, "", "")

    monkeypatch.setattr(service, "_run_witnessed", swapping_run)
    outcome = service._compare_failures_on_base(
        ["tests/test_app.py::test_handler_strips"],
        base_ref="HEAD",
        sandbox_path=sandbox,
        timeout_sec=5,
        execution_root=execution_root,
    )

    _assert_outside_intact(outside)
    assert outcome["base_cleanup"]["removed"] is False
    assert "replaced" in outcome["base_cleanup"]["detail"]
    assert service._integrity_violations


def test_review_with_a_worktree_swapped_during_the_ghost_run_leaves_it_untouched_and_does_not_pass(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    _init_app_repo(project)
    outside = _outside_repo(tmp_path)
    monkeypatch.setattr(ultra_mod, "os_sandbox_available", lambda: True)

    def swapping_ghost(self, test_candidates, *, execution_root, **_kwargs):
        # What a mapped test could do to the mirror it runs in.
        _swap_for_link(Path(execution_root), outside)
        return {
            "passed": True,
            "executed_tests": list(test_candidates),
            "failed_tests": [],
            "skipped_tests": [],
            "findings": [],
            "execution_mode": "sandbox_mirror",
            "execution_cwd": str(execution_root),
            "timeout": False,
        }

    monkeypatch.setattr(UltraReviewService, "_run_ghost_regression", swapping_ghost)
    payload = UltraReviewService(project).run(
        dry_run=False,
        report_path="reports/ultra.json",
        sandbox_root="reports/sandboxes",
        regression_tests=["tests/test_app.py"],
    )

    _assert_outside_intact(outside)
    assert payload["status"] != "PASS"
    assert payload["gate_passed"] is False
    assert payload["blocked_reason"].startswith("sandbox_entry_replaced")
    assert payload["worktree_cleanup"]["removed"] is False


# --- progress log -----------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_progress_log_never_writes_through_a_link_left_at_its_name(tmp_path, kind):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("ORIGINAL\n", encoding="utf-8")
    service = UltraReviewService(project)
    sandbox = service._prepare_sandbox(Path("reports/sandboxes"), "run-1")
    progress_path = sandbox / "progress.jsonl"
    progress: list[dict] = []
    service._record_progress(progress, progress_path, "sandbox_prepared")
    progress_path.unlink()
    if kind == "symlink":
        os.symlink(outside, progress_path)
    else:
        os.link(outside, progress_path)

    with pytest.raises(OSError):
        service._record_progress(progress, progress_path, "diff_captured")

    assert outside.read_text(encoding="utf-8") == "ORIGINAL\n"


def test_progress_log_keeps_every_event_in_order(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    service = UltraReviewService(project)
    sandbox = service._prepare_sandbox(Path("reports/sandboxes"), "run-1")
    progress_path = sandbox / "progress.jsonl"
    progress: list[dict] = []
    for stage in ("one", "two", "three"):
        service._record_progress(progress, progress_path, stage)

    lines = progress_path.read_text(encoding="utf-8").splitlines()
    assert [ultra_mod.json.loads(line)["stage"] for line in lines] == ["one", "two", "three"]


def test_progress_log_is_not_written_once_the_sandbox_dir_was_replaced(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    (outside / "progress.jsonl").write_text("ORIGINAL\n", encoding="utf-8")
    service = UltraReviewService(project)
    sandbox = service._prepare_sandbox(Path("reports/sandboxes"), "run-1")
    progress: list[dict] = []
    service._record_progress(progress, sandbox / "progress.jsonl", "sandbox_prepared")
    _swap_for_link(sandbox, outside)

    with pytest.raises(OSError):
        service._record_progress(progress, sandbox / "progress.jsonl", "diff_captured")

    assert (outside / "progress.jsonl").read_text(encoding="utf-8") == "ORIGINAL\n"
    assert sorted(p.name for p in outside.iterdir()) == ["progress.jsonl"]


# --- report file ------------------------------------------------------------------------------


def _report_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    _init_app_repo(project)
    (project / ".nexus" / "reports" / "ultra_review").mkdir(parents=True)
    return project


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_report_never_writes_through_a_link_left_at_the_report_path(tmp_path, monkeypatch, kind):
    monkeypatch.setenv(ULTRA_SKIP_GHOST_ENV, "1")
    project = _report_project(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("ORIGINAL\n", encoding="utf-8")
    rel = ".nexus/reports/ultra_review/task_capability_report.json"
    if kind == "symlink":
        os.symlink(outside, project / rel)
    else:
        os.link(outside, project / rel)

    payload = UltraReviewService(project).run(
        dry_run=False,
        report_path=rel,
        sandbox_root=".nexus/reports/ultra_review/capability_sandboxes",
    )

    assert outside.read_text(encoding="utf-8") == "ORIGINAL\n"
    assert payload["status"] == "BLOCKED"
    assert payload["gate_passed"] is False
    assert payload["report_path"] == ""


def test_report_never_writes_through_a_linked_report_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(ULTRA_SKIP_GHOST_ENV, "1")
    project = tmp_path / "project"
    _init_app_repo(project)
    outside = tmp_path / "outside_reports"
    outside.mkdir()
    (outside / "report.json").write_text("ORIGINAL\n", encoding="utf-8")
    (project / "reports").symlink_to(outside, target_is_directory=True)

    payload = UltraReviewService(project).run(
        dry_run=False,
        report_path=str(project / "reports" / "report.json"),
        sandbox_root=".nexus/reports/ultra_review/sandboxes",
    )

    assert (outside / "report.json").read_text(encoding="utf-8") == "ORIGINAL\n"
    assert payload["report_path"] == ""


def test_blocked_report_never_writes_through_a_link_left_at_the_report_path(tmp_path, monkeypatch):
    project = _report_project(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("ORIGINAL\n", encoding="utf-8")
    rel = ".nexus/reports/ultra_review/blocked_report.json"
    os.symlink(outside, project / rel)

    def failing_diff(self, base_ref):
        raise OSError("diff unavailable")

    monkeypatch.setattr(UltraReviewService, "_capture_diff", failing_diff)
    payload = UltraReviewService(project).run(
        dry_run=False, report_path=rel, sandbox_root=".nexus/reports/ultra_review/sandboxes"
    )

    assert payload["status"] == "BLOCKED"
    assert outside.read_text(encoding="utf-8") == "ORIGINAL\n"
    assert payload["report_path"] == ""


def test_report_is_written_at_a_relative_and_an_absolute_path_inside_the_project(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(ULTRA_SKIP_GHOST_ENV, "1")
    project = _report_project(tmp_path)
    service = UltraReviewService(project)

    first = service.run(
        dry_run=False, report_path="reports/one.json", sandbox_root="reports/sandboxes"
    )
    second = service.run(
        dry_run=False,
        report_path=project / "reports" / "nested" / "two.json",
        sandbox_root="reports/sandboxes",
    )

    for payload, path in (
        (first, project / "reports" / "one.json"),
        (second, project / "reports" / "nested" / "two.json"),
    ):
        assert payload["report_path"] == str(path.resolve())
        assert ultra_mod.json.loads(path.read_text(encoding="utf-8"))["run_id"] == payload["run_id"]
