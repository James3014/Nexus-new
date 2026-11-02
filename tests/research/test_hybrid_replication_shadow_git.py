"""The harness reads an agent's shadow checkout without running a program that checkout names.

The agent may write every path under its shadow root, so the shadow git dir lives beside
that root and every harness git call is pinned to it. Every planted program only touches a
marker file under tmp_path.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

from nexus.research import hybrid_replication_live as live

_IDENTITY = ("-c", "user.name=Shadow Test", "-c", "user.email=shadow@test.invalid")
_HOOKS = ("post-checkout", "post-index-change", "pre-commit", "post-commit")
_SUBMODULE_COMMIT = "8a145b0f44470c25b32a2ebdc161bb3fbd588047"


def _clean_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    env["GIT_CEILING_DIRECTORIES"] = os.environ["GIT_CEILING_DIRECTORIES"]
    return env


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "commit.gpgSign=false",
            *_IDENTITY,
            *args,
        ],
        cwd=cwd,
        env=_clean_env(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    monkeypatch.chdir(sentinel)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return tmp_path


def _origin(root: Path, *, gitlink: bool = False) -> tuple[Path, str]:
    repo = root / "origin"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Shadow Test")
    _git(repo, "config", "user.email", "shadow@test.invalid")
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    if gitlink:
        _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{_SUBMODULE_COMMIT},sub")
    _git(repo, "commit", "-qm", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _plant_config(git_dir: Path, markers: Path, *, refused: bool = True) -> None:
    """What a writer of ``git_dir`` can do. ``refused=False`` plants only programs that
    command-line config switches off, so the repository is still read."""
    markers.mkdir(exist_ok=True)
    hooks = git_dir / "hooks"
    hooks.mkdir(exist_ok=True)
    for hook in _HOOKS:
        script = hooks / hook
        script.write_text(f"#!/bin/sh\ntouch '{markers}/hook.{hook}'\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    settings = [("core.fsmonitor", f"touch '{markers}/fsmonitor'; true")]
    if refused:
        settings += [
            ("diff.external", f"sh -c \"touch '{markers}/diff.external'\" --"),
            ("hook.planted.event", "post-index-change"),
            ("hook.planted.command", f"touch '{markers}/config-hook'"),
        ]
    for key, value in settings:
        subprocess.run(
            ["git", "--git-dir", str(git_dir), "config", key, value],
            env=_clean_env(),
            check=True,
            capture_output=True,
        )


def _plant_repository(root: Path, name: str, markers: Path) -> Path:
    """A repository written under the agent root, whose config names programs."""
    planted = root / name
    planted.mkdir(parents=True)
    _git(planted, "init", "-q")
    (planted / "x").write_text("x\n", encoding="utf-8")
    _git(planted, "add", "x")
    _git(planted, "commit", "-qm", "planted")
    _plant_config(planted / ".git", markers)
    return planted / ".git"


def _fired(markers: Path) -> list[str]:
    return sorted(path.name for path in markers.iterdir()) if markers.exists() else []


def _dispatch_result(cwd: Path, dispatch: Path) -> tuple[Any, ...]:
    record = {
        "operation_id": "agyop_shadow_git",
        "status": "COMPLETED",
        "provider": "agy",
        "observed_provider": "agy",
        "observed_model": live.EXACT_AGY_MODEL,
        "exit_code": 0,
    }
    return (
        record,
        1.0,
        dispatch.parent / "stdout.log",
        dispatch.parent / "stderr.log",
        False,
        None,
        dispatch,
    )


def _stub_dispatch(sandbox: Path, monkeypatch: pytest.MonkeyPatch, agent: Any) -> None:
    dispatch = sandbox / "dispatch" / live.CANONICAL_AGY_DISPATCH_NAME
    dispatch.parent.mkdir()
    dispatch.write_text("#!/bin/sh\n", encoding="utf-8")
    (dispatch.parent / "stdout.log").write_text("", encoding="utf-8")
    (dispatch.parent / "stderr.log").write_text("", encoding="utf-8")
    monkeypatch.setattr(live, "CANONICAL_AGY_DISPATCH_SHA256", live._sha256_file(dispatch))

    def fake_dispatch(**kwargs: Any) -> tuple[Any, ...]:
        cwd = Path(str(kwargs["cwd"]))
        agent(cwd)
        return _dispatch_result(cwd, dispatch)

    monkeypatch.setattr(live, "_run_agy_dispatch", fake_dispatch)


def _rewrite_gitfile(source: Path, markers: Path) -> None:
    """An edit-only agent points the shadow's ``.git`` at a repository it wrote (or, when
    ``.git`` is a directory under its root, writes that directory's config)."""
    if (source / ".git").is_dir():
        _plant_config(source / ".git", markers)
        return
    planted = _plant_repository(source, "planted", markers)
    (source / ".git").write_text(f"gitdir: {planted}\n", encoding="utf-8")


