"""A separate Controller worktree keeps Task Card binds out of the loaded deployment (#1939)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.orchestrator import canonical_source_root as roots
from scripts.ops.gateway_health_hmac import KEY_FILE_ENV, load_or_create_key, path_hmac
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
def _health_hmac_key(tmp_path, monkeypatch):
    monkeypatch.setenv(KEY_FILE_ENV, str(tmp_path / "health-hmac.key"))


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
    _git(controller, "checkout", "-q", "--detach")  # Controllers are detached
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
    assert "repo_root_sha256" not in public
    assert public["repo_root_hmac_sha256"] == path_hmac(
        "repo_root", str(loaded), load_or_create_key()
    )
    plain = hashlib.sha256(str(loaded).encode("utf-8")).hexdigest()
    assert public["repo_root_hmac_sha256"] != plain


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


def test_primary_worktree_controller_with_linked_loaded_checkout_is_accepted(pair, tmp_path):
    """Loaded = a linked worktree, Controller = the repository's primary worktree."""
    primary, _, head = pair
    linked_loaded = tmp_path / "linked-loaded"
    _git(primary, "worktree", "add", "-q", "--detach", str(linked_loaded), head)
    assert roots.bound_controller_problem(primary, linked_loaded) is None


def test_copied_gitdir_posing_as_a_primary_worktree_is_refused(pair, tmp_path):
    loaded, controller, _ = pair
    gitdir = Path(_git(controller, "rev-parse", "--absolute-git-dir"))
    (controller / ".git").unlink()
    subprocess.run(["cp", "-R", str(gitdir), str(controller / ".git")], check=True)
    assert roots.bound_controller_problem(controller, loaded) in {
        "CONTROLLER_GITDIR_NOT_ITS_OWN",
        "DIFFERENT_REPOSITORY",
        "COMMON_DIR_UNREADABLE",
    }


# ----------------------------------------------- #2230: prevention + safety net


def test_startup_degrades_instead_of_crashing_on_a_bad_own_controller(pair):
    loaded, controller, _ = pair
    _commit(controller, "nexus/evil.py", "x = 1\n", "direct commit")
    root, problem = roots.resolve_canonical_source_root_at_startup(
        {roots.CANONICAL_SOURCE_ROOT_ENV: str(controller)}, source_root=loaded
    )
    assert root == loaded.resolve()
    assert problem == "NEXUS_CANONICAL_SOURCE_ROOT_SOURCE_MISMATCH:CONTROLLER_CHANGES_OUTSIDE_TASKS"


def test_startup_degrades_when_the_controller_is_gone(pair, tmp_path):
    loaded, _, _ = pair
    root, problem = roots.resolve_canonical_source_root_at_startup(
        {roots.CANONICAL_SOURCE_ROOT_ENV: str(tmp_path / "pruned")}, source_root=loaded
    )
    assert root == loaded.resolve()
    assert problem == "NEXUS_CANONICAL_SOURCE_ROOT_MISSING"


def test_startup_still_refuses_a_root_from_another_repository(pair, tmp_path):
    loaded, _, _ = pair
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    # CI runners have no global git identity.
    _git(other, "config", "user.name", "Nexus Test")
    _git(other, "config", "user.email", "nexus-test@example.invalid")
    _commit(other, "README.md", "x\n", "other")
    with pytest.raises(RuntimeError, match="DIFFERENT_REPOSITORY"):
        roots.resolve_canonical_source_root_at_startup(
            {roots.CANONICAL_SOURCE_ROOT_ENV: str(other)}, source_root=loaded
        )


