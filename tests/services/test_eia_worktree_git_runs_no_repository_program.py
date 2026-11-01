"""EIA fanout and closure run git in a worker's worktree only through nexus.core.hardened_git.

The OpenCode worker runs in a linked worktree and can rewrite anything in it, including the
``.git`` pointer file, so capture, commit, the repair and binding re-checks, receipt
validation and the verifier's workspace checks pin git to the Controller's registration of
that worktree and start no program a repository names. Every repo here is a fresh
``git init`` under ``tmp_path``; each test moves the cwd to a sentinel directory first, and
every hook or config program only touches a marker file under ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from nexus.services import external_intelligence_closure as closure
from nexus.services import external_intelligence_fanout as fanout
from nexus.services.external_intelligence_core_binding import CoreBindingError
from nexus.services.external_intelligence_fanout import (
    AdaptiveWorkerFanoutRuntime,
    ExecutionUnit,
    FanoutError,
    GitWorktreeAllocator,
    WorkspaceLease,
)
from tests.services.test_external_intelligence_closure import make_receipt
from tests.services.test_external_intelligence_closure import make_repo as make_closure_repo

HOOKS = (
    "pre-commit",
    "commit-msg",
    "post-commit",
    "post-checkout",
    "post-index-change",
    "reference-transaction",
)


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


def _controller(env: Path) -> tuple[Path, str]:
    repo = env / "controller"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.invalid")
    (repo / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-qm", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _unit(base: str, paths: list[str]) -> ExecutionUnit:
    return ExecutionUnit.from_mapping({
        "task_id": "task-1",
        "unit_id": "u1",
        "envelope_ref": "/envelope.json",
        "envelope_sha256": "a" * 64,
        "expected_base_sha": base,
        "mutation_paths": paths,
    })


def _plant_hooks_and_fsmonitor(git_dir: Path, markers: Path) -> None:
    """Hooks in the hooks dir and an fsmonitor: the command line switches both off."""
    markers.mkdir(exist_ok=True)
    hooks = git_dir / "hooks"
    hooks.mkdir(exist_ok=True)
    for hook in HOOKS:
        script = hooks / hook
        script.write_text(f"#!/bin/sh\ntouch '{markers}/hook.{hook}'\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
    _git(git_dir, "config", "--file", str(git_dir / "config"), "core.fsmonitor",
         f"touch '{markers}/fsmonitor'; true")  # fmt: skip


def _plant_config(git_dir: Path, markers: Path, *pairs: tuple[str, str]) -> None:
    markers.mkdir(exist_ok=True)
    for key, value in pairs:
        _git(git_dir, "config", "--file", str(git_dir / "config"), key, value)


def _plant_git_dir_inside(worktree: Path, controller: Path, markers: Path) -> None:
    """What an edit-only worker can do: write a git dir inside its worktree and point
    ``.git`` at it. Its config and hooks only touch markers."""
    planted = worktree / "planted"
    shutil.copytree(controller / ".git" / "objects", planted / "objects")
    (planted / "refs" / "heads").mkdir(parents=True)
    (planted / "HEAD").write_text(_git(worktree, "rev-parse", "HEAD") + "\n", encoding="utf-8")
    (planted / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
    _plant_hooks_and_fsmonitor(planted, markers)
    _plant_config(
        planted, markers, ("diff.external", f"sh -c \"touch '{markers}/diff.external'\" --")
    )
    (worktree / ".git").write_text("gitdir: planted\n", encoding="utf-8")


def _fired(markers: Path) -> list[str]:
    return sorted(p.name for p in markers.iterdir()) if markers.exists() else []


def _plain_diff_sha(worktree: Path, base: str, head: str) -> str:
    diff = subprocess.run(
        ["git", "diff", "--binary", base, head],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return hashlib.sha256(diff.encode("utf-8")).hexdigest()


# --- fanout ---------------------------------------------------------------------------


def _allocated(env: Path) -> tuple[Path, WorkspaceLease, ExecutionUnit]:
    repo, base = _controller(env)
    unit = _unit(base, ["a.py", "data.bin", "notes.txt", ".gitattributes"])
    lease = GitWorktreeAllocator(repo, env / "workspaces").allocate(unit)
    return repo, lease, unit


def test_fanout_capture_commits_the_candidate_without_running_a_hook_or_fsmonitor(env):
    repo, lease, unit = _allocated(env)
    markers = env / "markers"
    _plant_hooks_and_fsmonitor(repo / ".git", markers)
    worktree = Path(lease.path)
    (worktree / "a.py").write_text("VALUE = 2\n", encoding="utf-8")

    candidate = fanout._capture_candidate(unit, lease, expected_head=unit.expected_base_sha)

    assert _fired(markers) == []
    assert candidate["changed_paths"] == ["a.py"]
    assert _git(worktree, "rev-parse", "HEAD") == candidate["candidate_commit"]
    identity = fanout.eia_worker_identity(provider=unit.provider, model=unit.model)
    expected = f"{identity['name']} <{identity['email']}>"
    assert _git(worktree, "log", "-1", "--format=%an <%ae>|%cn <%ce>") == f"{expected}|{expected}"


def test_fanout_capture_diff_hash_is_the_plain_binary_diff_hash(env):
    _repo, lease, unit = _allocated(env)
    worktree = Path(lease.path)
    (worktree / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    (worktree / "data.bin").write_bytes(bytes(range(256)) * 4)
    (worktree / "notes.txt").write_text("naïve çà ünï\n", encoding="utf-8")

    candidate = fanout._capture_candidate(unit, lease, expected_head=unit.expected_base_sha)

    assert candidate["candidate_diff_sha256"] == _plain_diff_sha(
        worktree, unit.expected_base_sha, candidate["candidate_commit"]
    )
    assert candidate["changed_paths"] == ["a.py", "data.bin", "notes.txt"]


def test_fanout_capture_refuses_a_git_dir_the_worker_planted_in_its_worktree(env):
    repo, lease, unit = _allocated(env)
    markers = env / "markers"
    worktree = Path(lease.path)
    (worktree / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    _plant_git_dir_inside(worktree, repo, markers)

    with pytest.raises(FanoutError, match="WORKSPACE_GIT_DIR_UNTRUSTED"):
        fanout._capture_candidate(unit, lease, expected_head=unit.expected_base_sha)
    commit = fanout.eia_git_commit(worktree, subject="s", name="n", email="n@n", trailers=())

    assert commit.returncode != 0 and "WORKSPACE_GIT_DIR_UNTRUSTED" in commit.stderr
    assert _fired(markers) == []
    assert _git(repo, "rev-parse", "HEAD") == unit.expected_base_sha


def test_fanout_capture_refuses_a_worktree_registered_in_another_controller(env):
    _repo, lease, unit = _allocated(env)
    (Path(lease.path) / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    other = env / "other"
    other.mkdir()
    _git(other, "init", "-q")

    foreign = replace(lease, controller_root=str(other))
    with pytest.raises(FanoutError, match="WORKSPACE_GIT_DIR_UNTRUSTED"):
        fanout._capture_candidate(unit, foreign, expected_head=unit.expected_base_sha)


@pytest.mark.parametrize(
    "keys",
    [
        ("hook.mark.command", "hook.mark.event"),
        ("filter.mark.clean",),
        ("diff.external",),
        ("diff.mark.textconv",),
    ],
)
def test_fanout_capture_refuses_controller_config_that_names_a_program(env, keys):
    repo, lease, unit = _allocated(env)
    markers = env / "markers"
    (Path(lease.path) / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    program = f"sh -c \"touch '{markers}/program'\" --"
    _plant_config(
        repo / ".git",
        markers,
        *((key, "post-commit" if key.endswith(".event") else program) for key in keys),
    )
    (Path(lease.path) / ".gitattributes").write_text("*.py filter=mark diff=mark\n", "utf-8")

    with pytest.raises(FanoutError, match="WORKSPACE_GIT_CONFIG_NAMES_A_PROGRAM"):
        fanout._capture_candidate(unit, lease, expected_head=unit.expected_base_sha)
    assert _fired(markers) == []


def test_fanout_binding_recheck_refuses_a_planted_git_dir_before_any_git_call(env):
    repo, lease, unit = _allocated(env)
    markers = env / "markers"
    _plant_git_dir_inside(Path(lease.path), repo, markers)

    with pytest.raises(CoreBindingError, match="workspace_observation"):
        AdaptiveWorkerFanoutRuntime._revalidate_core_binding(unit, lease, {})
    assert _fired(markers) == []


def test_fanout_binding_recheck_reads_the_workspace_without_running_a_hook_or_fsmonitor(env):
    repo, lease, unit = _allocated(env)
    _git(repo, "remote", "add", "origin", "https://example.invalid/example/repo.git")
    markers = env / "markers"
    _plant_hooks_and_fsmonitor(repo / ".git", markers)

    with pytest.raises(CoreBindingError, match="bound_envelope_read"):
        AdaptiveWorkerFanoutRuntime._revalidate_core_binding(
            unit, lease, {"bound_envelope_ref": str(env / "missing.json")}
        )
    assert _fired(markers) == []


def _global_textconv(env: Path, monkeypatch: pytest.MonkeyPatch, markers: Path) -> None:
    """A textconv driver in the caller's global config: the hardened runner reads none."""
    markers.mkdir(exist_ok=True)
    script = env / "textconv.sh"
    script.write_text(f"#!/bin/sh\ntouch '{markers}/textconv'\necho converted\n", "utf-8")
    script.chmod(0o755)
    config = env / "global.gitconfig"
    config.write_text(f'[diff "mark"]\n\ttextconv = {script}\n', encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))


