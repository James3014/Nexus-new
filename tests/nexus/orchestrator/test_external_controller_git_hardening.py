"""Hardened git for an external measurement Controller (Issue #2749, Refs #2721).

P1: every git call ``WorktreeManager`` makes for an accepted external
Controller (lease, ``worktree add``, status, capture) runs with fsmonitor,
hooks and transports disabled and without the inherited ``GIT_*`` env, so an
fsmonitor or post-checkout hook planted after validation never runs.

P2: a clean/smudge filter declared by the target (``.gitattributes`` or
``info/attributes`` plus a ``filter.*`` driver in its config) never runs: the
target is refused at validation, at the lease, and by every later hardened
call.

Live parity: a Controller outside the measurement root (or with the
measurement mode off) gets exactly the git argv and env it got before.

Every repository is a temporary git repository created here; no network.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from nexus.orchestrator import measure_external_target as met
from nexus.orchestrator import worktree_manager as wm_module
from nexus.orchestrator.measure_external_target import (
    FILTER_DRIVER_PRESENT,
    MEASURE_EXTERNAL_TARGET_ROOT_ENV,
    ExternalTargetError,
    external_git_context,
    hardened_git_argv,
    validate_external_target,
)
from nexus.orchestrator.task_contract import MutationMode, SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import WorktreeManager

_HARDENED = [
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "protocol.allow=never",
]  # fmt: skip


def _clean_env() -> dict[str, str]:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return environment


def _run(*args: str, cwd: Path) -> str:
    """Plain git as a test fixture would use it (repository config applies)."""
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_clean_env(),
    ).stdout.strip()


def _repo(path: Path, files: dict[str, str]) -> str:
    path.mkdir(parents=True, exist_ok=True)
    _run("init", "-q", "-b", "main", cwd=path)
    for name, text in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _run("add", "-A", cwd=path)
    _run("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "init", cwd=path)
    return _run("rev-parse", "HEAD", cwd=path)


def _script(path: Path, marker: Path, *, passthrough: bool = False, status: int = 1) -> Path:
    body = f'#!/bin/sh\ntouch "{marker}"\n' + ("exec cat\n" if passthrough else f"exit {status}\n")
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _contract(controller: Path, sha: str, target_root: Path, task_id: str = "ext-task"):
    return SelfHostedTaskContract(
        task_id=task_id,
        objective="Capture a bounded candidate",
        controller_revision=sha,
        target_base_revision=sha,
        controller_repo_root=str(controller),
        target_repo_root=str(target_root / task_id),
        target_worktree_root=str(target_root),
        allowed_files=["src/"],
        forbidden_files=[],
        verifier_commands=["python -c pass"],
        protected_contracts=[],
        preferred_provider=None,
        fallback_provider=None,
        maximum_provider_calls=0,
        maximum_replans=0,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )


@pytest.fixture
def ext(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """An external repository under a measurement root, validated, mode on."""
    nexus_root = tmp_path / "nexus-controller"
    _repo(nexus_root, {"tasks/README.md": "cards\n"})
    measure_root = tmp_path / "measure"
    measure_root.mkdir()
    repo = measure_root / "extrepo"
    sha = _repo(repo, {"src/allowed.txt": "base\n", "data.txt": "data\n"})
    target_root = tmp_path / "targets"
    target_root.mkdir()
    markers = tmp_path / "markers"
    markers.mkdir()
    env = {MEASURE_EXTERNAL_TARGET_ROOT_ENV: str(measure_root)}
    monkeypatch.setattr(met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(measure_root))
    monkeypatch.delenv("NEXUS_CANONICAL_GIT_HOOKS_DIR", raising=False)
    return {
        "nexus_root": nexus_root,
        "measure_root": measure_root,
        "repo": repo,
        "sha": sha,
        "target_root": target_root,
        "markers": markers,
        "env": env,
        "tmp": tmp_path,
    }


def _validate(ctx: dict[str, Any]):
    return validate_external_target(
        {"repo_root": str(ctx["repo"]), "base_revision": ctx["sha"]},
        nexus_root=ctx["nexus_root"],
        env=ctx["env"],
    )


def _plant_commands(ctx: dict[str, Any]) -> dict[str, Path]:
    """fsmonitor + post-checkout hooks in every place the pre-#2749 lease looked."""
    repo, markers, tmp = ctx["repo"], ctx["markers"], ctx["tmp"]
    planted = {
        "fsmonitor": markers / "fsmonitor-ran",
        "config_hook": markers / "config-hook-ran",
        "dotgit_hook": markers / "dotgit-hook-ran",
        "derived_hook": markers / "derived-hook-ran",
        "trace": markers / "inherited-git-trace",
    }
    _run(
        "config", "core.fsmonitor",
        str(_script(tmp / "fsmonitor.sh", planted["fsmonitor"])), cwd=repo,
    )  # fmt: skip
    hooks = tmp / "planted-hooks"
    hooks.mkdir()
    _script(hooks / "post-checkout", planted["config_hook"], status=0)
    _run("config", "core.hooksPath", str(hooks), cwd=repo)
    _script(repo / ".git" / "hooks" / "post-checkout", planted["dotgit_hook"], status=0)
    # The pre-#2749 lease used a hooks dir derived from the Controller's
    # location, which for an external Controller is inside the measurement root.
    derived = wm_module.get_canonical_git_hooks_dir(repo)
    _script(derived / "post-checkout", planted["derived_hook"], status=0)
    return planted