def test_real_gateway_import_starts_degraded_not_crash_looping(tmp_path):
    """A pruned Controller no longer crash-loops the real Gateway module import."""
    repo = Path(__file__).resolve().parents[3]
    code = (
        "from nexus.orchestrator import unified_mcp_gateway as g;"
        "from nexus.orchestrator import canonical_source_root as r;"
        "print(r.controller_binding_status()['status'], g.CONTROLLER_BINDING_PROBLEM)"
    )
    env = {
        **os.environ,
        roots.CANONICAL_SOURCE_ROOT_ENV: str(tmp_path / "controllers" / "a1-pruned"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.split() == ["DEGRADED", "NEXUS_CANONICAL_SOURCE_ROOT_MISSING"]


def test_degraded_gateway_refuses_task_card_create_without_writing_and_reports_degraded_identity(
    pair, monkeypatch
):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module
    import scripts.ops.nexus_mcp_gateway_http as http_module

    loaded, _, _ = pair
    _allow_owner_effect_authority(monkeypatch)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", False)
    monkeypatch.setattr(
        gateway_module, "CONTROLLER_BINDING_PROBLEM", "NEXUS_CANONICAL_SOURCE_ROOT_MISSING"
    )
    monkeypatch.setattr(roots, "CONTROLLER_BINDING_PROBLEM", "NEXUS_CANONICAL_SOURCE_ROOT_MISSING")
    gateway = gateway_module.UnifiedMCPGateway(service=FakeService())
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "nexus_task_card_create",
            "arguments": {
                **AUTHORITY_ARGS,
                "owner_confirmation": True,
                "campaign_id": "deg",
                "task_id": "card",
                "objective": "x",
                "allowed_files": ["README.md"],
                "verifier_commands": ["git diff --check"],
            },
        },
    })
    assert response["result"]["isError"] is True
    assert "CONTROLLER_BINDING_INVALID:DEGRADED" in response["result"]["structuredContent"]["error"]
    assert not (loaded / "tasks" / "deg").exists()
    monkeypatch.setattr(http_module, "LOADED_SOURCE_ROOT", loaded)
    identity = http_module.runtime_identity()
    assert identity["status"] == "degraded"
    assert identity["controller_binding"] == {
        "status": "DEGRADED",
        "reason": "NEXUS_CANONICAL_SOURCE_ROOT_MISSING",
    }


def _degraded_gateway(pair, monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    loaded, _, _ = pair
    _allow_owner_effect_authority(monkeypatch)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", False)
    monkeypatch.setattr(
        gateway_module, "CONTROLLER_BINDING_PROBLEM", "NEXUS_CANONICAL_SOURCE_ROOT_MISSING"
    )
    monkeypatch.setattr(roots, "CONTROLLER_BINDING_PROBLEM", "NEXUS_CANONICAL_SOURCE_ROOT_MISSING")
    return gateway_module.UnifiedMCPGateway(service=FakeService())


def _call(gateway, name: str, arguments: dict) -> dict:
    return gateway.handle({
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })["result"]


@pytest.mark.parametrize(
    "tool",
    [
        "nexus_task_retry",
        "nexus_task_resume",
        "nexus_candidate_approve",
        "nexus_candidate_adopt_external",
        "nexus_candidate_bind_integration",
        "nexus_candidate_integrate",
        "nexus_task_run",
        "nexus_learning_policy_adopt",
        "nexus_learning_policy_rollback",
    ],
)
def test_degraded_gateway_refuses_governed_mutation_before_validation(pair, monkeypatch, tool):
    gateway = _degraded_gateway(pair, monkeypatch)
    # Empty arguments: the degraded refusal must come before argument validation.
    result = _call(gateway, tool, {})
    assert result["isError"] is True
    assert "CONTROLLER_BINDING_INVALID:DEGRADED" in result["structuredContent"]["error"]


_OWNER_CONFIRMED_EFFECT_ARGS = {
    "nexus_worker_candidate": {
        "owner_confirmation": True,
        "what": "x",
        "why": "y",
        "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"],
        "task_card_path": "tasks/deg/card.md",
        "task_card_hash": "a" * 64,
    },
    "nexus_task_card_create": {
        **AUTHORITY_ARGS,
        "owner_confirmation": True,
        "campaign_id": "deg",
        "task_id": "card",
        "objective": "x",
        "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"],
    },
    "nexus_task_card_commit": {
        **AUTHORITY_ARGS,
        "owner_confirmation": True,
        "campaign_id": "deg",
        "task_id": "card",
        "expected_head": "a" * 40,
        "card_hash": "b" * 64,
        "index_hash": "c" * 64,
    },
}


@pytest.mark.parametrize("tool", sorted(_OWNER_CONFIRMED_EFFECT_ARGS))
def test_degraded_gateway_refuses_owner_confirmed_effects(pair, monkeypatch, tool):
    gateway = _degraded_gateway(pair, monkeypatch)
    result = _call(gateway, tool, dict(_OWNER_CONFIRMED_EFFECT_ARGS[tool]))
    assert result["isError"] is True
    assert "CONTROLLER_BINDING_INVALID:DEGRADED" in result["structuredContent"]["error"]
    assert not (pair[0] / "tasks" / "deg").exists()


