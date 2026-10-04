from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from nexus.executors.worker_contract import WorkerExecutionReceipt, WorkerOutcome
from nexus.orchestrator import runtime_coordination_bridge as bridge
from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt, VerifierEvidence
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.research.clm_system_one.trajectory_continuity import (
    bind_trajectory_step_result,
    seal_trajectory_step,
    self_hosted_worker_trajectory_id,
)


class _Contract:
    def __init__(self, repo: Path, task_id: str, base_revision: str):
        self.task_id = task_id
        self.objective = "repair the bounded target"
        self.controller_repo_root = str(repo)
        self.target_repo_root = str(repo)
        self.target_base_revision = base_revision
        self.controller_revision = base_revision
        self.allowed_files = ["target.py"]
        self.verifier_commands = ["python -m pytest tests/test_target.py"]

    def model_dump(self, mode="json"):
        del mode
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "controller_repo_root": self.controller_repo_root,
            "target_repo_root": self.target_repo_root,
            "target_base_revision": self.target_base_revision,
            "controller_revision": self.controller_revision,
            "allowed_files": list(self.allowed_files),
            "verifier_commands": list(self.verifier_commands),
        }


def _init_repo(root: Path) -> str:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "target.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "target.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _worker_receipt(task_id: str, target: str) -> WorkerExecutionReceipt:
    return WorkerExecutionReceipt(
        provider="agy",
        task_id=task_id,
        target_worktree=target,
        worker_status="COMPLETED",
        outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
        exit_code=0,
        executable_identity="/usr/bin/true",
        argv=("true",),
        stdout_sha256="1" * 64,
        stderr_sha256="2" * 64,
        wall_time_ms=10,
        process_group_id=123,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
        failure_reason=None,
        provider_attempt_count=1,
    )


def test_natural_self_hosted_worker_emits_passive_trajectory(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    base = _init_repo(repo)
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False
    )
    service._write_state(
        "task-1",
        {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "status": "WORKER_RUNNING",
            "selected_model": "gemini-test",
            "request": {},
        },
    )
    monkeypatch.setattr(service, "_bridge_validate_claim", lambda *a, **kw: None)
    monkeypatch.setattr(service, "_ambient_core_required", lambda *a, **kw: False)
    monkeypatch.setattr(
        service.worker_registry,
        "invoke",
        lambda provider, contract, lease, **kwargs: _worker_receipt(
            contract.task_id, lease.target_worktree
        ),
    )

    contract = _Contract(repo, "task-1", base)
    lease = SimpleNamespace(target_worktree=str(repo))
    receipt = bridge._Worker(service).invoke(
        "agy", contract, lease, prompt="repair target", model="gemini-test"
    )

    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    state = service._read_state("task-1")
    assert "track1_worker_trajectories" not in state
    trajectory_id = self_hosted_worker_trajectory_id(
        task_id="task-1", attempt_id="attempt-1", provider="agy"
    )
    step_paths = list((evidence_root / "trajectory" / "steps").rglob("00000000.json"))
    assert len(step_paths) == 1
    step_path = step_paths[0]
    step = json.loads(step_path.read_text())
    assert step["trajectory_id"] == trajectory_id
    assert step["source_revision"] == base
    action = json.loads((evidence_root / step["action_ref"]).read_text())
    assert action["prompt_sha256"]
    assert "repair target" not in json.dumps(action)

    result_paths = list((evidence_root / "trajectory" / "step_results").rglob("00000000.json"))
    assert len(result_paths) == 1
    result = json.loads(result_paths[0].read_text())
    assert result["trajectory_id"] == trajectory_id


def test_verified_natural_candidate_binds_strong_outcome(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    base = _init_repo(repo)
    evidence_root = tmp_path / "evidence"
    state_root = tmp_path / "state-root"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(state_root))

    task_id = "task-2"
    attempt_id = "attempt-1"
    trajectory_id = self_hosted_worker_trajectory_id(
        task_id=task_id, attempt_id=attempt_id, provider="agy"
    )
    step = seal_trajectory_step(
        evidence_root=evidence_root,
        task_id=task_id,
        trajectory_id=trajectory_id,
        attempt_id=attempt_id,
        candidate_id=None,
        step_index=0,
        source_revision=base,
        base_source_revision=base,
        pre_action_state={"task_objective": "repair target"},
        action_type="self_hosted_worker_invoke",
        action_payload={"provider": "agy"},
    )
    bind_trajectory_step_result(
        evidence_root=evidence_root,
        step_ref=step,
        action_result={"outcome": "EXECUTION_COMPLETED"},
    )

    (repo / "target.py").write_text("VALUE = 2\n")
    candidate = SimpleNamespace(
        tracked_diff_sha256="3" * 64,
        untracked_content_hashes={},
        changed_files=["target.py"],
        untracked_files=[],
        deleted_files=[],
        candidate_state_hash="4" * 64,
    )
    verifier = VerifierEvidence(
        command="python -m pytest tests/test_target.py",
        status="COMPLETED",
        exit_code=0,
        stdout_sha256="5" * 64,
        stderr_sha256="6" * 64,
        wall_time_ms=1,
    )
    verified = VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt.v1",
        task_id=task_id,
        contract_hash="contract",
        lease_id="lease",
        candidate_state_hash="4" * 64,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=True,
        verified=True,
        candidate_commit_allowed=True,
        public_claim_allowed=False,
        production_ready=False,
        failure_reasons=[],
        verifier_evidence=(verifier,),
        candidate_commit_created=False,
        merge_performed=False,
    )

    import nexus.research.clm_system_one.trajectory_continuity as continuity

    monkeypatch.setattr(
        continuity,
        "refresh_registered_experiment",
        lambda **kwargs: {
            "readiness": {"disposition": "WAITING_FOR_DATA"},
            "checkpoint": {
                "status": "WAITING_FOR_DATA",
                "checkpoint_sha256": "7" * 64,
            },
        },
    )

    service = SelfHostedTaskService(
        state_dir=tmp_path / "service-state", ephemeral=True, auto_reconcile=False
    )
    state = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "selected_model": "gemini-test",
    }
    contract = _Contract(repo, task_id, base)
    lease = SimpleNamespace(target_worktree=str(repo))

    result = service._record_track1_verified_outcome(
        contract=contract,
        lease=lease,
        state=state,
        candidate=candidate,
        verified=verified,
        execution=_worker_receipt(task_id, str(repo)),
    )

    assert result["status"] == "COLLECTED"
    assert result["eligible_count"] == 1
    assert result["outcome_bound"] is True
    assert result["readiness"] == "WAITING_FOR_DATA"
    outcome_paths = list((evidence_root / "trajectory" / "outcomes").glob("*.json"))
    assert len(outcome_paths) == 1
    outcome = json.loads(outcome_paths[0].read_text())
    assert outcome["trajectory_id"] == trajectory_id
    assert outcome["verifier_status"] == "PASS"

    rows = [
        json.loads(path.read_text())
        for path in (evidence_root / "groups").rglob("*.json")
        if path.name != ".complete"
    ]
    assert len(rows) == 1
    assert rows[0]["collector_source"] == "self_hosted_worker"
    assert rows[0]["dataset_eligible"] is True
    payload = (evidence_root / rows[0]["candidate_payload_ref"]).read_text()
    payload_obj = json.loads(payload)
    assert "VALUE = 2" in payload_obj["tracked_diff"]
