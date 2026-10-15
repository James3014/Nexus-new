"""A separate Controller worktree keeps Task Card binds out of the loaded deployment (#1939)."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator import canonical_source_root as roots
from tests.nexus.orchestrator.test_unified_mcp_gateway import (
    AUTHORITY_ARGS,
    FakeService,
    _allow_owner_effect_authority,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(root: Path, path: str, text: str, message: str) -> str:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(root, "add", "--", path)
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture(autouse=True)
def _isolated_git_config(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path, str]:
    """A loaded deployment worktree and a Controller worktree of the same repository."""
    loaded = tmp_path / "deployments" / "a1-x"
    loaded.mkdir(parents=True)
    _git(loaded, "init", "-q")
    _git(loaded, "config", "user.name", "Nexus Test")
    _git(loaded, "config", "user.email", "nexus-test@example.invalid")
    head = _commit(loaded, "README.md", "base\n", "base")
    _git(loaded, "checkout", "-q", "--detach", head)
    controller = tmp_path / "controllers" / "a1-x"
    controller.parent.mkdir(parents=True)
    _git(loaded, "worktree", "add", "-q", "--detach", str(controller), head)
    return loaded, controller, head


def test_fresh_controller_at_the_loaded_commit_is_bound(pair):
    loaded, controller, _ = pair
    assert roots.bound_controller_problem(controller, loaded) is None
    resolved = roots.resolve_canonical_source_root(
        {roots.CANONICAL_SOURCE_ROOT_ENV: str(controller)}, source_root=loaded
    )
    assert resolved == controller.resolve()


def test_controller_with_task_card_bind_commits_only_is_bound(pair):
    loaded, controller, _ = pair
    _commit(controller, "tasks/c/00-t.md", "card\n", "chore(tasks): bind t")
    assert roots.bound_controller_problem(controller, loaded) is None


def test_controller_with_code_changes_is_refused(pair):
    loaded, controller, _ = pair
    _commit(controller, "nexus/evil.py", "x = 1\n", "not a bind")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_CHANGES_OUTSIDE_TASKS"
    with pytest.raises(RuntimeError, match="SOURCE_MISMATCH:CONTROLLER_CHANGES_OUTSIDE_TASKS"):
        roots.resolve_canonical_source_root(
            {roots.CANONICAL_SOURCE_ROOT_ENV: str(controller)}, source_root=loaded
        )


def test_controller_not_descending_from_the_loaded_commit_is_refused(pair):
    loaded, controller, head = pair
    _git(controller, "checkout", "-q", "--orphan", "other")
    _git(controller, "rm", "-rq", "--cached", ".")
    _commit(controller, "tasks/c/00-t.md", "card\n", "unrelated root")
    assert roots.bound_controller_problem(controller, loaded) == "LOADED_COMMIT_NOT_ANCESTOR"
    assert _git(loaded, "rev-parse", "HEAD") == head


def test_controller_of_another_repository_is_refused(pair, tmp_path):
    loaded, _, _ = pair
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    _git(other, "config", "user.name", "Nexus Test")
    _git(other, "config", "user.email", "nexus-test@example.invalid")
    _commit(other, "README.md", "base\n", "base")
    assert roots.bound_controller_problem(other, loaded) == "DIFFERENT_REPOSITORY"


def test_task_card_bind_lands_in_controller_and_never_in_the_loaded_deployment(pair, monkeypatch):
    """#1939 acceptance: the Gateway never creates commits in the checkout it runs."""
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    loaded, controller, head = pair
    _allow_owner_effect_authority(monkeypatch)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", controller)
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", True)
    gateway = gateway_module.UnifiedMCPGateway(service=FakeService())

    create = gateway.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_card_create",
            "arguments": {
                **AUTHORITY_ARGS,
                "owner_confirmation": True,
                "campaign_id": "split",
                "task_id": "card",
                "objective": "Bind in the Controller.",
                "allowed_files": ["README.md"],
                "verifier_commands": ["git diff --check"],
            },
        },
    })
    created = create["result"]["structuredContent"]
    commit = gateway.handle({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_card_commit",
            "arguments": {
                **AUTHORITY_ARGS,
                "owner_confirmation": True,
                "campaign_id": "split",
                "task_id": "card",
                "expected_head": head,
                "card_hash": created["card_hash"],
                "index_hash": created["index_hash"],
            },
        },
    })
    payload = commit["result"]["structuredContent"]

    assert payload["status"] == "COMMITTED"
    # The Controller holds the bind commit and stays clean (worker leases need that).
    assert _git(controller, "rev-parse", "HEAD") == payload["commit_sha"]
    assert _git(controller, "status", "--porcelain=v1", "--untracked-files=all") == ""
    # The loaded deployment is untouched: same HEAD, clean, no card.
    assert _git(loaded, "rev-parse", "HEAD") == head
    assert _git(loaded, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert not (loaded / "tasks").exists()
    # Identity reports describe the loaded commit, not the bind commit.
    assert gateway_module._loaded_git("rev-parse", "HEAD").strip() == head
    assert roots.bound_controller_problem(controller, loaded) is None


def test_health_git_head_reports_the_loaded_commit(pair, monkeypatch):
    import scripts.ops.nexus_mcp_gateway_http as http_module

    loaded, controller, head = pair
    bind = _commit(controller, "tasks/c/00-t.md", "card\n", "chore(tasks): bind t")
    monkeypatch.setattr(http_module, "LOADED_SOURCE_ROOT", loaded)
    assert bind != head
    assert http_module._git_head() == head
    # GB-077 requires /health to name the evaluated (loaded) root, not the Controller.
    identity = http_module.runtime_identity(include_paths=True)
    assert identity["repo_root"] == str(loaded)
    assert identity["git_head"] == head
    public = http_module.runtime_identity()
    assert public["repo_root_sha256"] == hashlib.sha256(str(loaded).encode("utf-8")).hexdigest()


def _commit_raw(root: Path, message: str) -> None:
    _git(root, "commit", "-qm", message)


def test_symlink_under_tasks_is_refused(pair):
    loaded, controller, _ = pair
    (controller / "tasks").mkdir()
    (controller / "tasks" / "link.md").symlink_to("../README.md")
    _git(controller, "add", "--", "tasks/link.md")
    _commit_raw(controller, "symlink bind")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_BIND_NOT_REGULAR_FILE"


def test_gitlink_under_tasks_is_refused(pair):
    loaded, controller, head = pair
    _git(controller, "update-index", "--add", "--cacheinfo", f"160000,{head},tasks/sub")
    _commit_raw(controller, "gitlink bind")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_BIND_NOT_REGULAR_FILE"


@pytest.mark.parametrize("name", [".gitattributes", ".gitmodules", ".gitignore"])
def test_git_metadata_under_tasks_is_refused(pair, name):
    loaded, controller, _ = pair
    _commit(controller, f"tasks/{name}", "* filter=evil\n", "metadata bind")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_BIND_GIT_METADATA"


def test_dirty_tracked_file_or_untracked_code_in_controller_is_refused(pair):
    loaded, controller, _ = pair
    (controller / "README.md").write_text("changed\n", encoding="utf-8")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_WORKTREE_DIRTY"
    _git(controller, "checkout", "--", "README.md")
    (controller / "nexus").mkdir()
    (controller / "nexus" / "x.py").write_text("x = 1\n", encoding="utf-8")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_WORKTREE_DIRTY"


def test_pending_untracked_card_is_allowed(pair):
    loaded, controller, _ = pair
    (controller / "tasks" / "c").mkdir(parents=True)
    (controller / "tasks" / "c" / "00-t.md").write_text("card\n", encoding="utf-8")
    assert roots.bound_controller_problem(controller, loaded) is None


def test_checkout_sharing_the_git_dir_through_a_symlink_is_refused(pair, tmp_path):
    """Another directory whose .git is a symlink to the loaded repository is not a Controller."""
    loaded, _, _ = pair
    other = tmp_path / "other"
    other.mkdir()
    (other / ".git").symlink_to(loaded / ".git")
    (other / "nexus").mkdir()
    (other / "nexus" / "evil.py").write_text("x = 1\n", encoding="utf-8")
    assert roots.bound_controller_problem(other, loaded) == "CONTROLLER_SHARES_LOADED_GITDIR"
    with pytest.raises(RuntimeError, match="SOURCE_MISMATCH"):
        roots.resolve_canonical_source_root(
            {roots.CANONICAL_SOURCE_ROOT_ENV: str(other)}, source_root=loaded
        )


def test_controller_drift_after_startup_blocks_task_card_effects(pair, monkeypatch):
    """TOCTOU: a Controller that drifts after startup is re-checked before each effect."""
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    loaded, controller, _ = pair
    _allow_owner_effect_authority(monkeypatch)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", controller)
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", True)
    _commit(controller, "nexus/evil.py", "x = 1\n", "drift after startup")
    gateway = gateway_module.UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_card_create",
            "arguments": {
                **AUTHORITY_ARGS,
                "owner_confirmation": True,
                "campaign_id": "drift",
                "task_id": "card",
                "objective": "x",
                "allowed_files": ["README.md"],
                "verifier_commands": ["git diff --check"],
            },
        },
    })
    assert response["result"]["isError"] is True
    assert (
        "CONTROLLER_BINDING_INVALID:CONTROLLER_CHANGES_OUTSIDE_TASKS"
        in response["result"]["structuredContent"]["error"]
    )
    assert not (controller / "tasks").exists()


