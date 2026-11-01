"""Live git calls in a worker-written Target start no program the repository names.

Every program planted here only touches a marker file under ``tmp_path``.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.orchestrator import worktree_manager as wm_module
from nexus.orchestrator.worktree_manager import WorktreeManager


def _clean_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"core.hooksPath={os.devnull}", *args],
        cwd=cwd,
        env=_clean_env(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    monkeypatch.chdir(sentinel)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("NEXUS_CANONICAL_GIT_HOOKS_DIR", str(tmp_path / "canonical-hooks"))
    monkeypatch.setattr(wm_module, "measurement_mode_at_start", lambda: False)
    controller = tmp_path / "controller"
    controller.mkdir()
    _git(controller, "init", "-q", "-b", "main")
    _git(controller, "config", "user.name", "Test")
    _git(controller, "config", "user.email", "test@example.invalid")
    (controller / "f.txt").write_text("a\n", encoding="utf-8")
    _git(controller, "add", "f.txt")
    _git(controller, "commit", "-qm", "init")
    targets = tmp_path / "targets"
    targets.mkdir()
    target = targets / "task-1"
    _git(controller, "worktree", "add", "-q", "-b", "codex/task/task-1", str(target))
    markers = tmp_path / "markers"
    markers.mkdir()
    return SimpleNamespace(
        controller=controller,
        target=target,
        manager=WorktreeManager(root_dir=str(targets), create_root=False),
        contract=SimpleNamespace(controller_repo_root=str(controller)),
        markers=markers,
    )


def _plant_repository(target: Path, markers: Path) -> None:
    """What a worker that can only write files in its Target can do: point ``.git`` at a
    repository it wrote, whose config and hooks name programs."""
    planted = target / "planted"
    _git(target.parent, "init", "-q", "--bare", str(planted))
    _git(target, "config", "--file", str(planted / "config"), "core.bare", "false")
    _git(target, "--git-dir", str(planted), "--work-tree", str(target), "add", "f.txt")
    _git(
        target,
        "--git-dir",
        str(planted),
        "--work-tree",
        str(target),
        "-c",
        "user.name=w",
        "-c",
        "user.email=w@example.invalid",
        "commit",
        "-qm",
        "planted",
    )
    for key, value in (
        ("hook.m.command", f"touch '{markers}/config-hook'"),
        ("hook.m.event", "pre-commit"),
        ("diff.external", f"sh -c \"touch '{markers}/diff-external'\" --"),
        ("core.fsmonitor", f"touch '{markers}/fsmonitor'; true"),
    ):
        _git(target, "config", "--file", str(planted / "config"), "--add", key, value)
    hooks = planted / "hooks"
    hooks.mkdir(exist_ok=True)
    for name in ("pre-commit", "post-commit", "post-index-change"):
        hook = hooks / name
        hook.write_text(f"#!/bin/sh\ntouch '{markers}/hook-{name}'\n", encoding="utf-8")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    (target / ".git").write_text(f"gitdir: {planted}\n", encoding="utf-8")


def _target_calls(manager: WorktreeManager, target: Path) -> list[str]:
    """Run the Target calls capture, contract gate, salvage and candidate commit make;
    returns the ones that were refused."""
    (target / "f.txt").write_text("worker edit\n", encoding="utf-8")
    calls = (
        lambda: manager._status_bytes(target),
        lambda: manager._run_git(["diff", "--unified=0", "HEAD", "--", "f.txt"], cwd=target),
        lambda: manager._run_git_bytes(
            ["diff", "--binary", "--no-ext-diff", "HEAD", "--"], cwd=target
        ),
        lambda: manager._run_git(["add", "--all"], cwd=target),
        lambda: manager._run_git(
            ["-c", "user.name=n", "-c", "user.email=n@example.invalid", "commit", "-m", "salvage"],
            cwd=target,
        ),
    )
    refused = []
    for index, call in enumerate(calls):
        try:
            call()
        except RuntimeError:
            refused.append(str(index))
    return refused


def _fired(markers: Path) -> list[str]:
    return sorted(path.name for path in markers.iterdir())


def test_target_calls_refuse_a_planted_repository_without_running_its_programs(layout):
    _plant_repository(layout.target, layout.markers)

    refused = _target_calls(layout.manager, layout.target)

    assert _fired(layout.markers) == []
    assert refused == ["0", "1", "2", "3", "4"]


def test_contract_bound_target_calls_refuse_a_redirected_git_file(layout):
    _plant_repository(layout.target, layout.markers)

    with layout.manager.controller_git_scope(layout.contract):
        refused = _target_calls(layout.manager, layout.target)
        with pytest.raises(RuntimeError, match="TARGET_GITDIR_UNTRUSTED"):
            layout.manager._run_git(["rev-parse", "HEAD"], cwd=layout.target)

    assert _fired(layout.markers) == []
    assert refused == ["0", "1", "2", "3", "4"]


def test_contract_bound_target_calls_run_on_the_controller_registration(layout, monkeypatch):
    seen: list[dict[str, str]] = []
    real_run = subprocess.run

    def recording_run(argv, *args, **kwargs):
        if kwargs.get("env") is not None:
            seen.append(dict(kwargs["env"]))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    registration = (layout.controller / ".git" / "worktrees" / "task-1").resolve()

    with layout.manager.controller_git_scope(layout.contract):
        layout.manager._run_git(["rev-parse", "HEAD"], cwd=layout.target)

    assert seen
    assert all(env["GIT_DIR"] == str(registration) for env in seen)
    assert all(env["GIT_WORK_TREE"] == str(layout.target.resolve()) for env in seen)


def test_target_calls_skip_hooks_and_external_diff_from_a_controller_config(layout):
    """A config-defined hook or external diff the hooks path cannot switch off is refused
    before git runs, even when it comes from the Controller's own config."""
    _git(layout.controller, "config", "hook.m.command", f"touch '{layout.markers}/config-hook'")
    _git(layout.controller, "config", "--add", "hook.m.event", "pre-commit")
    _git(layout.controller, "config", "--add", "hook.m.event", "post-commit")
    _git(
        layout.controller,
        "config",
        "diff.external",
        f"sh -c \"touch '{layout.markers}/diff-external'\" --",
    )

    with layout.manager.controller_git_scope(layout.contract):
        refused = _target_calls(layout.manager, layout.target)

    assert _fired(layout.markers) == []
    assert refused == ["0", "1", "2", "3", "4"]


