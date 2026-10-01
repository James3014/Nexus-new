"""Tests for #129 canonical public read-only work claim surface.

Invariants verified:
- Same canonical authority/store (SelfHostedTaskService)
- No second claim registry
- read/list never mints, transfers, or releases ownership
- claim_enforcement_state remains below REPO_ENFORCED (FAIL_CLOSED_PROJECTION_ONLY)
- Truthful exposure of all required fields: repository, issue, task_id, attempt_id,
  claim_id, holder, generation, fencing_token, scope/mutation_domain, state,
  source/admission binding, freshness, canonical_revision
- Stale generation is detectably marked
- Filtering by repo, issue, worker, status
- Malformed/tampered active claims make list fail closed instead of disappearing
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.orchestrator.self_hosted_task_service import (
    SelfHostedTaskService,
)


@pytest.fixture
def service(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    return svc


def _sample_claim_request(task_id: str = "task-claim-1", **extra):
    base = {
        "repository": "James3014/Nexus-new",
        "issue": "129",
        "task_id": task_id,
        "attempt_id": f"attempt-{task_id}",
        "action_id": "action-01",
        "worker_id": "worker-luna",
        "provider": "openai",
        "model": "gpt-6-luna",
        "role": "PRIMARY_PRODUCER",
        "claim_ceiling": "PROJECTION_READ_ONLY_NOT_REPO_ENFORCED",
        "base_revision": "a" * 40,
        "source_hash": "b" * 40,
        "task_card_path": "tasks/test.yaml",
        "allowed_files": ["nexus/orchestrator/self_hosted_task_service.py"],
        "workforce_admission": {"admission_id": "adm-001", "verdict": "PERMITTED"},
        "provider_preflight": {"preflight_id": "pre-001"},
    }
    base.update(extra)
    return base


def _seed_task_state(service: SelfHostedTaskService, task_id: str, state: dict | None = None):
    initial = {
        "task_id": task_id,
        "attempt_id": f"attempt-{task_id}",
        "status": "SUBMITTED",
        "revision": 3,
    }
    if state:
        initial.update(state)
    with service._state_lock():
        service._write_state_locked(task_id, initial)


def test_read_work_claim_not_found_and_no_claim(service: SelfHostedTaskService):
    # Task completely missing
    res = service.read_work_claim({"task_id": "nonexistent"})
    assert res["status"] == "NOT_FOUND"
    assert res["found"] is False

    # Task exists but has no claim
    _seed_task_state(service, "task-unclaimed")
    res2 = service.read_work_claim({"task_id": "task-unclaimed"})
    assert res2["status"] == "NO_ACTIVE_CLAIM"
    assert res2["found"] is False


def test_read_work_claim_exposes_all_required_contract_fields(service: SelfHostedTaskService):
    task_id = "task-alpha"
    _seed_task_state(service, task_id)
    req = _sample_claim_request(task_id=task_id)

    # Acquire claim
    acq = service.acquire_work_claim(req)
    assert acq["status"] == "CLAIMED"

    # Read claim via public surface
    read_res = service.read_work_claim({"task_id": task_id})
    assert read_res["status"] == "FOUND"
    assert read_res["found"] is True

    claim = read_res["claim"]
    assert claim["schema"] == service.PUBLIC_WORK_CLAIM_SCHEMA
    assert claim["claim_ceiling"] == service.PUBLIC_WORK_CLAIM_CEILING
    # Must NOT claim REPO_ENFORCED
    assert claim["claim_enforcement_state"] != "REPO_ENFORCED"
    assert claim["claim_enforcement_state"] == "FAIL_CLOSED_PROJECTION_ONLY"

    # Identity and fencing fields
    assert claim["repository"] == "James3014/Nexus-new"
    assert claim["issue"] == "129"
    assert claim["task_id"] == task_id
    assert claim["attempt_id"] == f"attempt-{task_id}"
    assert claim["claim_id"]
    assert claim["generation"] == 1
    # Raw mutation credential MUST NOT be exposed in public read projection
    assert "fencing_token" not in claim
    assert claim["fence_identity"] == f"urn:nexus:claim_fence:{claim['claim_id']}:1"
    assert claim["fence_hash"]
    assert claim["holder"] == "worker-luna"
    assert claim["provider"] == "openai"
    assert claim["model"] == "gpt-6-luna"
    assert claim["role"] == "PRIMARY_PRODUCER"
    assert claim["allowed_files"] == ["nexus/orchestrator/self_hosted_task_service.py"]
    assert claim["mutation_domain"] == ["nexus/orchestrator/self_hosted_task_service.py"]
    assert claim["state"] == "CLAIMED"
    assert claim["admission_identity"]
    assert claim["provider_preflight_identity"]
    assert claim["observed_at"]
    assert claim["canonical_revision"] >= 1
    assert claim["generation_status"] == "CURRENT"

    # Alias check (ignoring observed_at timestamp difference)
    alias_res = service.read_claim({"task_id": task_id})
    assert {k: v for k, v in alias_res["claim"].items() if k != "observed_at"} == {
        k: v for k, v in read_res["claim"].items() if k != "observed_at"
    }


def test_read_work_claim_detects_stale_and_future_generation(service: SelfHostedTaskService):
    task_id = "task-gen-test"
    _seed_task_state(service, task_id)
    req = _sample_claim_request(task_id=task_id)

    acq = service.acquire_work_claim(req)
    claim = acq["claim"]

    # Recover advances generation to 2 (needs current claim_id, generation, fencing_token)
    rec_req = dict(req)
    rec_req["claim_id"] = claim["claim_id"]
    rec_req["generation"] = claim["generation"]
    rec_req["fencing_token"] = claim["fencing_token"]

    rec = service.recover_work_claim(rec_req, reason="HOST_FAILOVER")
    assert rec["status"] == "CLAIMED"
    assert rec["claim"]["generation"] == 2

    # Read probing old generation 1 -> marked STALE_GENERATION
    stale_probe = service.read_work_claim({"task_id": task_id, "generation": 1})
    assert stale_probe["status"] == "FOUND"
    assert stale_probe["claim"]["generation"] == 2
    assert stale_probe["claim"]["generation_status"] == "STALE_GENERATION"
    assert stale_probe["claim"]["recovery_reason"] == "HOST_FAILOVER"

    # Read probing current generation 2 -> CURRENT
    current_probe = service.read_work_claim({"task_id": task_id, "generation": 2})
    assert current_probe["claim"]["generation_status"] == "CURRENT"

    # Read probing future generation 3 -> marked FUTURE_GENERATION (never false-safe CURRENT)
    future_probe = service.read_work_claim({"task_id": task_id, "generation": 3})
    assert future_probe["claim"]["generation_status"] == "FUTURE_GENERATION"

    # Invalid generation type probe fails closed
    inv_probe = service.read_work_claim({"task_id": task_id, "generation": "two"})
    assert inv_probe["status"] == "BLOCKED"
    assert inv_probe["reason"] == "INVALID_GENERATION"


def test_read_claim_is_strictly_read_only_and_never_mints_ownership(service: SelfHostedTaskService):
    task_id = "task-readonly-check"
    _seed_task_state(service, task_id)
    path = service._state_path(task_id)
    state_before = path.read_text(encoding="utf-8")

    # Read unclaimed task
    service.read_work_claim({"task_id": task_id})
    assert path.read_text(encoding="utf-8") == state_before

    # Acquire claim
    req = _sample_claim_request(task_id=task_id)
    service.acquire_work_claim(req)
    state_with_claim = path.read_text(encoding="utf-8")

    # Multiple reads do not alter state file
    service.read_work_claim({"task_id": task_id})
    service.read_claim({"task_id": task_id})
    service.list_active_work_claims()
    assert path.read_text(encoding="utf-8") == state_with_claim


def test_list_active_work_claims_and_filtering(service: SelfHostedTaskService):
    # Seed 3 tasks
    for i in range(1, 4):
        _seed_task_state(service, f"task-{i}")

    # Task 1: repo A, issue 129, worker luna
    service.acquire_work_claim(_sample_claim_request(task_id="task-1", repository="repo-A", issue="129", worker_id="luna"))
    # Task 2: repo A, issue 98, worker bob
    service.acquire_work_claim(_sample_claim_request(task_id="task-2", repository="repo-A", issue="98", worker_id="bob"))
    # Task 3: repo B, issue 129, worker luna
    service.acquire_work_claim(_sample_claim_request(task_id="task-3", repository="repo-B", issue="129", worker_id="luna"))

    # Unfiltered listing
    all_claims = service.list_active_work_claims()
    assert len(all_claims) == 3

    # Filter by repo
    repo_a_claims = service.list_active_work_claims({"repository": "repo-A"})
    assert len(repo_a_claims) == 2
    assert {c["task_id"] for c in repo_a_claims} == {"task-1", "task-2"}

    # Filter by issue
    issue_129_claims = service.list_active_work_claims({"issue": "129"})
    assert len(issue_129_claims) == 2
    assert {c["task_id"] for c in issue_129_claims} == {"task-1", "task-3"}

    # Filter by worker
    luna_claims = service.list_active_work_claims({"worker_id": "luna"})
    assert len(luna_claims) == 2
    assert {c["task_id"] for c in luna_claims} == {"task-1", "task-3"}

    # Filter by repo + worker
    repo_a_luna = service.list_active_work_claims({"repository": "repo-A", "worker_id": "luna"})
    assert len(repo_a_luna) == 1
    assert repo_a_luna[0]["task_id"] == "task-1"

    # Alias check
    assert [c["task_id"] for c in service.list_active_claims()] == [
        c["task_id"] for c in all_claims
    ]


def test_list_active_work_claims_fails_closed_on_malformed_active_claim(service: SelfHostedTaskService):
    task_id = "task-corrupted"
    _seed_task_state(service, task_id)
    with service._state_lock():
        path = service._state_path(task_id)
        # Put an invalid active work_claim record missing identity.
        path.write_text(
            json.dumps({"task_id": task_id, "work_claim": {"claim_id": "bad"}}),
            encoding="utf-8",
        )

    # A corrupted active claim must never disappear into an apparently empty list.
    with pytest.raises(RuntimeError, match="WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_MALFORMED"):
        service.list_active_work_claims()


def test_read_work_claim_fails_closed_on_tampered_stored_record(service: SelfHostedTaskService):
    task_id = "task-tampered"
    _seed_task_state(service, task_id)
    req = _sample_claim_request(task_id=task_id)
    service.acquire_work_claim(req)

    # Tamper with the stored state file directly
    with service._state_lock():
        path = service._state_path(task_id)
        state = json.loads(path.read_text(encoding="utf-8"))
        state["work_claim"]["identity_hash"] = "forged-identity-hash"
        path.write_text(json.dumps(state), encoding="utf-8")

    # Read must fail closed rather than return forged/tampered claim
    res = service.read_work_claim({"task_id": task_id})
    assert res["status"] == "BLOCKED"
    assert res["reason"] == "WORK_CLAIM_TAMPERED"
    assert res["found"] is False

    # Listing the same canonical store must also fail closed instead of hiding it.
    with pytest.raises(RuntimeError, match="WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_TAMPERED"):
        service.list_active_work_claims()


def test_read_work_claim_does_not_leak_mutation_credential(service: SelfHostedTaskService):
    task_id = "task-credential-guard"
    _seed_task_state(service, task_id)
    req = _sample_claim_request(task_id=task_id)
    acq = service.acquire_work_claim(req)
    raw_token = acq["claim"]["fencing_token"]
    assert raw_token  # Authoritative acquire returned token to holder

    read_res = service.read_work_claim({"task_id": task_id})
    assert read_res["found"] is True
    claim = read_res["claim"]

    # Raw token must not appear in any value of the projected public dictionary
    for k, v in claim.items():
        assert v != raw_token, f"raw token leaked in key {k}"
    assert "fencing_token" not in claim
    assert claim["fence_identity"]
    assert claim["fence_hash"]
