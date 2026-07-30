from dataclasses import replace
import re
import subprocess
from pathlib import Path

from nexus.orchestrator.repository_contract_gate import RepositoryContractGate
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


def _init_repo(root: Path, *, with_policy_inputs: bool) -> tuple[str, str]:
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "repository-contract@example.test")
    _git(root, "config", "user.name", "Repository Contract")
    (root / "bounded.txt").write_text("base\n", encoding="utf-8")
    if with_policy_inputs:
        (root / "AGENTS.md").write_text("agent authority\n", encoding="utf-8")
        (root / "MUSE_PROTO.md").write_text("proto authority\n", encoding="utf-8")
        (root / ".github/workflows").mkdir(parents=True)
        (root / ".github/workflows/pytest.yml").write_text(
            "name: pytest\n",
            encoding="utf-8",
        )
        (root / "docs/arch").mkdir(parents=True)
        (root / "docs/arch/module-inventory.generated.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    target_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(root, "rev-parse", "HEAD")
    return target_sha, controller_sha


def _contract(
    controller_root: Path,
    target_root: Path,
    *,
    task_id: str,
    target_sha: str,
    controller_sha: str,
    allowed_files: list[str],
    verifier_commands: list[str],
) -> SelfHostedTaskContract:
    return SelfHostedTaskContract(
        task_id=task_id,
        objective="Verify repository contract gate",
        controller_revision=controller_sha,
        target_base_revision=target_sha,
        controller_repo_root=str(controller_root),
        target_repo_root=str(target_root / task_id),
        target_worktree_root=str(target_root),
        allowed_files=allowed_files,
        verifier_commands=verifier_commands,
        protected_contracts=["candidate-receipt-v1"],
        preferred_provider="codex",
        maximum_provider_calls=1,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )


def _prepare(contract: SelfHostedTaskContract, target_root: Path):
    controller = SelfHostedDevelopmentController(WorktreeManager(str(target_root)))
    lease = controller.prepare_task(contract)
    return controller, lease


def test_repository_contract_gate_records_shadow_findings_without_blocking(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="shadow-findings",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=[
            "bounded.txt",
            ".github/workflows/new.yml",
            "docs/arch/module-inventory.generated.json",
        ],
        verifier_commands=[],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "bounded.txt").unlink()
    (target / ".github/workflows").mkdir(parents=True)
    (target / ".github/workflows/new.yml").write_text("name: new\n", encoding="utf-8")
    (target / "docs/arch").mkdir(parents=True)
    (target / "docs/arch/module-inventory.generated.json").write_text(
        '{"new": true}\n',
        encoding="utf-8",
    )
    current = controller.collect_candidate(contract, lease)
    candidate = replace(current, contract_hash="0" * 64)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=candidate,
        current=current,
    )

    assert receipt.passed is True
    assert {finding.kind for finding in receipt.findings} >= {
        "ci_workflow_authority_drift",
        "declared_test_verifier_absent",
        "tracked_deletion",
        "candidate_lineage_mismatch",
        "generated_facts_authority_drift",
    }
    assert all(finding.severity == "shadow" for finding in receipt.findings)


def test_repository_contract_gate_policy_hash_is_deterministic(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=True)
    contract = _contract(
        controller_root,
        target_root,
        task_id="deterministic-hash",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    Path(lease.target_worktree, "bounded.txt").write_text("candidate\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)
    gate = RepositoryContractGate(controller.worktree_manager)

    first = gate.evaluate(contract, lease, current, current)
    second = gate.evaluate(contract, lease, current, current)

    assert first.policy_revision_hash == second.policy_revision_hash
    assert re.fullmatch(r"[0-9a-f]{64}", first.policy_revision_hash)
    assert first.findings == second.findings
    assert first.passed is True


def test_new_persistent_markdown_outside_tasks_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-md-frozen",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "docs/reports/new_report.md"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "docs/reports").mkdir(parents=True)
    (target / "docs/reports/new_report.md").write_text("# New Report\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_persistent_markdown_frozen:docs/reports/new_report.md" in receipt.blocking_reasons
    findings = [f for f in receipt.findings if f.kind == "new_persistent_markdown_frozen"]
    assert len(findings) == 1
    assert findings[0].severity == "blocking"
    assert findings[0].path == "docs/reports/new_report.md"


def test_new_policy_markdown_cannot_bypass_freeze(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-policy-md-frozen",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "AGENTS.md"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "AGENTS.md").write_text("# New AGENTS\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_persistent_markdown_frozen:AGENTS.md" in receipt.blocking_reasons


def test_new_markdown_under_tasks_allowed_if_in_allowed_files(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-md-tasks-allowed",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "tasks/my-campaign/00-task.md"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "tasks/my-campaign").mkdir(parents=True)
    (target / "tasks/my-campaign/00-task.md").write_text("# Task\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is True
    assert not [f for f in receipt.findings if f.kind == "new_persistent_markdown_frozen"]


def test_new_markdown_under_tasks_blocked_if_not_in_allowed_files(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-md-tasks-unallowed",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "tasks/my-campaign").mkdir(parents=True)
    (target / "tasks/my-campaign/00-unallowed.md").write_text("# Unallowed\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_persistent_markdown_frozen:tasks/my-campaign/00-unallowed.md" in receipt.blocking_reasons


def test_existing_non_policy_markdown_update_permitted(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "verifier@example.test")
    _git(controller_root, "config", "user.name", "Verifier")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    (controller_root / "docs").mkdir()
    (controller_root / "docs/README.md").write_text("# Base Readme\n", encoding="utf-8")
    _git(controller_root, "add", ".")
    _git(controller_root, "commit", "-m", "base with docs/README.md")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")

    contract = _contract(
        controller_root,
        target_root,
        task_id="update-existing-non-policy-md",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "docs/README.md"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "docs/README.md").write_text("# Updated Readme\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is True
    assert not [f for f in receipt.findings if f.kind == "new_persistent_markdown_frozen"]


def test_new_production_python_module_denoting_agent_router_wrapper_is_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-python-module-frozen",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "nexus/core/custom_agent.py"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "nexus/core").mkdir(parents=True)
    (target / "nexus/core/custom_agent.py").write_text("x = 1\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_component_module_frozen:nexus/core/custom_agent.py" in receipt.blocking_reasons


def test_new_ast_class_ending_agent_router_wrapper_is_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-ast-class-frozen",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "nexus/core/helper.py"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "nexus/core").mkdir(parents=True)
    (target / "nexus/core/helper.py").write_text(
        "class NewWrapper:\n    pass\n",
        encoding="utf-8",
    )
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_component_class_frozen:nexus/core/helper.py:NewWrapper" in receipt.blocking_reasons


def test_existing_ast_class_modification_permitted(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "verifier@example.test")
    _git(controller_root, "config", "user.name", "Verifier")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    (controller_root / "nexus/core").mkdir(parents=True)
    (controller_root / "nexus/core/router.py").write_text(
        "class CoreRouter:\n    def run(self):\n        pass\n",
        encoding="utf-8",
    )
    _git(controller_root, "add", ".")
    _git(controller_root, "commit", "-m", "base with router")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")

    contract = _contract(
        controller_root,
        target_root,
        task_id="modify-existing-ast-class",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "nexus/core/router.py"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "nexus/core/router.py").write_text(
        "class CoreRouter:\n    def run(self):\n        return True\n",
        encoding="utf-8",
    )
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is True
    assert not [f for f in receipt.findings if f.kind in ("new_component_class_frozen", "new_component_module_frozen")]
