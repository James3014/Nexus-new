from dataclasses import asdict
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from nexus.orchestrator.candidate_commit import CandidateCommitter
from nexus.orchestrator.candidate_verifier import CandidateVerifier
from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
from nexus.orchestrator.task_contract import MutationMode, SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _scenario(tmp_path: Path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    target_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "commit@example.test")
    _git(controller_root, "config", "user.name", "Commit Test")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    _git(controller_root, "add", "bounded.txt")
    _git(controller_root, "commit", "-m", "base")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")
    contract = SelfHostedTaskContract(
        task_id="candidate-commit",
        objective="Create one isolated candidate commit",
        controller_revision=controller_sha,
        target_base_revision=target_sha,
        controller_repo_root=str(controller_root),
        target_repo_root=str(target_root / "candidate-commit"),
        target_worktree_root=str(target_root),
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
        protected_contracts=["candidate-receipt-v1"],
        preferred_provider="codex",
        maximum_provider_calls=1,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )
    manager = WorktreeManager(str(target_root))
    controller = SelfHostedDevelopmentController(manager)
    lease = controller.prepare_task(contract)
    empty_hooks = tmp_path / "default_scenario_hooks"
    empty_hooks.mkdir(exist_ok=True)
    _git(Path(lease.target_worktree), "config", "core.hooksPath", str(empty_hooks))
    Path(lease.target_worktree, "bounded.txt").write_text("candidate\n", encoding="utf-8")
    candidate = controller.collect_candidate(contract, lease)
    verified = CandidateVerifier(manager).verify(contract, lease, candidate)
    return contract, lease, verified, manager


def test_candidate_commit_is_automatic_but_promotion_pending(tmp_path):
    contract, lease, verified, manager = _scenario(tmp_path)

    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)

    assert packet.candidate_commit_created is True
    assert packet.promotion_status == "PENDING_HUMAN_APPROVAL"
    assert packet.public_claim_allowed is False
    assert packet.production_ready is False
    assert packet.merge_performed is False
    assert packet.push_performed is False
    assert len(packet.candidate_commit_sha) == 40
    assert len(packet.candidate_tree_sha) == 40
    assert packet.verified_receipt_hash
    assert _git(Path(lease.target_worktree), "status", "--short") == ""
    assert _git(Path(lease.target_worktree), "rev-parse", "HEAD") == packet.candidate_commit_sha
    changed = _git(Path(lease.target_worktree), "diff-tree", "--no-commit-id", "--name-only", "-r", packet.candidate_commit_sha)
    assert changed.splitlines() == ["bounded.txt"]


def test_candidate_commit_allows_only_explicit_authorized_deletion(tmp_path):
    contract, lease, _, manager = _scenario(tmp_path)
    authorized_contract = contract.model_copy(update={"authorized_deletions": ["bounded.txt"]})
    target = Path(lease.target_worktree)
    target.joinpath("bounded.txt").unlink()
    candidate = manager.capture_candidate(authorized_contract, lease)
    verified = CandidateVerifier(manager).verify(authorized_contract, lease, candidate)

    assert verified.verified is True
    packet = CandidateCommitter(manager).create_candidate_commit(
        authorized_contract, lease, verified
    )

    assert packet.candidate_commit_created is True
    assert _git(Path(lease.target_worktree), "status", "--short") == ""
    tree_paths = _git(
        Path(lease.target_worktree),
        "ls-tree",
        "-r",
        "--name-only",
        packet.candidate_commit_sha,
    )
    assert "bounded.txt" not in tree_paths.splitlines()


def test_precommitted_worker_candidate_is_reused_without_wrapper_commit(tmp_path):
    contract, lease, _, manager = _scenario(tmp_path)
    target = Path(lease.target_worktree)
    target.joinpath("bounded.txt").write_text("worker committed\n", encoding="utf-8")
    _git(target, "add", "bounded.txt")
    _git(target, "commit", "-m", "worker candidate")
    worker_head = _git(target, "rev-parse", "HEAD")

    candidate = manager.capture_candidate(contract, lease)
    verified = CandidateVerifier(manager).verify(contract, lease, candidate)
    assert verified.verified is True
    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)

    assert packet.candidate_commit_created is True
    assert packet.candidate_commit_sha == worker_head
    assert _git(target, "rev-list", "--count", f"{lease.initial_head}..HEAD") == "1"


