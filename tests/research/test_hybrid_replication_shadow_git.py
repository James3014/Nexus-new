"""The harness reads an agent's shadow checkout without running a program that checkout names.

The agent may write every path under its shadow root, so the shadow git dir lives beside
that root and every harness git call is pinned to it. Every planted program only touches a
marker file under tmp_path.
"""

from __future__ import annotations

import hashlib
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


def test_seal_does_not_read_untracked_links_into_the_receipt(sandbox: Path) -> None:
    # #3130 item 4: an untracked link (or hard link) in the shadow checkout is refused,
    # never read, so bytes from outside the checkout are not sealed into the receipt.
    outside = sandbox / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_bytes(b"host-secret-bytes")
    source = sandbox / "source"
    source.mkdir()
    _git(source, "init", "-q")
    (source / "f.txt").write_text("a\n", encoding="utf-8")
    _git(source, "add", "f.txt")
    _git(source, "commit", "-qm", "base")
    (source / "new.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "leak.txt").symlink_to(secret)
    os.link(secret, source / "hard.txt")

    sealing = live.seal_shadow_candidate(source)

    assert [row["path"] for row in sealing["untracked_files"]] == ["new.py"]
    assert sealing["refused_untracked_files"] == ["hard.txt", "leak.txt"]
    assert sealing["scope_valid"] is False
    secret_sha = hashlib.sha256(b"host-secret-bytes").hexdigest()
    assert all(row["sha256"] != secret_sha for row in sealing["untracked_files"])


def test_seal_skips_untracked_directory_links(sandbox: Path) -> None:
    # A link to a directory carries no bytes: it is skipped as before #3130 item 4, keeps the
    # scope valid, and nothing under its target is sealed (test-tool temp-dir links and
    # agent-made virtualenv links are real producers).
    outside = sandbox / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"host-secret-bytes")
    source = sandbox / "source"
    (source / "pkg").mkdir(parents=True)
    _git(source, "init", "-q")
    (source / "pkg" / "f.txt").write_text("a\n", encoding="utf-8")
    _git(source, "add", "pkg/f.txt")
    _git(source, "commit", "-qm", "base")
    (source / "new.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "outdir-current").symlink_to(outside, target_is_directory=True)
    (source / "pkgdir").symlink_to("pkg", target_is_directory=True)

    sealing = live.seal_shadow_candidate(source)

    assert sorted(sealing["changed_files"]) == ["new.py", "outdir-current", "pkgdir"]
    assert [row["path"] for row in sealing["untracked_files"]] == ["new.py"]
    assert sealing["refused_untracked_files"] == []
    assert sealing["scope_valid"] is True
    secret_sha = hashlib.sha256(b"host-secret-bytes").hexdigest()
    assert all(row["sha256"] != secret_sha for row in sealing["untracked_files"])


def _plant_outside_file_link(sandbox: Path, cwd: Path) -> None:
    outside = sandbox / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_bytes(b"host-secret-bytes")
    (cwd / "leak.txt").symlink_to(outside / "secret.txt")


def test_accept_edits_candidate_with_an_untracked_file_link_is_linked_artifact_rejected(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)

    def agent(cwd: Path) -> None:
        (cwd / "f.txt").write_text("changed by agent\n", encoding="utf-8")
        _plant_outside_file_link(sandbox, cwd)

    _stub_dispatch(sandbox, monkeypatch, agent)

    receipt, _ = live._run_agy_candidate(repo=repo, revision=revision, prompt="edit", binding={})

    assert receipt["refused_untracked_files"] == ["leak.txt"]
    assert receipt["status"] == "LINKED_ARTIFACT_REJECTED"
    assert receipt["valid"] is False


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


def test_codex_candidate_with_an_untracked_file_link_is_protocol_invalid(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
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
        _plant_outside_file_link(sandbox, source)
        Path(argv[argv.index("-o") + 1]).write_text(json.dumps({"ok": True}), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(live, "_run", fake_run)
    monkeypatch.setattr(live, "_sha256_file", lambda _path: live.CODEX_EXECUTABLE_SHA256)

    receipt, _ = live._run_codex_candidate(
        repo=repo, revision=revision, prompt="edit", schema={}, binding=binding
    )

    assert receipt["refused_untracked_files"] == ["leak.txt"]
    assert receipt["oversized_untracked_files"] == []
    assert receipt["forbidden_commands"] == []
    assert receipt["protocol_valid"] is False
    assert receipt["status"] == "INVALID"


def _tracked_repo(sandbox: Path) -> Path:
    source = sandbox / "tsource"
    source.mkdir()
    _git(source, "init", "-q")
    (source / "f.txt").write_text("a\n", encoding="utf-8")
    (source / "g.txt").write_text("b\n", encoding="utf-8")
    _git(source, "add", "f.txt", "g.txt")
    _git(source, "commit", "-qm", "base")
    return source


def test_seal_refuses_a_tracked_file_replaced_by_a_hard_link(sandbox: Path) -> None:
    source = _tracked_repo(sandbox)
    outside = sandbox / "outside.txt"
    outside.write_text("OUTSIDE-SECRET\n", encoding="utf-8")
    (source / "f.txt").unlink()
    os.link(outside, source / "f.txt")

    sealing = live.seal_shadow_candidate(source)

    assert sealing["refused_untracked_files"] == ["f.txt"]
    assert sealing["scope_valid"] is False


def test_seal_refuses_a_tracked_file_replaced_by_a_symlink(sandbox: Path) -> None:
    source = _tracked_repo(sandbox)
    outside = sandbox / "outside.txt"
    outside.write_text("OUTSIDE-SECRET\n", encoding="utf-8")
    (source / "f.txt").unlink()
    (source / "f.txt").symlink_to(outside)

    sealing = live.seal_shadow_candidate(source)

    assert sealing["refused_untracked_files"] == ["f.txt"]
    assert sealing["scope_valid"] is False


def test_seal_still_seals_a_plain_tracked_edit_and_a_deletion(sandbox: Path) -> None:
    source = _tracked_repo(sandbox)
    (source / "f.txt").write_text("edited\n", encoding="utf-8")
    (source / "g.txt").unlink()

    sealing = live.seal_shadow_candidate(source)

    assert sealing["changed_files"] == ["f.txt", "g.txt"]
    assert sealing["refused_untracked_files"] == []
    assert sealing["scope_valid"] is True


def test_seal_refuses_when_head_moved_off_the_revision(sandbox: Path) -> None:
    source = _tracked_repo(sandbox)
    revision = _git(source, "rev-parse", "HEAD").strip()
    (source / "f.txt").write_text("edited\n", encoding="utf-8")
    _git(source, "add", "f.txt")
    _git(source, "commit", "-qm", "agent moved HEAD")

    with pytest.raises(RuntimeError, match="shadow_candidate_head_moved"):
        live.seal_shadow_candidate(source, revision=revision)
    sealing = live.seal_shadow_candidate(source, revision=_git(source, "rev-parse", "HEAD").strip())
    assert sealing["scope_valid"] is True


def _candidate_with_shadow_change(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch, tamper: Any
) -> tuple[dict[str, Any], float]:
    repo, revision = _origin(sandbox)

    def agent(cwd: Path) -> None:
        (cwd / "f.txt").write_text("changed by agent\n", encoding="utf-8")
        if tamper is not None:
            tamper(live._shadow_git_dir(cwd))

    _stub_dispatch(sandbox, monkeypatch, agent)
    return live._run_agy_candidate(repo=repo, revision=revision, prompt="edit", binding={})


def test_seal_is_refused_when_a_new_file_appears_in_the_shadow_git_dir(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def tamper(git_dir: Path) -> None:
        (git_dir / "planted").write_text("x", encoding="utf-8")

    with pytest.raises(RuntimeError, match="shadow_git_dir_changed"):
        _candidate_with_shadow_change(sandbox, monkeypatch, tamper)


def test_seal_is_refused_when_a_ref_in_the_shadow_git_dir_is_rewritten(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def tamper(git_dir: Path) -> None:
        (git_dir / "refs" / "heads" / "other").write_text("0" * 40 + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="shadow_git_dir_changed"):
        _candidate_with_shadow_change(sandbox, monkeypatch, tamper)


def test_seal_still_proceeds_when_the_shadow_git_dir_is_untouched(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, _ = _candidate_with_shadow_change(sandbox, monkeypatch, None)

    assert receipt["changed_files"] == ["f.txt"]


def test_plan_mode_counts_a_changed_shadow_git_dir_as_mutation(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)

    def agent(cwd: Path) -> None:
        (live._shadow_git_dir(cwd) / "planted").write_text("x", encoding="utf-8")

    _stub_dispatch(sandbox, monkeypatch, agent)
    receipt, _ = live._run_agy_b_fallback(repo=repo, revision=revision, prompt="plan", binding={})

    assert receipt["repository_mutated"] is True


def _persistent_candidate(
    guard: _PersistentSlots, repo: Path, revision: str, agent: Any
) -> dict[str, Any]:
    receipt, _ = live._run_agy_candidate(
        repo=repo,
        revision=revision,
        prompt="edit",
        binding={},
        prospective_guard=guard,  # type: ignore[arg-type]
    )
    return receipt


def test_resumed_persistent_shadow_is_compared_with_the_digest_stored_at_creation(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    guard = _PersistentSlots(sandbox / "task")
    calls: list[int] = []

    def agent(cwd: Path) -> None:
        calls.append(1)
        if len(calls) == 1:
            # The first run writes into the shadow git dir, then dies before it seals.
            (live._shadow_git_dir(cwd) / "planted").write_text("x", encoding="utf-8")
            raise KeyboardInterrupt
        (cwd / "f.txt").write_text("changed by agent\n", encoding="utf-8")

    _stub_dispatch(sandbox, monkeypatch, agent)
    with pytest.raises(KeyboardInterrupt):
        _persistent_candidate(guard, repo, revision, agent)

    with pytest.raises(RuntimeError, match="shadow_git_dir_changed"):
        _persistent_candidate(guard, repo, revision, agent)
    assert len(calls) == 2


def test_resumed_persistent_shadow_without_a_stored_digest_is_refused(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    guard = _PersistentSlots(sandbox / "task")
    _stub_dispatch(sandbox, monkeypatch, lambda cwd: None)
    _persistent_candidate(guard, repo, revision, None)
    source = guard.shadow_source("c")
    live._shadow_digest_path(source).unlink()

    with pytest.raises(RuntimeError, match="persistent_shadow_digest_missing"):
        _persistent_candidate(guard, repo, revision, None)


def test_stored_digest_is_never_overwritten_by_a_resume(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    guard = _PersistentSlots(sandbox / "task")
    _stub_dispatch(sandbox, monkeypatch, lambda cwd: None)
    _persistent_candidate(guard, repo, revision, None)
    stored = live._shadow_digest_path(guard.shadow_source("c"))
    first = stored.read_text(encoding="utf-8")
    _persistent_candidate(guard, repo, revision, None)

    assert stored.read_text(encoding="utf-8") == first


def test_seal_still_proceeds_when_the_agent_rewrites_a_file_and_runs_git_status(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    seen: dict[str, bytes] = {}

    def agent(cwd: Path) -> None:
        index = live._shadow_git_dir(cwd) / "index"
        seen["before"] = index.read_bytes()
        target = cwd / "f.txt"
        target.write_bytes(target.read_bytes())
        stat_info = target.stat()
        os.utime(target, ns=(stat_info.st_atime_ns, stat_info.st_mtime_ns + 10_000_000_000))
        _git(cwd, "status", "--porcelain")
        seen["after"] = index.read_bytes()

    _stub_dispatch(sandbox, monkeypatch, agent)
    receipt, _ = live._run_agy_candidate(repo=repo, revision=revision, prompt="edit", binding={})

    assert seen["before"] != seen["after"]
    assert receipt["changed_files"] == []


@pytest.mark.parametrize("target", ["HEAD", "config"])
def test_seal_is_refused_when_a_shadow_git_file_is_rewritten_in_place_at_the_same_size(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    def tamper(git_dir: Path) -> None:
        path = git_dir / target
        data = path.read_bytes()
        changed = data.replace(data[:1], b"X" if data[:1] != b"X" else b"Y", 1)
        assert len(changed) == len(data) and changed != data
        path.write_bytes(changed)

    with pytest.raises(RuntimeError, match="shadow_git_dir_changed"):
        _candidate_with_shadow_change(sandbox, monkeypatch, tamper)


def test_seal_is_refused_when_only_a_shadow_git_file_mode_changes(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def tamper(git_dir: Path) -> None:
        path = git_dir / "config"
        path.chmod(path.stat().st_mode ^ stat.S_IXUSR)

    with pytest.raises(RuntimeError, match="shadow_git_dir_changed"):
        _candidate_with_shadow_change(sandbox, monkeypatch, tamper)


def test_seal_refuses_a_separate_git_dir_given_without_a_digest(sandbox: Path) -> None:
    repo, revision = _origin(sandbox)
    source = sandbox / "shadow" / "source"
    source.parent.mkdir()
    live._prepare_shadow_checkout(repo=repo, revision=revision, source=source)

    with pytest.raises(RuntimeError, match="shadow_git_dir_digest_missing"):
        live.seal_shadow_candidate(source, git_dir=live._shadow_git_dir(source))


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_seal_sees_a_change_to_a_file_the_agent_marked_clean_in_the_index(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    repo, revision = _origin(sandbox)

    def agent(cwd: Path) -> None:
        _git(cwd, "update-index", flag, "f.txt")
        (cwd / "f.txt").write_text("changed by agent\n", encoding="utf-8")
        assert _git(cwd, "diff", "--name-only", "HEAD") == ""

    _stub_dispatch(sandbox, monkeypatch, agent)
    receipt, _ = live._run_agy_candidate(repo=repo, revision=revision, prompt="edit", binding={})

    assert receipt["changed_files"] == ["f.txt"]


def test_seal_sees_a_change_whose_stat_the_agent_copied_into_the_index(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)

    def agent(cwd: Path) -> None:
        target = cwd / "f.txt"
        target.write_text("b\n", encoding="utf-8")  # same size as the committed "a\n"
        os.utime(target, (1_000_000_000, 1_000_000_000))
        info = target.lstat()
        index = live._shadow_git_dir(cwd) / "index"
        data = bytearray(index.read_bytes())
        fields = [
            int(info.st_ctime),
            info.st_ctime_ns % 1_000_000_000,
            int(info.st_mtime),
            info.st_mtime_ns % 1_000_000_000,
            info.st_dev,
            info.st_ino,
        ]
        for at, value in enumerate(fields):
            data[12 + 4 * at : 16 + 4 * at] = (value & 0xFFFFFFFF).to_bytes(4, "big")
        data[12 + 36 : 12 + 40] = (info.st_size & 0xFFFFFFFF).to_bytes(4, "big")
        data[-20:] = hashlib.sha1(bytes(data[:-20])).digest()
        index.write_bytes(bytes(data))
        assert _git(cwd, "diff", "--name-only", "HEAD") == ""

    _stub_dispatch(sandbox, monkeypatch, agent)
    receipt, _ = live._run_agy_candidate(repo=repo, revision=revision, prompt="edit", binding={})

    assert receipt["changed_files"] == ["f.txt"]


def test_plan_mode_counts_a_change_hidden_by_an_index_flag_as_mutation(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)

    def agent(cwd: Path) -> None:
        _git(cwd, "update-index", "--assume-unchanged", "f.txt")
        (cwd / "f.txt").write_text("changed by agent\n", encoding="utf-8")

    _stub_dispatch(sandbox, monkeypatch, agent)
    receipt, _ = live._run_agy_b_fallback(repo=repo, revision=revision, prompt="plan", binding={})

    assert receipt["repository_mutated"] is True


def test_resume_reads_a_stored_digest_that_is_a_link_as_missing(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, revision = _origin(sandbox)
    guard = _PersistentSlots(sandbox / "task")
    _stub_dispatch(sandbox, monkeypatch, lambda cwd: None)
    _persistent_candidate(guard, repo, revision, None)
    stored = live._shadow_digest_path(guard.shadow_source("c"))
    elsewhere = sandbox / "elsewhere.digest"
    elsewhere.write_text(stored.read_text(encoding="utf-8"), encoding="utf-8")
    stored.unlink()
    stored.symlink_to(elsewhere)

    with pytest.raises(RuntimeError, match="persistent_shadow_digest_missing"):
        _persistent_candidate(guard, repo, revision, None)