def test_target_calls_on_a_normal_target_match_plain_git(layout):
    target = layout.target
    (target / "f.txt").write_text("worker edit\n", encoding="utf-8")
    (target / "new.txt").write_text("new\n", encoding="utf-8")
    manager = layout.manager
    expected_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=target,
        env=_clean_env(),
        capture_output=True,
        check=True,
    ).stdout
    expected_diff = _git(target, "diff", "--unified=0", "HEAD", "--", "f.txt").strip()

    with manager.controller_git_scope(layout.contract):
        assert manager._status_bytes(target) == expected_status
        assert manager._run_git(["diff", "--unified=0", "HEAD", "--", "f.txt"], cwd=target) == (
            expected_diff
        )
        manager._run_git(["add", "--all"], cwd=target)
        manager._run_git(
            ["-c", "user.name=n", "-c", "user.email=n@example.invalid", "commit", "-m", "salvage"],
            cwd=target,
        )
        head = manager._run_git(["rev-parse", "HEAD"], cwd=target)
        assert manager._status_bytes(target) == b""

    assert _git(layout.controller, "rev-parse", "codex/task/task-1").strip() == head
    assert _git(target, "log", "-1", "--format=%s").strip() == "salvage"


def test_unbound_target_calls_skip_target_hooks(layout):
    """Unbound to a contract, a Target under the manager's root still runs no hook its git
    dir holds (commit hooks included) while normal output is unchanged."""
    registration = layout.controller / ".git" / "worktrees" / "task-1"
    hooks = layout.controller / ".git" / "hooks"
    for name in ("pre-commit", "commit-msg", "post-commit", "post-index-change"):
        hook = hooks / name
        hook.write_text(f"#!/bin/sh\ntouch '{layout.markers}/hook-{name}'\n", encoding="utf-8")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    assert registration.is_dir()

    assert _target_calls(layout.manager, layout.target) == []

    assert _fired(layout.markers) == []
    assert _git(layout.target, "log", "-1", "--format=%s").strip() == "salvage"