# --------------------------------------------------------------------------
# P1
# --------------------------------------------------------------------------


def test_p1_positive_control_plain_git_runs_the_planted_commands(ext):
    """The plants are live: plain git with the same config runs both."""
    _validate(ext)
    planted = _plant_commands(ext)
    _run("status", "--porcelain", cwd=ext["repo"])
    _run("worktree", "add", "-q", str(ext["tmp"] / "plain-wt"), ext["sha"], cwd=ext["repo"])
    assert planted["fsmonitor"].exists()
    assert planted["config_hook"].exists()


def test_p1_lease_and_capture_never_run_planted_fsmonitor_hooks_or_inherited_git_env(
    ext, monkeypatch
):
    _validate(ext)
    planted = _plant_commands(ext)
    # Inherited GIT_* in the Gateway env must not reach any lease git call.
    monkeypatch.setenv("GIT_TRACE", str(planted["trace"]))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(ext["tmp"] / "fsmonitor.sh"))

    calls: list[tuple[list[str], dict[str, Any]]] = []
    real_run = subprocess.run

    def spy(args, **kwargs):
        if list(args)[:1] == ["git"]:
            calls.append((list(args), kwargs))
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    contract = _contract(ext["repo"], ext["sha"], ext["target_root"])
    manager = WorktreeManager(root_dir=str(ext["target_root"]))
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "src" / "allowed.txt").write_text("changed\n", encoding="utf-8")
    receipt = manager.capture_candidate(contract, lease)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert lease.initial_head == ext["sha"]
    assert receipt.changed_files == ["src/allowed.txt"]
    for name, marker in planted.items():
        assert not marker.exists(), name
    commands = [args[args.index("commit.gpgSign=false") + 1 :] for args, _ in calls]
    assert ["status", "--porcelain=v1", "-z", "--untracked-files=all"] in commands
    assert any(command[:2] == ["worktree", "add"] for command in commands)
    assert any(command[:1] == ["diff"] for command in commands)
    for args, kwargs in calls:
        flags = [a for a in args if not a.startswith("--attr-source=")]
        assert flags[1:7] == _HARDENED, args
        environment = kwargs["env"]
        assert sorted(k for k in environment if k.startswith("GIT_")) == [
            "GIT_ATTR_NOSYSTEM",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_TERMINAL_PROMPT",
        ], args
        assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
        assert environment["GIT_TERMINAL_PROMPT"] == "0"
        assert kwargs["stdin"] is subprocess.DEVNULL
    worktree_add = next(args for args, _ in calls if "worktree" in args and "add" in args)
    assert worktree_add[1] == f"--attr-source={ext['sha']}"