def test_fanout_capture_diff_runs_no_textconv_driver_from_the_global_config(env, monkeypatch):
    _repo, lease, unit = _allocated(env)
    markers = env / "markers"
    worktree = Path(lease.path)
    (worktree / ".gitattributes").write_text("*.py diff=mark\n", encoding="utf-8")
    (worktree / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    _global_textconv(env, monkeypatch, markers)

    candidate = fanout._capture_candidate(unit, lease, expected_head=unit.expected_base_sha)

    assert _fired(markers) == []
    assert candidate["changed_paths"] == [".gitattributes", "a.py"]


def test_fanout_runtime_leases_name_the_allocator_repository_as_controller(env):
    repo, lease, _unit_ = _allocated(env)
    runtime = AdaptiveWorkerFanoutRuntime.__new__(AdaptiveWorkerFanoutRuntime)
    runtime.allocator = GitWorktreeAllocator(repo, env / "workspaces")

    assert lease.controller_root == str(repo.resolve())
    assert runtime._controller_root() == str(repo.resolve())


# --- closure --------------------------------------------------------------------------


def test_closure_receipt_check_reads_the_workspace_without_running_a_hook_or_fsmonitor(env):
    repo, base = make_closure_repo(env)
    receipt = make_receipt(repo, env, base, "u1", "a.py", "A = 1\n")
    markers = env / "markers"
    _plant_hooks_and_fsmonitor(repo / ".git", markers)

    bound = closure.validate_worker_receipt(receipt)

    assert _fired(markers) == []
    assert bound["candidate_diff_sha256"] == receipt["candidate_diff_sha256"]
    assert bound["cumulative_changed_paths"] == ["a.py"]


def test_closure_receipt_check_refuses_a_git_dir_the_worker_planted(env):
    repo, base = make_closure_repo(env)
    receipt = make_receipt(repo, env, base, "u1", "a.py", "A = 1\n")
    markers = env / "markers"
    _plant_git_dir_inside(Path(receipt["workspace_path"]), repo, markers)

    with pytest.raises(closure.ClosureError, match="WORKSPACE_GIT_DIR_UNTRUSTED"):
        closure.validate_worker_receipt(receipt)
    with pytest.raises(closure.ClosureError, match="WORKSPACE_GIT_DIR_UNTRUSTED"):
        closure._run_verifier_specs(
            task_id="task-1",
            unit_id="u1",
            workspace_path=receipt["workspace_path"],
            candidate_commit=receipt["candidate_commit"],
            specs=[{"id": "v", "argv": ["true"]}],
            schema=closure.UNIT_VERIFICATION_SCHEMA,
            scope="UNIT",
            base_sha=base,
            authorized_paths=["a.py"],
            deletable_paths=[],
        )
    assert _fired(markers) == []


def test_closure_receipt_check_refuses_an_external_diff_driver(env):
    repo, base = make_closure_repo(env)
    receipt = make_receipt(repo, env, base, "u1", "a.py", "A = 1\n")
    markers = env / "markers"
    _plant_config(
        repo / ".git", markers, ("diff.external", f"sh -c \"touch '{markers}/diff.external'\" --")
    )

    with pytest.raises(closure.ClosureError, match="WORKSPACE_GIT_CONFIG_NAMES_A_PROGRAM"):
        closure.validate_worker_receipt(receipt)
    assert _fired(markers) == []


def test_closure_diff_hash_runs_no_textconv_driver_from_the_global_config(env, monkeypatch):
    repo, base = make_closure_repo(env)
    (repo / ".gitattributes").write_text("*.py diff=mark\n", encoding="utf-8")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-qm", "attributes")
    receipt = make_receipt(repo, env, _git(repo, "rev-parse", "HEAD"), "u1", "a.py", "A = 1\n")
    markers = env / "markers"
    _global_textconv(env, monkeypatch, markers)

    digest = closure._diff_sha(repo, receipt["parent_commit"], receipt["candidate_commit"])

    assert _fired(markers) == []
    assert digest == receipt["candidate_diff_sha256"]


def test_closure_composition_patch_is_the_raw_patch_not_a_diff_driver_rendering(env):
    repo, base = make_closure_repo(env)
    receipt = make_receipt(repo, env, base, "u1", "a.py", "A = 1\n")
    markers = env / "markers"
    textconv = env / "textconv.sh"
    textconv.write_text(f"#!/bin/sh\ntouch '{markers}/textconv'\necho converted\n", "utf-8")
    textconv.chmod(0o755)
    _plant_config(
        repo / ".git",
        markers,
        ("diff.external", f"sh -c \"touch '{markers}/diff.external'\" --"),
        ("diff.mark.textconv", str(textconv)),
    )
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("*.py diff=mark\n", encoding="utf-8")

    patch = closure._raw_diff_patch(repo, base, receipt["candidate_commit"])

    assert _fired(markers) == []
    assert "-A = 0\n+A = 1\n" in patch
    assert (
        hashlib.sha256(patch.strip().encode("utf-8")).hexdigest()
        == (receipt["candidate_diff_sha256"])
    )