def test_controller_calls_keep_the_existing_runner(layout, monkeypatch):
    seen: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(argv, *args, **kwargs):
        seen.append(list(argv))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)

    with layout.manager.controller_git_scope(layout.contract):
        layout.manager._run_git(["rev-parse", "HEAD"], cwd=layout.controller)
    layout.manager._run_git(["rev-parse", "HEAD"], cwd=layout.controller)

    assert len(seen) == 2
    assert all(argv[:3] == ["git", "-c", "core.fsmonitor=false"] for argv in seen)


def _register_with_other_controller(target: Path, other: Path) -> None:
    """Re-register ``target`` as a worktree of another repository ``other``."""
    other.mkdir()
    _git(other, "init", "-q", "-b", "main")
    _git(other, "config", "user.name", "Test")
    _git(other, "config", "user.email", "test@example.invalid")
    _git(other, "commit", "-q", "--allow-empty", "-m", "other")
    _git(other, "worktree", "add", "-q", "--detach", str(other.parent / "other-wt"))
    registration = (other / ".git" / "worktrees" / "other-wt").resolve()
    (registration / "gitdir").write_text(f"{target / '.git'}\n", encoding="utf-8")
    (target / ".git").write_text(f"gitdir: {registration}\n", encoding="utf-8")


def test_contract_bound_target_must_belong_to_the_contract_controller(layout, tmp_path):
    _register_with_other_controller(layout.target, tmp_path / "other")

    with layout.manager.controller_git_scope(layout.contract):
        with pytest.raises(RuntimeError, match="TARGET_GITDIR_UNTRUSTED"):
            layout.manager._run_git(["rev-parse", "HEAD"], cwd=layout.target)


def test_slot_reuse_verifies_the_slot_against_the_contract_controller(layout, tmp_path):
    contract = SimpleNamespace(controller_repo_root=str(layout.controller))
    _register_with_other_controller(layout.target, tmp_path / "other")
    manager = layout.manager
    manager.get_reusable_slot_path = lambda campaign_id, slot_index: layout.target

    with pytest.raises(RuntimeError, match="TARGET_GITDIR_UNTRUSTED"):
        manager.prepare_reusable_slot(contract, campaign_id="c", slot_index=0)


def test_unbound_target_refuses_a_registration_planted_inside_it(layout):
    target = layout.target
    planted = target / "nested"
    planted.mkdir()
    _git(planted, "init", "-q")
    registration = planted / ".git" / "worktrees" / "w"
    registration.mkdir(parents=True)
    (registration / "commondir").write_text("../..\n", encoding="utf-8")
    (registration / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (registration / "gitdir").write_text(f"{target / '.git'}\n", encoding="utf-8")
    (target / ".git").write_text(f"gitdir: {registration}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="TARGET_GITDIR_UNTRUSTED"):
        layout.manager._run_git(["rev-parse", "HEAD"], cwd=target)


def test_a_missing_target_directory_still_fails_as_before(layout):
    missing = layout.target.parent / "missing"

    with layout.manager.controller_git_scope(layout.contract):
        with pytest.raises(FileNotFoundError):
            layout.manager._run_git(["rev-parse", "HEAD"], cwd=missing)
