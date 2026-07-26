import hashlib
import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.candidate_verifier import CandidateVerifier
from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
from nexus.orchestrator.task_contract import MutationMode, SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def scenario(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    target_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "verifier@example.test")
    _git(controller_root, "config", "user.name", "Verifier")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    _git(controller_root, "add", "bounded.txt")
    _git(controller_root, "commit", "-m", "base")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")
    contract = SelfHostedTaskContract(
        task_id="candidate-verifier",
        objective="Verify one candidate",
        controller_revision=controller_sha,
        target_base_revision=target_sha,
        controller_repo_root=str(controller_root),
        target_repo_root=str(target_root / "candidate-verifier"),
        target_worktree_root=str(target_root),
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"verifier pass\")'"],
        protected_contracts=["candidate-receipt-v1"],
        preferred_provider="codex",
        maximum_provider_calls=1,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )
    controller = SelfHostedDevelopmentController(WorktreeManager(str(target_root)))
    lease = controller.prepare_task(contract)
    Path(lease.target_worktree, "bounded.txt").write_text("candidate\n", encoding="utf-8")
    candidate = controller.collect_candidate(contract, lease)
    return contract, lease, candidate, controller


def test_candidate_verifier_produces_verified_receipt(scenario):
    contract, lease, candidate, controller = scenario

    receipt = CandidateVerifier(controller.worktree_manager).verify(contract, lease, candidate)

    assert receipt.verified is True
    assert receipt.scope_gate_passed is True
    assert receipt.deletion_gate_passed is True
    assert receipt.controller_gate_passed is True
    assert receipt.protected_contract_gate_passed is True
    assert receipt.verifier_gate_passed is True
    assert receipt.candidate_state_hash == candidate.candidate_state_hash
    assert receipt.candidate_commit_created is False
    assert receipt.candidate_commit_allowed is True
    assert receipt.public_claim_allowed is False
    assert receipt.production_ready is False


def test_candidate_verifier_fails_closed_for_deleted_file(scenario):
    contract, lease, candidate, controller = scenario
    target = Path(lease.target_worktree)
    (target / "bounded.txt").unlink()
    deleted_candidate = controller.collect_candidate(contract, lease)

    receipt = CandidateVerifier(controller.worktree_manager).verify(contract, lease, deleted_candidate)

    assert receipt.verified is False
    assert receipt.deletion_gate_passed is False
    assert receipt.public_claim_allowed is False


def test_candidate_verifier_protects_explicit_contract_paths(scenario):
    contract, lease, candidate, controller = scenario
    protected_hash = hashlib.sha256(Path(lease.target_worktree, "bounded.txt").read_bytes()).hexdigest()

    receipt = CandidateVerifier(controller.worktree_manager).verify(
        contract,
        lease,
        candidate,
        protected_paths={"bounded.txt": protected_hash},
    )

    assert receipt.verified is False
    assert receipt.protected_contract_gate_passed is False
    assert receipt.failure_reasons == ["protected_contract_changed:bounded.txt"]
