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
            "AGENTS.md",
            ".github/workflows/new.yml",
            "docs/arch/module-inventory.generated.json",
        ],
        verifier_commands=[],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "bounded.txt").unlink()
    (target / "AGENTS.md").write_text("new authority\n", encoding="utf-8")
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
        "agent_instruction_authority_drift",
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