def test_candidate_commit_rejects_unverified_receipt(tmp_path):
    contract, lease, verified, manager = _scenario(tmp_path)
    object.__setattr__(verified, "verified", False)

    with pytest.raises(RuntimeError, match="Verified Candidate Receipt"):
        CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)


def test_candidate_commit_requires_independent_commit_authority(tmp_path):
    contract, lease, verified, manager = _scenario(tmp_path)
    object.__setattr__(verified, "candidate_commit_allowed", False)
    object.__setattr__(verified, "public_claim_allowed", True)

    with pytest.raises(RuntimeError, match="Verified Candidate Receipt"):
        CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)


def test_candidate_commit_forces_muse_run_codex_loop_zero_via_subprocess_env_and_preserves_outer_env(tmp_path, monkeypatch):
    contract, lease, verified, manager = _scenario(tmp_path)
    hooks_dir = tmp_path / "custom_hooks_1"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text(
        "#!/bin/sh\nif [ \"$MUSE_RUN_CODEX_LOOP\" != \"0\" ]; then\n  echo \"HOOK FAIL: MUSE_RUN_CODEX_LOOP=$MUSE_RUN_CODEX_LOOP\" >&2\n  exit 1\nfi\n",
        encoding="utf-8",
    )
    pre_commit.chmod(0o755)
    _git(Path(lease.target_worktree), "config", "core.hooksPath", str(hooks_dir))

    monkeypatch.setenv("MUSE_RUN_CODEX_LOOP", "1")

    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)

    assert packet.candidate_commit_created is True
    assert os.environ.get("MUSE_RUN_CODEX_LOOP") == "1"


def test_candidate_commit_subprocess_env_preserves_absent_outer_variable(tmp_path, monkeypatch):
    contract, lease, verified, manager = _scenario(tmp_path)
    hooks_dir = tmp_path / "custom_hooks_2"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text(
        "#!/bin/sh\nif [ \"$MUSE_RUN_CODEX_LOOP\" != \"0\" ]; then\n  echo \"HOOK FAIL: MUSE_RUN_CODEX_LOOP=$MUSE_RUN_CODEX_LOOP\" >&2\n  exit 1\nfi\n",
        encoding="utf-8",
    )
    pre_commit.chmod(0o755)
    _git(Path(lease.target_worktree), "config", "core.hooksPath", str(hooks_dir))

    monkeypatch.delenv("MUSE_RUN_CODEX_LOOP", raising=False)

    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)

    assert packet.candidate_commit_created is True
    assert "MUSE_RUN_CODEX_LOOP" not in os.environ


def test_candidate_commit_does_not_mutate_global_env_concurrent_sentinel_thread(tmp_path, monkeypatch):
    contract, lease, verified, manager = _scenario(tmp_path)
    hooks_dir = tmp_path / "custom_hooks_sentinel"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text(
        "#!/bin/sh\nif [ \"$MUSE_RUN_CODEX_LOOP\" != \"0\" ]; then\n  echo \"HOOK FAIL: MUSE_RUN_CODEX_LOOP=$MUSE_RUN_CODEX_LOOP\" >&2\n  exit 1\nfi\nsleep 0.05\n",
        encoding="utf-8",
    )
    pre_commit.chmod(0o755)
    _git(Path(lease.target_worktree), "config", "core.hooksPath", str(hooks_dir))

    monkeypatch.setenv("MUSE_RUN_CODEX_LOOP", "1")

    observed_values = []
    stop_event = threading.Event()

    def sentinel():
        while not stop_event.is_set():
            observed_values.append(os.environ.get("MUSE_RUN_CODEX_LOOP"))
            time.sleep(0.0005)

    sentinel_thread = threading.Thread(target=sentinel, daemon=True)
    sentinel_thread.start()

    try:
        packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
    finally:
        stop_event.set()
        sentinel_thread.join(timeout=2.0)

    assert packet.candidate_commit_created is True
    assert os.environ.get("MUSE_RUN_CODEX_LOOP") == "1"
    assert len(observed_values) > 0
    assert all(val == "1" for val in observed_values)


