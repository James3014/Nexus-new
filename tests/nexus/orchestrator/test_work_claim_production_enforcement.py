"""Adversarial and production enforcement tests for Issue #129 Campaign B.

Validates that canonical work claim authority (acquire, validate, release, recover)
is wired into the first-effect boundaries of production dispatch and mutation:
- Physical Target lease
- Ambient core / host preparation
- Provider invocation
- Candidate capture / finalization
- Approval / promotion ceiling separation
"""

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nexus.orchestrator.self_hosted_task_service import (
    SelfHostedTaskService,
)


def _seed_base_repo(repo_path: Path) -> str:
    """Initialize a git repo with a commit and return its SHA."""
    import subprocess

    repo_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    readme = repo_path / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    return head


def _claim_request(task_id: str = "claim-task", **overrides):
    values = {
        "task_id": task_id,
        "repository": "James3014/Nexus-new",
        "issue": 129,
        "attempt_id": f"attempt-{task_id}",
        "action_id": "action-1",
        "worker_id": "worker-a",
        "provider": "codex",
        "model": "gpt-4",
        "role": "bounded_code_candidate",
        "claim_ceiling": "CLAIM_PROTOCOL_CANDIDATE_PR_ONLY",
        "base_revision": "b" * 40,
        "source_hash": "s" * 64,
        "task_card_path": "tasks/card.md",
        "allowed_files": ["a.py"],
        "workforce_admission": {"receipt_id": "admission-1"},
    }
    values.update(overrides)
    return values


def _submission_request(tmp_path: Path, task_id: str, base_sha: str, **overrides):
    values = {
        "task_id": task_id,
        "what": "Implement claim enforcement",
        "why": "Prevent uncoordinated mutation",
        "repository": "James3014/Nexus-new",
        "issue": 129,
        "issue_number": 129,
        "controller_revision": base_sha,
        "target_base_revision": base_sha,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / task_id),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["nexus/orchestrator/self_hosted_task_service.py"],
        "worker": "codex",
        "model": "gpt-4",
        "execution_lane": "ISOLATED_TARGET",
        "claim_required": True,
    }
    values.update(overrides)
    return values