def test_seal_starts_no_program_named_by_the_repository_it_reads(sandbox: Path) -> None:
    source = sandbox / "source"
    source.mkdir()
    _git(source, "init", "-q")
    (source / "f.txt").write_text("a\n", encoding="utf-8")
    _git(source, "add", "f.txt")
    _git(source, "commit", "-qm", "base")
    markers = sandbox / "markers"
    _plant_config(source / ".git", markers)
    (source / "f.txt").write_text("changed by agent\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="shadow_candidate_config_refused"):
        live.seal_shadow_candidate(source)

    assert _fired(markers) == []


def test_seal_reads_a_repository_whose_remaining_programs_are_switched_off(sandbox: Path) -> None:
    source = sandbox / "source"
    source.mkdir()
    _git(source, "init", "-q")
    (source / "f.txt").write_text("a\n", encoding="utf-8")
    _git(source, "add", "f.txt")
    _git(source, "commit", "-qm", "base")
    markers = sandbox / "markers"
    _plant_config(source / ".git", markers, refused=False)
    (source / "f.txt").write_text("changed by agent\n", encoding="utf-8")
    (source / "new.txt").write_text("new\n", encoding="utf-8")

    sealing = live.seal_shadow_candidate(source)

    assert sealing["changed_files"] == ["f.txt", "new.txt"]
    assert _fired(markers) == []


def test_shadow_git_dir_lies_outside_the_agent_write_root(sandbox: Path) -> None:
    repo, revision = _origin(sandbox)
    source = sandbox / "shadow" / "source"
    source.parent.mkdir()

    live._prepare_shadow_checkout(repo=repo, revision=revision, source=source)

    git_dir = live._shadow_git_dir(source)
    assert git_dir.is_dir()
    assert not git_dir.resolve().is_relative_to(source.resolve())
    assert (source / ".git").is_file()
    grants = live._agy_permission_args(source, mode="accept-edits")
    write_roots = [
        grants[i + 1].removeprefix("write_file(").removesuffix("/**)")
        for i, flag in enumerate(grants)
        if flag == "--allow" and grants[i + 1].startswith("write_file(")
    ]
    assert write_roots == [str(source.resolve())]
    assert not git_dir.resolve().is_relative_to(Path(write_roots[0]))


def test_accept_edits_seal_ignores_a_rewritten_git_pointer(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    markers = sandbox / "markers"

    def agent(cwd: Path) -> None:
        (cwd / "f.txt").write_text("changed by agent\n", encoding="utf-8")
        _rewrite_gitfile(cwd, markers)

    _stub_dispatch(sandbox, monkeypatch, agent)

    receipt, _ = live._run_agy_candidate(
        repo=repo, revision=revision, prompt="edit", binding={}, allowed_paths=["f.txt"]
    )

    assert _fired(markers) == []
    assert "f.txt" in receipt["changed_files"]
    assert receipt["out_of_scope_paths"] == ["planted/"]


def test_accept_edits_seal_does_not_enter_a_planted_submodule(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox, gitlink=True)
    markers = sandbox / "markers"

    def agent(cwd: Path) -> None:
        planted = _plant_repository(cwd, "planted", markers)
        (cwd / "sub" / ".git").write_text(f"gitdir: {planted}\n", encoding="utf-8")
        (cwd / "sub" / "x").write_text("changed\n", encoding="utf-8")

    _stub_dispatch(sandbox, monkeypatch, agent)

    receipt, _ = live._run_agy_candidate(repo=repo, revision=revision, prompt="edit", binding={})

    assert _fired(markers) == []
    assert "sub" not in receipt["changed_files"]


def test_plan_mode_status_ignores_a_rewritten_git_pointer(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox, gitlink=True)
    markers = sandbox / "markers"

    def agent(cwd: Path) -> None:
        _rewrite_gitfile(cwd, markers)
        planted = _plant_repository(cwd, "planted-sub", markers)
        (cwd / "sub" / ".git").write_text(f"gitdir: {planted}\n", encoding="utf-8")
        (cwd / "sub" / "x").write_text("changed\n", encoding="utf-8")

    _stub_dispatch(sandbox, monkeypatch, agent)

    receipt, _ = live._run_agy_b_fallback(repo=repo, revision=revision, prompt="plan", binding={})

    assert _fired(markers) == []
    assert receipt["repository_mutated"] is True


def test_plan_mode_counts_a_git_dir_that_now_names_a_program_as_mutation(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    markers = sandbox / "markers"
    _stub_dispatch(
        sandbox,
        monkeypatch,
        lambda cwd: _plant_config(live._shadow_git_dir(cwd), markers),
    )

    receipt, _ = live._run_agy_b_fallback(repo=repo, revision=revision, prompt="plan", binding={})

    assert _fired(markers) == []
    assert receipt["repository_mutated"] is True
    assert receipt["valid"] is False


class _PersistentSlots:
    def __init__(self, root: Path) -> None:
        self.root = root

    def shadow_source(self, slot: str) -> Path:
        return self.root / "effects" / slot / "source"


@contextmanager
def _persistent(guard: _PersistentSlots, repo: Path, revision: str) -> Iterator[Path]:
    with live._agy_shadow_checkout(
        repo=repo,
        revision=revision,
        default_branch="main",
        prospective_guard=guard,  # type: ignore[arg-type]
        effect_slot="c",
    ) as source:
        yield source


def test_persistent_shadow_is_reused_when_its_git_dir_is_intact(sandbox: Path) -> None:
    repo, revision = _origin(sandbox)
    guard = _PersistentSlots(sandbox / "task")
    with _persistent(guard, repo, revision) as first:
        (first / "f.txt").write_text("partial\n", encoding="utf-8")

    with _persistent(guard, repo, revision) as again:
        assert again == first
        assert (again / "f.txt").read_text(encoding="utf-8") == "partial\n"


@pytest.mark.parametrize("tamper", ["git_dir_config", "gitfile", "legacy_in_tree_git_dir"])
def test_persistent_shadow_is_not_reused_after_its_git_metadata_changed(
    sandbox: Path, tamper: str
) -> None:
    repo, revision = _origin(sandbox)
    markers = sandbox / "markers"
    guard = _PersistentSlots(sandbox / "task")
    with _persistent(guard, repo, revision) as source:
        git_dir = live._shadow_git_dir(source)
        if tamper == "git_dir_config":
            _plant_config(git_dir, markers)
        elif tamper == "gitfile":
            _rewrite_gitfile(source, markers)
        else:
            (source / ".git").unlink()
            os.rename(git_dir, source / ".git")
            subprocess.run(
                ["git", "--git-dir", str(source / ".git"), "config", "--unset", "core.worktree"],
                env=_clean_env(),
                capture_output=True,
            )
            _plant_config(source / ".git", markers)

    with pytest.raises(RuntimeError, match="persistent_shadow"):
        with _persistent(guard, repo, revision):
            pass

    assert _fired(markers) == []


def test_persistent_shadow_is_not_reused_for_another_revision(sandbox: Path) -> None:
    repo, revision = _origin(sandbox)
    (repo / "f.txt").write_text("b\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "later")
    later = _git(repo, "rev-parse", "HEAD")
    guard = _PersistentSlots(sandbox / "task")
    with _persistent(guard, repo, revision):
        pass

    with pytest.raises(RuntimeError, match="persistent_shadow_revision_mismatch"):
        with _persistent(guard, repo, later):
            pass


def test_new_shadow_checkout_never_adopts_a_git_dir_left_beside_it(sandbox: Path) -> None:
    repo, revision = _origin(sandbox)
    markers = sandbox / "markers"
    source = sandbox / "task" / "source"
    stale = live._shadow_git_dir(source)
    stale.parent.mkdir()
    _git(stale.parent, "init", "-q", "--bare", stale.name)
    _plant_config(stale, markers)

    with pytest.raises(RuntimeError, match="shadow_git_dir_exists"):
        live._prepare_shadow_checkout(repo=repo, revision=revision, source=source)

    assert _fired(markers) == []
    assert not source.exists()


def test_plan_mode_counts_a_failing_status_as_mutation(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    _stub_dispatch(
        sandbox,
        monkeypatch,
        lambda cwd: (live._shadow_git_dir(cwd) / "index").write_bytes(b"not an index"),
    )

    receipt, _ = live._run_agy_b_fallback(repo=repo, revision=revision, prompt="plan", binding={})

    assert receipt["repository_mutated"] is True


def test_codex_candidate_seal_ignores_a_rewritten_git_pointer(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    markers = sandbox / "markers"
    codex = sandbox / "codex"
    codex.write_text("#!/bin/sh\n", encoding="utf-8")
    binding = {
        "strong_online": {
            "codex_binary": str(codex),
            "codex_cli": "codex-cli 0.0.0",
            "codex_executable_path": str(codex),
            "codex_executable_sha256": live.CODEX_EXECUTABLE_SHA256,
            "requested_model": "model",
        }
    }
    real_run = live._run

    def fake_run(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(argv)
        if argv[0] != str(codex):
            return real_run(argv, **kwargs)
        if argv[1:] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, "codex-cli 0.0.0\n", "")
        source = Path(argv[argv.index("-C") + 1])
        (source / "f.txt").write_text("changed by agent\n", encoding="utf-8")
        _rewrite_gitfile(source, markers)
        Path(argv[argv.index("-o") + 1]).write_text(json.dumps({"ok": True}), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(live, "_run", fake_run)
    monkeypatch.setattr(live, "_sha256_file", lambda _path: live.CODEX_EXECUTABLE_SHA256)

    receipt, _ = live._run_codex_candidate(
        repo=repo, revision=revision, prompt="edit", schema={}, binding=binding
    )

    assert _fired(markers) == []
    assert receipt["changed_files"] == ["f.txt", "planted/"]