def test_hardened_argv_keeps_caller_config_but_hardened_values_win():
    argv = hardened_git_argv(
        ["-c", "user.name=n", "-c", "core.hooksPath=/hooks", "commit", "-m", "x"],
        attr_source="a" * 40,
    )
    assert argv[:6] == [
        "git",
        f"--attr-source={'a' * 40}",
        "-c",
        "user.name=n",
        "-c",
        "core.hooksPath=/hooks",
    ]
    assert argv[6:12] == _HARDENED
    assert argv[-3:] == ["commit", "-m", "x"]


def test_external_git_context_fails_closed_and_is_off_without_the_mode(ext, tmp_path, monkeypatch):
    not_a_repo = tmp_path / "plain-dir"
    not_a_repo.mkdir()
    assert external_git_context(ext["repo"]) is True
    assert external_git_context(ext["nexus_root"]) is False
    assert external_git_context(not_a_repo) is True
    monkeypatch.setenv("GIT_DIR", str(ext["nexus_root"] / ".git"))
    assert external_git_context(ext["nexus_root"]) is True
    monkeypatch.setattr(met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", "")
    assert external_git_context(ext["repo"]) is False
    assert external_git_context(not_a_repo) is False


# --------------------------------------------------------------------------
# P2
# --------------------------------------------------------------------------


def _plant_filter_driver(repo: Path, tmp: Path, marker: Path) -> None:
    script = _script(tmp / "filter.sh", marker, passthrough=True)
    _run("config", "filter.ctl.clean", str(script), cwd=repo)
    _run("config", "filter.ctl.smudge", str(script), cwd=repo)


@pytest.mark.parametrize(
    "variant", ["gitattributes_and_driver", "gitattributes_only", "driver_only", "info_attributes"]
)
def test_p2_validation_refuses_a_target_with_a_filter(ext, variant):
    repo, marker = ext["repo"], ext["markers"] / "filter-ran"
    if variant.startswith("gitattributes"):
        (repo / ".gitattributes").write_text("*.txt filter=ctl\n", encoding="utf-8")
        _run("add", ".gitattributes", cwd=repo)
        _run("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "attrs", cwd=repo)
        ext["sha"] = _run("rev-parse", "HEAD", cwd=repo)
    if variant in {"gitattributes_and_driver", "driver_only"}:
        _plant_filter_driver(repo, ext["tmp"], marker)
    if variant == "info_attributes":
        (repo / ".git" / "info").mkdir(exist_ok=True)
        (repo / ".git" / "info" / "attributes").write_text("*.txt filter=ctl\n", encoding="utf-8")
    # Make every tracked file look modified so status would consult the filter.
    (repo / "data.txt").touch()
    with pytest.raises(ExternalTargetError) as caught:
        _validate(ext)
    assert str(caught.value) == FILTER_DRIVER_PRESENT
    assert not marker.exists()


def _chain(exc: BaseException) -> str:
    seen = []
    current: BaseException | None = exc
    while current is not None:
        seen.append(str(current))
        current = current.__cause__ or current.__context__
    return " | ".join(seen)


def test_p2_filter_planted_after_validation_is_refused_at_the_lease(ext):
    _validate(ext)
    marker = ext["markers"] / "filter-ran"
    _plant_filter_driver(ext["repo"], ext["tmp"], marker)
    info = ext["repo"] / ".git" / "info"
    info.mkdir(exist_ok=True)
    (info / "attributes").write_text("*.txt filter=ctl\n", encoding="utf-8")
    contract = _contract(ext["repo"], ext["sha"], ext["target_root"])
    manager = WorktreeManager(root_dir=str(ext["target_root"]))
    with pytest.raises(RuntimeError) as caught:
        manager.create_lease(contract)
    assert FILTER_DRIVER_PRESENT in _chain(caught.value)
    assert not marker.exists()
    assert not (ext["target_root"] / "ext-task").exists()


def test_p2_attributes_planted_after_validation_are_refused_by_the_lease_recheck(ext):
    """No driver yet, but ``info/attributes`` names one: the lease re-check refuses."""
    _validate(ext)
    info = ext["repo"] / ".git" / "info"
    info.mkdir(exist_ok=True)
    (info / "attributes").write_text("*.txt filter=ctl\n", encoding="utf-8")
    contract = _contract(ext["repo"], ext["sha"], ext["target_root"])
    manager = WorktreeManager(root_dir=str(ext["target_root"]))
    with pytest.raises(RuntimeError) as caught:
        manager.create_lease(contract)
    assert str(caught.value) == FILTER_DRIVER_PRESENT
    assert not (ext["target_root"] / "ext-task").exists()


def test_p2_filter_planted_after_the_lease_never_runs_during_capture(ext):
    _validate(ext)
    contract = _contract(ext["repo"], ext["sha"], ext["target_root"])
    manager = WorktreeManager(root_dir=str(ext["target_root"]))
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    marker = ext["markers"] / "filter-ran"
    _plant_filter_driver(ext["repo"], ext["tmp"], marker)
    info = ext["repo"] / ".git" / "info"
    info.mkdir(exist_ok=True)
    (info / "attributes").write_text("*.txt filter=ctl\n", encoding="utf-8")
    (target / "src" / "allowed.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError) as caught:
        manager.capture_candidate(contract, lease)
    assert FILTER_DRIVER_PRESENT in _chain(caught.value)
    assert not marker.exists()


# --------------------------------------------------------------------------
# Live parity
# --------------------------------------------------------------------------


def _recorded_lease_and_capture(base: Path, monkeypatch) -> list[tuple[list[str], Any, Any]]:
    controller = base / "controller"
    sha = _repo(controller, {"src/allowed.txt": "base\n"})
    target_root = base / "targets"
    target_root.mkdir()
    calls: list[tuple[list[str], Any, Any]] = []
    real_run = subprocess.run

    def spy(args, **kwargs):
        if list(args)[:1] == ["git"]:
            calls.append((
                [str(a).replace(str(base), "<BASE>").replace(sha, "<SHA>") for a in args],
                kwargs.get("env"),
                kwargs.get("stdin", "<absent>"),
            ))
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    try:
        contract = _contract(controller, sha, target_root, task_id="live-task")
        manager = WorktreeManager(root_dir=str(target_root))
        lease = manager.create_lease(contract)
        (Path(lease.target_worktree) / "src" / "allowed.txt").write_text("x\n", encoding="utf-8")
        manager.capture_candidate(contract, lease)
    finally:
        monkeypatch.setattr(subprocess, "run", real_run)
    return calls


def test_live_parity_non_external_controller_git_argv_and_env_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_CANONICAL_GIT_HOOKS_DIR", raising=False)
    monkeypatch.setattr(met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", "")
    live = _recorded_lease_and_capture(tmp_path / "live", monkeypatch)
    measure_root = tmp_path / "elsewhere-measure"
    measure_root.mkdir()
    monkeypatch.setattr(met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(measure_root))
    other = _recorded_lease_and_capture(tmp_path / "other", monkeypatch)

    expected_env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    hooks = "core.hooksPath=<BASE>/nexus-runtime-targets/.nexus_git_hooks"
    assert live, "no git call recorded"
    for args, env, stdin in live:
        assert stdin == "<absent>"
        if args[:3] == ["git", "-c", "core.hooksPath=/dev/null"]:
            continue  # the ownership-record probe, unchanged
        assert args[:3] == ["git", "-c", "core.fsmonitor=false"], args
        assert args[3] == "-c" and args[4] in {
            hooks,
            "core.hooksPath=<BASE>/targets/nexus-runtime-targets/.nexus_git_hooks",
        }, args
        assert not any(a.startswith("--attr-source") or a == "protocol.allow=never" for a in args)
        assert env == expected_env
    # A Controller outside the measurement root: byte-identical argv and env.
    assert [args for args, _, _ in other] == [args for args, _, _ in live]
    assert [env for _, env, _ in other] == [env for _, env, _ in live]
    assert [stdin for _, _, stdin in other] == [stdin for _, _, stdin in live]