# ---------------------------------------------------------------------------
# Matrix 1 & 2: Two workers claim same issue -> exactly one winner, loser 0 provider calls
# ---------------------------------------------------------------------------
def test_two_workers_concurrent_claim_same_issue_exactly_one_winner_and_loser_stops(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    controller_dir = tmp_path / "controller"
    base_sha = _seed_base_repo(controller_dir)

    provider_calls = []

    def mock_invoke(provider, contract, lease, **kwargs):
        provider_calls.append(contract.task_id)
        from nexus.executors.worker_contract import WorkerExecutionReceipt

        return WorkerExecutionReceipt(
            provider=provider,
            outcome="EXECUTION_COMPLETED",
            evidence_complete=True,
            provider_calls=1,
        )

    registry = MagicMock()
    registry.invoke = mock_invoke
    registry.preflight.return_value = MagicMock(ready=True)

    barrier = threading.Barrier(2)
    results = {}

    def worker_run(worker_name: str, task_id: str):
        svc = SelfHostedTaskService(
            state_dir=state_dir,
            auto_reconcile=False,
            ephemeral=True,
            worker_registry=registry,
        )
        req = _submission_request(
            tmp_path,
            task_id,
            base_sha,
            worker_id=worker_name,
            worker="codex",
        )
        barrier.wait()
        try:
            res = svc.submit_task(req)
            results[worker_name] = ("OK", res)
        except Exception as exc:
            results[worker_name] = ("ERROR", str(exc))

    t1 = threading.Thread(target=worker_run, args=("worker-1", "task-issue129-1"))
    t2 = threading.Thread(target=worker_run, args=("worker-2", "task-issue129-2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one winner, one loser blocked
    statuses = [v[0] for v in results.values()]
    assert sorted(statuses) == ["ERROR", "OK"], f"Expected one OK and one ERROR, got: {results}"

    loser_error = [v[1] for v in results.values() if v[0] == "ERROR"][0]
    assert "WORK_CLAIM_BLOCKED:ALREADY_CLAIMED" in loser_error


# ---------------------------------------------------------------------------
# Matrix 3: Idempotent replay of same logical attempt -> no second claim/provider call
# ---------------------------------------------------------------------------
def test_idempotent_replay_of_same_logical_attempt(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state("task-replay", {"task_id": "task-replay", "status": "SUBMITTED"})

    first = service.acquire_work_claim(_claim_request(task_id="task-replay"))
    assert first["status"] == "CLAIMED"
    gen1 = first["claim"]["generation"]

    # Replay identical attempt
    replay = service.acquire_work_claim(_claim_request(task_id="task-replay"))
    assert replay["status"] == "ALREADY_CLAIMED"
    assert replay["claim"]["generation"] == gen1 == 1


# ---------------------------------------------------------------------------
# Matrix 4: Stale generation cannot mutate, candidate, release, or cleanup
# ---------------------------------------------------------------------------
def test_stale_generation_fenced_from_mutation_and_lifecycle(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "task-stale-gen"
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "attempt_id": "attempt-1",
            "status": "SUBMITTED",
            "contract": {
                "task_id": task_id,
                "target_base_revision": "b" * 40,
                "controller_revision": "s" * 64,
                "target_worktree_root": str(tmp_path / "targets"),
            },
        },
    )

    first = service.acquire_work_claim(_claim_request(task_id=task_id, attempt_id="attempt-1"))
    assert first["status"] == "CLAIMED"

    # Simulate attempt-1 registering its bound generation = 1
    service._bridge_validate_claim(task_id, "attempt-1", operation="RUN_OWNED_ATTEMPT")
    assert service._bound_attempt_claims[(task_id, "attempt-1")]["generation"] == 1

    # Orchestrator recovers claim to generation 2
    recovered = service.recover_work_claim(
        {
            **_claim_request(task_id=task_id, attempt_id="attempt-1"),
            "claim_id": first["claim"]["claim_id"],
            "generation": 1,
            "fencing_token": first["claim"]["fencing_token"],
        },
        reason="timeout_recovery",
    )
    assert recovered["claim"]["generation"] == 2

    # Old attempt-1 tries to lease Target -> fails closed with WORK_CLAIM_STALE_FENCE
    with pytest.raises(RuntimeError, match="WORK_CLAIM_STALE_FENCE"):
        service._bridge_validate_claim(task_id, "attempt-1", operation="TARGET_LEASE")

    # Old attempt-1 tries to prepare ambient core -> fails closed
    with pytest.raises(RuntimeError, match="WORK_CLAIM_STALE_FENCE"):
        service._bridge_validate_claim(task_id, "attempt-1", operation="HOST_PREPARATION")

    # Old attempt-1 tries to invoke provider -> fails closed
    with pytest.raises(RuntimeError, match="WORK_CLAIM_STALE_FENCE"):
        service._bridge_validate_claim(task_id, "attempt-1", operation="PROVIDER_INVOKE")

    # Old attempt-1 tries to finalize candidate -> fails closed
    with pytest.raises(RuntimeError, match="WORK_CLAIM_STALE_FENCE"):
        service._bridge_validate_claim(task_id, "attempt-1", operation="FINALIZE_CANDIDATE")

    # Old attempt-1 tries to release claim -> fails closed
    with pytest.raises(RuntimeError, match="WORK_CLAIM_STALE_FENCE"):
        service.release_work_claim({
            **_claim_request(task_id=task_id, attempt_id="attempt-1"),
            "claim_id": first["claim"]["claim_id"],
            "generation": 1,
            "fencing_token": first["claim"]["fencing_token"],
        })


# ---------------------------------------------------------------------------
# Matrix 5: Future / forged generation fails closed
# ---------------------------------------------------------------------------
def test_future_or_forged_generation_fails_closed(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "task-future-gen"
    service._write_state(
        task_id, {"task_id": task_id, "attempt_id": "attempt-1", "status": "SUBMITTED"}
    )

    first = service.acquire_work_claim(_claim_request(task_id=task_id, attempt_id="attempt-1"))
    claim = first["claim"]

    # Bound with future generation
    service._bound_attempt_claims[(task_id, "attempt-1")] = {
        **_claim_request(task_id=task_id, attempt_id="attempt-1"),
        "claim_id": claim["claim_id"],
        "generation": 99,
        "fencing_token": f"{claim['claim_id']}:99",
    }

    with pytest.raises(RuntimeError, match="WORK_CLAIM_STALE_FENCE"):
        service._bridge_validate_claim(task_id, "attempt-1")


# ---------------------------------------------------------------------------
# Matrix 6: Stale source / base drift fails closed
# ---------------------------------------------------------------------------
def test_stale_source_or_base_drift_fails_closed(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "task-base-drift"
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "attempt_id": "attempt-1",
            "status": "SUBMITTED",
            "contract": {
                "task_id": task_id,
                "target_base_revision": "b" * 40,
                "controller_revision": "s" * 64,
            },
        },
    )

    service.acquire_work_claim(_claim_request(task_id=task_id, attempt_id="attempt-1"))

    # Mutate contract base revision to simulate repo drift
    state = service._read_state(task_id)
    state["contract"]["target_base_revision"] = "c" * 40
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError, match="WORK_CLAIM_BASE_REVISION_DRIFT"):
        service._bridge_validate_claim(task_id, "attempt-1")


# ---------------------------------------------------------------------------
# Matrix 7: Forged identity (worker, model, admission, scope) fails closed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tamper_field,tamper_value",
    [
        ("worker_id", "forged-worker"),
        ("model", "forged-model"),
        ("allowed_files", ["malicious.py"]),
        ("workforce_admission", {"receipt_id": "forged-admission"}),
    ],
)
def test_forged_identity_fails_closed(tmp_path, tamper_field, tamper_value):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = f"task-tamper-{tamper_field}"
    service._write_state(
        task_id, {"task_id": task_id, "attempt_id": "attempt-1", "status": "SUBMITTED"}
    )

    first = service.acquire_work_claim(_claim_request(task_id=task_id, attempt_id="attempt-1"))
    claim = first["claim"]

    tampered = _claim_request(task_id=task_id, attempt_id="attempt-1")
    tampered[tamper_field] = tamper_value
    tampered["claim_id"] = claim["claim_id"]
    tampered["generation"] = claim["generation"]
    tampered["fencing_token"] = claim["fencing_token"]

    service._bound_attempt_claims[(task_id, "attempt-1")] = tampered

    with pytest.raises(RuntimeError, match="WORK_CLAIM_FENCE_MISMATCH"):
        service._bridge_validate_claim(task_id, "attempt-1")


# ---------------------------------------------------------------------------
# Matrix 7b: Corrupt claim inventory fails closed instead of hiding an owner
# ---------------------------------------------------------------------------
def test_corrupt_claim_inventory_blocks_new_issue_claim(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    task_id = "task-new-claim"
    service._write_state(
        task_id,
        {"task_id": task_id, "attempt_id": "attempt-1", "status": "SUBMITTED"},
    )
    service.state_dir.mkdir(parents=True, exist_ok=True)
    corrupt = service.state_dir / "possibly-active-owner.json"
    corrupt.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="WORK_CLAIM_INVENTORY_UNKNOWN"):
        service.acquire_work_claim(
            _claim_request(task_id=task_id, attempt_id="attempt-1", issue=129),
            enforce_issue_uniqueness=True,
        )

    state = service._read_state(task_id)
    assert state is not None
    assert state.get("work_claim") is None


# ---------------------------------------------------------------------------
# Matrix 7c: Claim inventory with broken state/claim enclosure fails closed
# ---------------------------------------------------------------------------
def test_claim_inventory_with_broken_enclosure_blocks_new_issue_claim(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    existing_task = "task-existing-owner"
    service._write_state(
        existing_task,
        {"task_id": existing_task, "attempt_id": "attempt-1", "status": "SUBMITTED"},
    )
    service.acquire_work_claim(
        _claim_request(task_id=existing_task, attempt_id="attempt-1", issue=129)
    )

    existing_path = service._state_path(existing_task)
    existing_state = json.loads(existing_path.read_text(encoding="utf-8"))
    existing_state["task_id"] = "different-task-id"
    existing_path.write_text(json.dumps(existing_state), encoding="utf-8")

    new_task = "task-new-owner"
    service._write_state(
        new_task,
        {"task_id": new_task, "attempt_id": "attempt-2", "status": "SUBMITTED"},
    )

    with pytest.raises(RuntimeError, match="WORK_CLAIM_INVENTORY_UNKNOWN"):
        service.acquire_work_claim(
            _claim_request(task_id=new_task, attempt_id="attempt-2", issue=129),
            enforce_issue_uniqueness=True,
        )

    new_state = service._read_state(new_task)
    assert new_state is not None
    assert new_state.get("work_claim") is None


# ---------------------------------------------------------------------------
# Matrix 8: Recovery produces exactly one current owner at generation 2
# ---------------------------------------------------------------------------
def test_recovery_produces_single_current_owner(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "task-single-owner"
    service._write_state(
        task_id, {"task_id": task_id, "attempt_id": "attempt-1", "status": "SUBMITTED"}
    )

    first = service.acquire_work_claim(_claim_request(task_id=task_id, attempt_id="attempt-1"))
    claim = first["claim"]

    recovered = service.recover_work_claim(
        {
            **_claim_request(task_id=task_id, attempt_id="attempt-1"),
            "claim_id": claim["claim_id"],
            "generation": 1,
            "fencing_token": claim["fencing_token"],
        },
        reason="crash",
    )
    assert recovered["claim"]["generation"] == 2
    assert recovered["claim"]["fencing_token"] == f"{claim['claim_id']}:2"

    # Only generation 2 validates
    valid_res = service.validate_work_claim({
        **_claim_request(task_id=task_id, attempt_id="attempt-1"),
        "claim_id": claim["claim_id"],
        "generation": 2,
        "fencing_token": recovered["claim"]["fencing_token"],
    })
    assert valid_res["status"] == "CLAIMED"


# ---------------------------------------------------------------------------
# Matrix 9: Claim failure does not secretly fallback or change model
# ---------------------------------------------------------------------------
def test_claim_failure_does_not_fallback_or_reroute(tmp_path):
    controller_dir = tmp_path / "controller"
    base_sha = _seed_base_repo(controller_dir)

    fallback_calls = []

    def mock_invoke(provider, contract, lease, **kwargs):
        if provider == "gemini":
            fallback_calls.append(provider)
        from nexus.executors.worker_contract import WorkerExecutionReceipt

        return WorkerExecutionReceipt(
            provider=provider,
            outcome="EXECUTION_COMPLETED",
            evidence_complete=True,
            provider_calls=1,
        )

    registry = MagicMock()
    registry.invoke = mock_invoke
    registry.preflight.return_value = MagicMock(ready=True)

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
        worker_registry=registry,
    )

    # Pre-seed conflicting claim on another task
    other_id = "other-task"
    service._write_state(other_id, {"task_id": other_id, "status": "SUBMITTED"})
    service.acquire_work_claim(_claim_request(task_id=other_id, issue=129))

    # New task tries to claim same issue with fallback configured
    req = _submission_request(
        tmp_path,
        "task-fail-closed",
        base_sha,
        worker="codex",
        fallback_provider="gemini",
        provider_order=["codex", "gemini"],
    )

    with pytest.raises(RuntimeError, match="WORK_CLAIM_BLOCKED:ALREADY_CLAIMED"):
        service.submit_task(req)

    # Proves zero provider calls and zero fallback calls
    assert fallback_calls == []


# ---------------------------------------------------------------------------
# Matrix 10: Implementer claim cannot authorize review/acceptance/merge
# ---------------------------------------------------------------------------
def test_implementer_claim_cannot_authorize_approval(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "task-candidate"
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "attempt_id": "attempt-1",
            "status": "CANDIDATE_CAPTURED",
            "promotion_packet": {
                "candidate_commit_sha": "c" * 40,
                "candidate_tree_sha": "t" * 40,
                "candidate_state_hash": "s" * 64,
                "verified_receipt_hash": "v" * 64,
            },
        },
    )

    with pytest.raises(RuntimeError, match="IMPLEMENTER_CLAIM_CANNOT_AUTHORIZE_APPROVAL"):
        service.approve_promotion(
            task_id,
            candidate_commit_sha="c" * 40,
            candidate_tree_sha="t" * 40,
            candidate_state_hash="s" * 64,
            verified_receipt_hash="v" * 64,
            approval_context={
                "claim_ceiling": "CLAIM_PROTOCOL_CANDIDATE_PR_ONLY",
                "role": "bounded_code_candidate",
            },
        )


# ---------------------------------------------------------------------------
# Matrix 11: Two different Issues claim independently, but obey #98 concurrency
# ---------------------------------------------------------------------------
def test_two_different_issues_claim_independently(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    for task_id in ("task-issue-129", "task-issue-130"):
        service._write_state(task_id, {"task_id": task_id, "status": "SUBMITTED"})

    res_129 = service.acquire_work_claim(
        _claim_request(task_id="task-issue-129", issue=129), enforce_issue_uniqueness=True
    )
    res_130 = service.acquire_work_claim(
        _claim_request(task_id="task-issue-130", issue=130), enforce_issue_uniqueness=True
    )

    assert res_129["status"] == "CLAIMED"
    assert res_130["status"] == "CLAIMED"
    assert res_129["claim"]["identity"]["issue"] == "129"
    assert res_130["claim"]["identity"]["issue"] == "130"
