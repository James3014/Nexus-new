"""Tests for #129 canonical public read-only work claim surface.

Invariants verified:
- Same canonical authority/store (SelfHostedTaskService)
- No second claim registry
- read/list never mints, transfers, or releases ownership
- claim_enforcement_state remains below REPO_ENFORCED (FAIL_CLOSED_PROJECTION_ONLY)
- Truthful exposure of observational fields: repository, issue, task_id, attempt_id,
  opaque claim/fence identities, holder, generation, scope/mutation_domain, state,
  source/admission binding, freshness, canonical_revision; raw mutation credentials stay private
- Stale generation is detectably marked
- Filtering by repo, issue, worker, status
- Malformed/tampered active claims make list fail closed instead of disappearing
"""

from __future__ import annotations

import hashlib
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
    assert "claim_id" not in claim
    assert claim["claim_identity"].startswith("urn:nexus:claim:")
    assert claim["generation"] == 1
    # Neither the raw mutation credential nor enough material to reconstruct it
    # may be exposed by the public projection.
    assert "fencing_token" not in claim
    assert claim["fence_identity"].startswith("urn:nexus:claim_fence:")
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

    # Remove the writer lock artifact: public reads must not recreate it.
    lock_path = service._lock_path()
    lock_path.unlink(missing_ok=True)

    service.read_work_claim({"task_id": task_id})
    assert path.read_text(encoding="utf-8") == state_before
    assert not lock_path.exists()

    req = _sample_claim_request(task_id=task_id)
    service.acquire_work_claim(req)
    state_with_claim = path.read_text(encoding="utf-8")
    lock_path.unlink(missing_ok=True)

    service.read_work_claim({"task_id": task_id})
    service.read_claim({"task_id": task_id})
    service.list_active_work_claims()
    assert path.read_text(encoding="utf-8") == state_with_claim
    assert not lock_path.exists()


def test_list_active_work_claims_and_filtering(service: SelfHostedTaskService):
    # Seed 3 tasks
    for i in range(1, 4):
        _seed_task_state(service, f"task-{i}")

    # Task 1: repo A, issue 129, worker luna
    service.acquire_work_claim(
        _sample_claim_request(task_id="task-1", repository="repo-A", issue="129", worker_id="luna")
    )
    # Task 2: repo A, issue 98, worker bob
    service.acquire_work_claim(
        _sample_claim_request(task_id="task-2", repository="repo-A", issue="98", worker_id="bob")
    )
    # Task 3: repo B, issue 129, worker luna
    service.acquire_work_claim(
        _sample_claim_request(task_id="task-3", repository="repo-B", issue="129", worker_id="luna")
    )

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


def test_list_active_work_claims_fails_closed_on_malformed_active_claim(
    service: SelfHostedTaskService,
):
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

    # Raw token and its reconstructable claim_id component must not appear in
    # any public projection value.  Generation alone is observational.
    raw_claim_id = acq["claim"]["claim_id"]
    for k, v in claim.items():
        assert v != raw_token, f"raw token leaked in key {k}"
        assert v != raw_claim_id, f"raw claim_id leaked in key {k}"
        if isinstance(v, str):
            assert raw_claim_id not in v, f"raw claim_id embedded in key {k}"
    assert "fencing_token" not in claim
    assert "claim_id" not in claim
    assert claim["claim_identity"]
    assert claim["fence_identity"]
    assert claim["fence_hash"]
    assert f"{raw_claim_id}:{claim['generation']}" == raw_token


def test_read_and_list_fail_closed_on_tampered_fencing_token(service: SelfHostedTaskService):
    task_id = "task-fence-tamper"
    _seed_task_state(service, task_id)
    service.acquire_work_claim(_sample_claim_request(task_id=task_id))

    with service._state_lock():
        path = service._state_path(task_id)
        state = json.loads(path.read_text(encoding="utf-8"))
        state["work_claim"]["fencing_token"] = "forged-token"
        path.write_text(json.dumps(state), encoding="utf-8")

    read_res = service.read_work_claim({"task_id": task_id})
    assert read_res["status"] == "BLOCKED"
    assert read_res["reason"] == "WORK_CLAIM_STALE_FENCE"
    assert read_res["found"] is False

    with pytest.raises(RuntimeError, match="WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_STALE_FENCE"):
        service.list_active_work_claims()


@pytest.mark.parametrize("status", [None, True, "SUPERSEDED"])
def test_read_and_list_reject_malformed_active_claim_status(
    service: SelfHostedTaskService,
    status,
):
    task_id = "task-status-tamper"
    _seed_task_state(service, task_id)
    service.acquire_work_claim(_sample_claim_request(task_id=task_id))

    with service._state_lock():
        path = service._state_path(task_id)
        state = json.loads(path.read_text(encoding="utf-8"))
        if status is None:
            state["work_claim"].pop("status", None)
        else:
            state["work_claim"]["status"] = status
        path.write_text(json.dumps(state), encoding="utf-8")

    read_res = service.read_work_claim({"task_id": task_id})
    assert read_res["status"] == "BLOCKED"
    assert read_res["reason"] == "WORK_CLAIM_MALFORMED"
    assert read_res["found"] is False

    with pytest.raises(RuntimeError, match="WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_MALFORMED"):
        service.list_active_work_claims()


def test_read_and_list_reject_claim_transplanted_between_task_states(
    service: SelfHostedTaskService,
):
    for task_id in ("task-enclosure-a", "task-enclosure-b"):
        _seed_task_state(service, task_id)
        service.acquire_work_claim(_sample_claim_request(task_id=task_id))

    with service._state_lock():
        path_a = service._state_path("task-enclosure-a")
        path_b = service._state_path("task-enclosure-b")
        state_a = json.loads(path_a.read_text(encoding="utf-8"))
        state_b = json.loads(path_b.read_text(encoding="utf-8"))
        state_a["work_claim"] = state_b["work_claim"]
        path_a.write_text(json.dumps(state_a), encoding="utf-8")

    read_res = service.read_work_claim({"task_id": "task-enclosure-a"})
    assert read_res["status"] == "BLOCKED"
    assert read_res["reason"] == "WORK_CLAIM_TAMPERED"
    assert read_res["found"] is False

    with pytest.raises(RuntimeError, match="WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_TAMPERED"):
        service.list_active_work_claims()


def test_public_projection_does_not_hash_mutation_credential_material(
    service: SelfHostedTaskService,
):
    task_id = "task-low-entropy-claim-id"
    _seed_task_state(service, task_id)
    req = _sample_claim_request(task_id=task_id)
    req["claim_id"] = "1"
    acquired = service.acquire_work_claim(req)
    assert acquired["claim"]["claim_id"] == "1"
    assert acquired["claim"]["fencing_token"] == "1:1"

    projected = service.read_work_claim({"task_id": task_id})["claim"]
    leaked_claim_hash = hashlib.sha256(b"1").hexdigest()
    leaked_fence_hash = hashlib.sha256(b"1:1").hexdigest()
    assert leaked_claim_hash not in projected["claim_identity"]
    assert leaked_fence_hash != projected["fence_hash"]
    assert leaked_fence_hash not in projected["fence_identity"]