def test_runtime_identity_hashing_reads_the_loaded_checkout(pair, monkeypatch):
    """(d) runtime/action/permission fingerprints default to LOADED_SOURCE_ROOT."""
    import inspect

    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    for function in (
        gateway_module._hash_source_paths,
        gateway_module._action_contract_fingerprint,
        gateway_module._permission_enforcement_fingerprint,
    ):
        assert inspect.signature(function).parameters["root"].default is roots.LOADED_SOURCE_ROOT
    source = inspect.getsource(gateway_module._loaded_runtime_source_paths)
    assert "LOADED_SOURCE_ROOT" in source and "CANONICAL_SOURCE_ROOT" not in source


def test_clean_alias_of_the_loaded_gitdir_is_refused(pair, tmp_path):
    """A clean checkout whose .git aliases the loaded gitdir would move the loaded HEAD."""
    loaded, _, _ = pair
    gitdir = Path(_git(loaded, "rev-parse", "--absolute-git-dir"))
    alias = tmp_path / "alias"
    alias.mkdir()
    (alias / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    _git(alias, "checkout", "-q", "--", ".")
    assert roots.bound_controller_problem(alias, loaded) == "CONTROLLER_SHARES_LOADED_GITDIR"
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").symlink_to(loaded / ".git")
    _git(linked, "checkout", "-q", "--", ".")
    assert roots.bound_controller_problem(linked, loaded) == "CONTROLLER_SHARES_LOADED_GITDIR"


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_hidden_tracked_edits_are_refused(pair, flag):
    loaded, controller, _ = pair
    _git(controller, "update-index", flag, "README.md")
    (controller / "README.md").write_text("hidden edit\n", encoding="utf-8")
    assert _git(controller, "status", "--porcelain") == ""
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_INDEX_FLAGGED"


def test_untracked_symlink_under_tasks_is_refused(pair, tmp_path):
    loaded, controller, _ = pair
    (controller / "tasks").mkdir()
    (controller / "tasks" / "c").symlink_to(tmp_path)
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_BIND_NOT_REGULAR_FILE"


@pytest.mark.parametrize("name", [".GitAttributes", ".GITMODULES", ".GitIgnore"])
def test_case_variant_git_metadata_is_refused(pair, name):
    loaded, controller, _ = pair
    _commit(controller, f"tasks/c/{name}", "* eol=crlf\n", "case variant")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_BIND_GIT_METADATA"


@pytest.mark.parametrize("path", ["tasks/../x.md", "tasks//x.md", "tasks/./x.md"])
def test_bind_paths_with_dot_segments_are_refused(path):
    assert roots._bind_path_problem(path) == "CONTROLLER_BIND_PATH_INVALID"


def test_controller_must_be_a_registered_worktree(pair, tmp_path):
    loaded, controller, _ = pair
    copy = tmp_path / "copy"
    subprocess.run(["cp", "-R", str(controller), str(copy)], check=True)
    # The copy reuses the Controller's gitdir file: same gitdir as the Controller,
    # but it is not the registered worktree path.
    assert roots.bound_controller_problem(copy, loaded) == "CONTROLLER_NOT_A_REGISTERED_WORKTREE"


def test_mutation_admit_and_finish_recheck_the_controller(pair, monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    loaded, controller, _ = pair
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", controller)
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", True)
    _commit(controller, "nexus/evil.py", "x = 1\n", "drift")
    gateway = gateway_module.UnifiedMCPGateway(service=FakeService())
    for method in (gateway._mutation_admit, gateway._finish):
        with pytest.raises(gateway_module.GatewayInputError, match="CONTROLLER_BINDING_INVALID"):
            method({})


def test_controller_git_pointing_at_a_third_worktrees_gitdir_is_refused(pair, tmp_path):
    loaded, controller, head = pair
    third = tmp_path / "third"
    _git(loaded, "worktree", "add", "-q", "--detach", str(third), head)
    third_gitdir = _git(third, "rev-parse", "--absolute-git-dir")
    (controller / ".git").write_text(f"gitdir: {third_gitdir}\n", encoding="utf-8")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_GITDIR_NOT_ITS_OWN"


def test_controller_moved_during_the_check_is_refused(pair, monkeypatch):
    """The HEAD a caller binds must be the HEAD that was validated."""
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    loaded, controller, head = pair
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", controller)
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", True)
    real = gateway_module.bound_controller_problem

    def check_then_move(controller_root, loaded_root):
        reason = real(controller_root, loaded_root)
        _commit(controller, "tasks/c/00-late.md", "late\n", "moved after the check")
        return reason

    monkeypatch.setattr(gateway_module, "bound_controller_problem", check_then_move)
    with pytest.raises(gateway_module.GatewayInputError, match="HEAD_MOVED_DURING_CHECK"):
        gateway_module._require_bound_controller(head)
