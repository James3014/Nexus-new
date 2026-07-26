import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
from nexus.orchestrator.task_contract import MutationMode, SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def controller_scenario(tmp_path):
    controller_root = tmp_path / "controller"
    target_worktree_root = tmp_path / "targets"
    controller_root.mkdir()
    target_worktree_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "sh2@example.test")
    _git(controller_root, "config", "user.name", "SH2 Test")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    _git(controller_root, "add", "bounded.txt")
    _git(controller_root, "commit", "-m", "target base")
    target_base_revision = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller revision")
    controller_revision = _git(controller_root, "rev-parse", "HEAD")
    return {
        "controller_root": controller_root,
        "target_worktree_root": target_worktree_root,
        "controller_revision": controller_revision,
        "target_base_revision": target_base_revision,
    }


def _contract(controller_scenario, *, task_id="controller-vertical"):
    target_root = controller_scenario["target_worktree_root"]
    return SelfHostedTaskContract(
        task_id=task_id,
        objective="Prepare and collect one bounded candidate",
        controller_revision=controller_scenario["controller_revision"],
        target_base_revision=controller_scenario["target_base_revision"],
        controller_repo_root=str(controller_scenario["controller_root"]),
        target_repo_root=str(target_root / task_id),
        target_worktree_root=str(target_root),
        allowed_files=["bounded.txt"],
        forbidden_files=[],
        verifier_commands=[],
        protected_contracts=[],
        preferred_provider=None,
        fallback_provider=None,
        maximum_provider_calls=0,
        maximum_replans=0,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )


def _controller(controller_scenario):
    manager = WorktreeManager(
        root_dir=str(controller_scenario["target_worktree_root"])
    )
    return SelfHostedDevelopmentController(worktree_manager=manager)


def test_self_hosted_controller_prepare_and_collect_vertical(controller_scenario):
    contract = _contract(controller_scenario)
    controller = _controller(controller_scenario)

    lease = controller.prepare_task(contract)
    target = Path(lease.target_worktree)
    (target / "bounded.txt").write_text("candidate\n", encoding="utf-8")
    receipt = controller.collect_candidate(contract, lease)

    assert receipt.task_id == contract.task_id
    assert receipt.contract_hash == contract.contract_hash
    assert receipt.changed_files == ["bounded.txt"]
    assert receipt.allowed_scope_passed is True
    assert receipt.controller_unchanged is True


def test_self_hosted_controller_rejects_contract_lease_mismatch(controller_scenario):
    first_contract = _contract(controller_scenario)
    controller = _controller(controller_scenario)
    lease = controller.prepare_task(first_contract)
    mismatched_contract = _contract(
        controller_scenario,
        task_id="different-contract",
    )

    with pytest.raises(RuntimeError, match="contract.*lease.*identity"):
        controller.collect_candidate(mismatched_contract, lease)


def test_self_hosted_controller_rejects_controller_revision_drift(controller_scenario):
    contract = _contract(controller_scenario)
    controller = _controller(controller_scenario)
    lease = controller.prepare_task(contract)
    _git(
        controller_scenario["controller_root"],
        "commit",
        "--allow-empty",
        "-m",
        "controller drift",
    )

    with pytest.raises(RuntimeError, match="Controller revision drift"):
        controller.collect_candidate(contract, lease)
