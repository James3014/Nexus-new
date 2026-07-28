import hashlib
import subprocess
from pathlib import Path

import pytest

from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
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
    verifier_evidence = receipt.verifier_evidence[0]

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
    assert verifier_evidence.argv == ("-c", 'print("verifier pass")')
    assert verifier_evidence.cwd == str(Path(lease.target_worktree).resolve())
    assert verifier_evidence.executable_identity
    assert verifier_evidence.executable_sha256 == hashlib.sha256(
        Path(verifier_evidence.executable_identity).read_bytes()
    ).hexdigest()
    assert verifier_evidence.process_group_id is not None
    assert verifier_evidence.process_group_killed is False
    assert verifier_evidence.timed_out is False


def test_candidate_verifier_fails_closed_for_nonzero_verifier_exit(scenario):
    contract, lease, candidate, controller = scenario
    failing_contract = contract.model_copy(
        update={"verifier_commands": ["python3 -c 'import sys; sys.exit(4)'"]}
    )

    receipt = CandidateVerifier(controller.worktree_manager).verify(failing_contract, lease, candidate)

    assert receipt.verified is False
    assert receipt.verifier_gate_passed is False
    assert receipt.public_claim_allowed is False
    assert receipt.candidate_commit_allowed is False
    assert receipt.verifier_evidence[0].exit_code == 4
    assert receipt.failure_reasons == ["verifier_failed:python3 -c 'import sys; sys.exit(4)'"]


def test_candidate_verifier_records_timeout_cleanup(scenario, monkeypatch):
    contract, lease, candidate, controller = scenario
    timeout_contract = contract.model_copy(
        update={"verifier_commands": ["python3 -c 'import time; time.sleep(30)'"]}
    )
    monkeypatch.setattr(CandidateVerifier, "VERIFIER_TIMEOUT_SECONDS", 0.05)

    receipt = CandidateVerifier(controller.worktree_manager).verify(timeout_contract, lease, candidate)
    verifier_evidence = receipt.verifier_evidence[0]

    assert receipt.verified is False
    assert receipt.verifier_gate_passed is False
    assert verifier_evidence.status == CliWorkerStatus.TIMED_OUT.value
    assert verifier_evidence.timed_out is True
    assert verifier_evidence.process_group_killed is True
    assert verifier_evidence.process_group_id is not None
    assert receipt.failure_reasons == ["verifier_failed:python3 -c 'import time; time.sleep(30)'"]


@pytest.mark.parametrize(
    ("tampered_field", "expected_reason"),
    [
        ("cwd", "cwd_mismatch"),
        ("executable_identity", "executable_identity_mismatch"),
        ("argv", "argv_mismatch"),
        ("executable_sha256", "executable_sha256_mismatch"),
    ],
)
def test_candidate_verifier_fails_closed_for_fake_evidence_mismatch(
    scenario,
    monkeypatch,
    tampered_field,
    expected_reason,
):
    contract, lease, candidate, controller = scenario

    def fake_worker(request):
        executable_identity = request.executable
        cwd = request.cwd
        argv = request.argv
        executable_sha256 = hashlib.sha256(Path(request.executable).read_bytes()).hexdigest()
        if tampered_field == "cwd":
            cwd = str(Path(request.cwd).parent)
        if tampered_field == "executable_identity":
            executable_identity = str(Path(request.executable).with_name("fake-python"))
        if tampered_field == "argv":
            argv = (*request.argv, "--tampered")
        if tampered_field == "executable_sha256":
            executable_sha256 = "0" * 64
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=executable_identity,
            executable_sha256=executable_sha256,
            argv=argv,
            cwd=cwd,
            exit_code=0,
            stdout=b"",
            stderr=b"",
            wall_time_ms=1,
            process_group_id=123,
        )

    monkeypatch.setattr("nexus.orchestrator.candidate_verifier.run_cli_worker", fake_worker)

    receipt = CandidateVerifier(controller.worktree_manager).verify(contract, lease, candidate)

    assert receipt.verified is False
    assert receipt.verifier_gate_passed is False
    assert receipt.public_claim_allowed is False
    assert expected_reason in receipt.failure_reasons[0]


def test_candidate_verifier_fails_closed_for_argv_mismatch(scenario, monkeypatch):
    contract, lease, candidate, controller = scenario

    def fake_worker(request):
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            executable_sha256=hashlib.sha256(Path(request.executable).read_bytes()).hexdigest(),
            argv=(*request.argv, "--tampered-argv"),
            cwd=request.cwd,
            exit_code=0,
            stdout=b"",
            stderr=b"",
            wall_time_ms=1,
            process_group_id=123,
        )

    monkeypatch.setattr("nexus.orchestrator.candidate_verifier.run_cli_worker", fake_worker)

    receipt = CandidateVerifier(controller.worktree_manager).verify(contract, lease, candidate)

    assert receipt.verified is False
    assert receipt.verifier_gate_passed is False
    assert receipt.public_claim_allowed is False
    assert "argv_mismatch" in receipt.failure_reasons[0]


def test_candidate_verifier_fails_closed_for_executable_sha256_mismatch(scenario, monkeypatch):
    contract, lease, candidate, controller = scenario

    def fake_worker(request):
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            executable_sha256="deadbeef" * 8,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b"",
            stderr=b"",
            wall_time_ms=1,
            process_group_id=123,
        )

    monkeypatch.setattr("nexus.orchestrator.candidate_verifier.run_cli_worker", fake_worker)

    receipt = CandidateVerifier(controller.worktree_manager).verify(contract, lease, candidate)

    assert receipt.verified is False
    assert receipt.verifier_gate_passed is False
    assert receipt.public_claim_allowed is False
    assert "executable_sha256_mismatch" in receipt.failure_reasons[0]


def test_candidate_verifier_fails_closed_when_timeout_does_not_kill_process_group(
    scenario,
    monkeypatch,
):
    contract, lease, candidate, controller = scenario

    def fake_worker(request):
        return CliWorkerResult(
            status=CliWorkerStatus.TIMED_OUT,
            executable_identity=request.executable,
            executable_sha256=hashlib.sha256(Path(request.executable).read_bytes()).hexdigest(),
            argv=request.argv,
            cwd=request.cwd,
            exit_code=-9,
            stdout=b"",
            stderr=b"",
            wall_time_ms=1,
            process_group_id=123,
            process_group_killed=False,
            timed_out=True,
        )

    monkeypatch.setattr("nexus.orchestrator.candidate_verifier.run_cli_worker", fake_worker)

    receipt = CandidateVerifier(controller.worktree_manager).verify(contract, lease, candidate)

    assert receipt.verified is False
    assert receipt.verifier_gate_passed is False
    assert "timeout_without_process_group_kill" in receipt.failure_reasons[0]
    assert receipt.failure_reasons[1] == "verifier_failed:python3 -c 'print(\"verifier pass\")'"


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