class _SpyService(FakeService):
    def __init__(self):
        super().__init__()
        self.calls: list[tuple[str, str]] = []

    def cancel_task(self, task_id):
        self.calls.append(("cancel_task", task_id))
        return super().cancel_task(task_id)

    def reconcile_task(self, task_id):
        self.calls.append(("reconcile_task", task_id))
        return super().reconcile_task(task_id)

    def dispose_candidate(self, task_id, **kwargs):
        self.calls.append(("dispose_candidate", task_id))
        return super().dispose_candidate(task_id, **kwargs)


@pytest.mark.parametrize(
    ("tool", "arguments", "service_call"),
    [
        ("nexus_task_cancel", {"task_id": "t-1"}, "cancel_task"),
        (
            "nexus_candidate_dispose",
            {"task_id": "t-1", "disposition": "REJECTED", **AUTHORITY_ARGS},
            "dispose_candidate",
        ),
        ("nexus_task_reconcile", {"task_id": "t-1"}, "reconcile_task"),
    ],
)
def test_degraded_gateway_cleanup_tools_reach_their_service_call(
    pair, monkeypatch, tool, arguments, service_call
):
    gateway = _degraded_gateway(pair, monkeypatch)
    spy = _SpyService()
    gateway.service = spy
    result = _call(gateway, tool, arguments)
    assert result["isError"] is False, result
    assert spy.calls == [(service_call, "t-1")]
    assert "CONTROLLER_BINDING_INVALID" not in str(result)


def test_direct_canonical_finish_is_refused_with_a_separate_controller(pair, monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    loaded, controller, head = pair
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", controller)
    monkeypatch.setattr(gateway_module, "LOADED_SOURCE_ROOT", loaded)
    monkeypatch.setattr(gateway_module, "CONTROLLER_IS_SEPARATE", True)
    gateway = gateway_module.UnifiedMCPGateway(service=FakeService())
    with pytest.raises(gateway_module.GatewayInputError, match="DIRECT_CANONICAL_FORBIDDEN"):
        gateway._finish({"execution_lane": "DIRECT_CANONICAL", "task_id": "t", "base_sha": head})
    assert _git(controller, "rev-parse", "HEAD") == head


def test_direct_lane_is_never_chosen_with_a_separate_controller(monkeypatch):
    from nexus.orchestrator import self_hosted_task_service as service

    monkeypatch.setattr(roots, "CONTROLLER_IS_SEPARATE", True)
    lane = service.resolve_execution_lane({
        "execution_lane": "DIRECT_CANONICAL",
        "primary_agent": True,
    })
    assert lane["execution_lane"] == "ISOLATED_TARGET"
    assert "separate_controller_direct_forbidden" in lane["blockers"]


def test_startup_degrades_when_our_controller_metadata_is_broken(pair):
    loaded, controller, _ = pair
    (controller / ".git").unlink()  # half-deleted Controller: no gitfile
    root, problem = roots.resolve_canonical_source_root_at_startup(
        {roots.CANONICAL_SOURCE_ROOT_ENV: str(controller)}, source_root=loaded
    )
    assert root == loaded.resolve()
    assert problem is not None and problem.startswith("NEXUS_CANONICAL_SOURCE_ROOT_")


def test_startup_degrades_when_a_git_check_times_out(pair, monkeypatch):
    loaded, controller, _ = pair
    real = subprocess.run

    def slow(argv, *args, **kwargs):
        if list(argv[:2]) == ["git", "merge-base"] or "status" in argv:
            raise subprocess.TimeoutExpired(argv, 5)
        return real(argv, *args, **kwargs)

    _commit(controller, "tasks/c/00-t.md", "card\n", "bind")
    monkeypatch.setattr(roots.subprocess, "run", slow)
    root, problem = roots.resolve_canonical_source_root_at_startup(
        {roots.CANONICAL_SOURCE_ROOT_ENV: str(controller)}, source_root=loaded
    )
    assert root == loaded.resolve()
    assert problem == "CONTROLLER_CHECK_FAILED:TimeoutExpired"


def test_controller_with_a_branch_checked_out_is_refused(pair):
    loaded, controller, _ = pair
    _git(controller, "checkout", "-q", "-b", "nexus/integration/main")
    assert roots.bound_controller_problem(controller, loaded) == "CONTROLLER_NOT_DETACHED"


def test_symbolic_ref_timeout_is_a_binding_reason_not_an_exception(pair, monkeypatch):
    loaded, controller, _ = pair
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "symbolic-ref"]:
            raise subprocess.TimeoutExpired(cmd, 5)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(roots.subprocess, "run", run)
    assert roots.bound_controller_problem(controller, loaded) == "HEAD_UNREADABLE"