def test_candidate_commit_uses_nexus_git_home_when_set(tmp_path, monkeypatch):
    contract, lease, verified, manager = _scenario(tmp_path)
    custom_git_home = tmp_path / "custom_git_home"
    custom_git_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NEXUS_GIT_HOME", str(custom_git_home))

    hooks_dir = tmp_path / "custom_hooks_git_home"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text(
        f'#!/bin/sh\nif [ "$HOME" != "{custom_git_home.resolve()}" ]; then\n  echo "HOOK FAIL: HOME=$HOME" >&2\n  exit 1\nfi\n',
        encoding="utf-8",
    )
    pre_commit.chmod(0o755)
    _git(Path(lease.target_worktree), "config", "core.hooksPath", str(hooks_dir))

    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)

    assert packet.candidate_commit_created is True
    assert os.environ.get("NEXUS_GIT_HOME") == str(custom_git_home)


def test_candidate_commit_uses_posix_os_account_home_independent_of_outer_home(tmp_path, monkeypatch):
    import pwd

    contract, lease, verified, manager = _scenario(tmp_path)
    monkeypatch.delenv("NEXUS_GIT_HOME", raising=False)
    fake_outer_home = tmp_path / "fake_agy_credential_home"
    fake_outer_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_outer_home))

    expected_os_home = str(Path(pwd.getpwuid(os.getuid()).pw_dir).resolve())

    hooks_dir = tmp_path / "custom_hooks_posix_home"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text(
        f'#!/bin/sh\nif [ "$HOME" != "{expected_os_home}" ]; then\n  echo "HOOK FAIL: HOME=$HOME expected {expected_os_home}" >&2\n  exit 1\nfi\n',
        encoding="utf-8",
    )
    pre_commit.chmod(0o755)
    _git(Path(lease.target_worktree), "config", "core.hooksPath", str(hooks_dir))

    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)

    assert packet.candidate_commit_created is True
    assert os.environ.get("HOME") == str(fake_outer_home)


def test_candidate_commit_fails_closed_on_invalid_explicit_nexus_git_home(tmp_path, monkeypatch):
    contract, lease, verified, manager = _scenario(tmp_path)
    invalid_path = tmp_path / "does_not_exist_git_home"
    monkeypatch.setenv("NEXUS_GIT_HOME", str(invalid_path))

    with pytest.raises(RuntimeError, match="Explicit NEXUS_GIT_HOME is invalid or does not exist"):
        CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)


def test_candidate_commit_preserves_outer_home_and_muse_env(tmp_path, monkeypatch):
    contract, lease, verified, manager = _scenario(tmp_path)
    fake_home = tmp_path / "fake_outer_home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("MUSE_RUN_CODEX_LOOP", "1")

    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)

    assert packet.candidate_commit_created is True
    assert os.environ.get("HOME") == str(fake_home)
    assert os.environ.get("MUSE_RUN_CODEX_LOOP") == "1"


def test_candidate_commit_fails_closed_when_git_home_unresolvable(tmp_path, monkeypatch):
    contract, lease, verified, manager = _scenario(tmp_path)
    monkeypatch.delenv("NEXUS_GIT_HOME", raising=False)
    def _fail_resolve():
        raise RuntimeError("Failed to resolve safe Git HOME: NEXUS_GIT_HOME is unset/empty and POSIX OS-account home resolution failed")
    monkeypatch.setattr(CandidateCommitter, "_resolve_git_home", staticmethod(_fail_resolve))

    with pytest.raises(RuntimeError, match="Failed to resolve safe Git HOME"):
        CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
