from pathlib import Path
from types import SimpleNamespace

import pytest

import nexus.orchestrator.worker_competition as competition_module
from nexus.orchestrator.worker_competition import (
    WorkerCompetitionCoordinator,
    select_deterministic_winner,
)


def _verified(task_id, provider, *, commit="a" * 40, evidence=1):
    return {
        "task_id": task_id,
        "provider": provider,
        "status": "CANDIDATE_COMMITTED",
        "verified_receipt": {
            "verified": True,
            "scope_gate_passed": True,
            "deletion_gate_passed": True,
            "controller_gate_passed": True,
            "protected_contract_gate_passed": True,
            "verifier_gate_passed": True,
            "verifier_evidence": [{} for _ in range(evidence)],
        },
        "promotion_packet": {"candidate_commit_sha": commit},
        "candidate_commit_created": True,
        "merge_performed": False,
        "push_performed": False,
    }


def test_competition_selects_verified_candidate_by_declared_provider_order():
    decision = select_deterministic_winner(
        [_verified("task-opencode", "opencode"), _verified("task-codex", "codex")],
        ["codex", "opencode"],
    )

    assert decision["status"] == "WINNER_SELECTED"
    assert decision["winner_task_id"] == "task-codex"
    assert decision["ranked_candidates"] == ["task-codex", "task-opencode"]


def test_competition_rejects_unverified_candidate():
    rejected = _verified("task-codex", "codex")
    rejected["verified_receipt"]["verified"] = False

    decision = select_deterministic_winner([rejected], ["codex"])

    assert decision["status"] == "NO_WINNER"
    assert decision["winner_task_id"] is None


def test_submit_creates_distinct_target_candidates_in_parallel(tmp_path):
    class FakeService:
        state_dir = tmp_path / "service-state"

        def __init__(self):
            self.requests = []

        def submit_task(self, request):
            self.requests.append(dict(request))
            return {"task_id": request["task_id"], "status": "SUBMITTED"}

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "SUBMITTED"}

    service = FakeService()
    coordinator = WorkerCompetitionCoordinator(service)
    request = {
        "task_id": "refactor-001",
        "competition_id": "refactor-competition",
        "target_repo_root": str(tmp_path / "targets"),
        "target_worktree_root": str(tmp_path / "targets"),
    }

    state = coordinator.submit(request, ["codex", "opencode"])

    assert state["status"] == "SUBMITTED"
    assert {item["provider"] for item in state["candidates"]} == {"codex", "opencode"}
    assert len({item["target_repo_root"] for item in state["candidates"]}) == 2
    assert {item["worker"] for item in service.requests} == {"codex", "opencode"}
    assert Path(state["candidates"][0]["target_repo_root"]).parent == (tmp_path / "targets").resolve()


def test_get_persists_winner_after_all_candidates_finish(tmp_path):
    class FakeService:
        state_dir = tmp_path / "service-state"

        def __init__(self):
            self.states = {}

        def submit_task(self, request):
            self.states[request["task_id"]] = {"task_id": request["task_id"], "status": "SUBMITTED"}
            return self.states[request["task_id"]]

        def get_task(self, task_id):
            return self.states[task_id]

    service = FakeService()
    coordinator = WorkerCompetitionCoordinator(service)
    request = {
        "task_id": "refactor-002",
        "competition_id": "refactor-competition-002",
        "target_repo_root": str(tmp_path / "targets"),
        "target_worktree_root": str(tmp_path / "targets"),
    }
    submitted = coordinator.submit(request, ["codex", "opencode"])
    for candidate in submitted["candidates"]:
        service.states[candidate["task_id"]] = _verified(
            candidate["task_id"], candidate["provider"], evidence=2 if candidate["provider"] == "codex" else 1
        )

    current = coordinator.get("refactor-competition-002")

    assert current["status"] == "WINNER_SELECTED"
    assert current["winner"]["winner_task_id"].endswith("-codex")


def test_push_winner_passes_exact_effect_identity_to_governed_push_sink(monkeypatch, tmp_path):
    class FakeService:
        state_dir = tmp_path / "service-state"

        def get_task(self, task_id):
            return {
                "task_id": task_id,
                "contract": {"controller_repo_root": str(tmp_path / "repo")},
            }

    coordinator = WorkerCompetitionCoordinator(FakeService())
    coordinator._write({
        "schema": "nexus.worker_competition_state.v1",
        "competition_id": "push-competition",
        "status": "INTEGRATED",
        "winner": {"winner_task_id": "winner-task"},
        "integration": {
            "integration_branch": "nexus/integration/main",
            "integration_commit_sha": "a" * 40,
            "merge_performed": True,
            "push_performed": False,
        },
        "candidates": [],
    })
    observed = {}

    def push(_self, **kwargs):
        observed["push"] = kwargs
        return SimpleNamespace(
            schema="nexus.governed_push_receipt.v2",
            remote="origin",
            branch="nexus/integration/main",
            pushed_commit_sha="a" * 40,
            remote_commit_sha="a" * 40,
            push_performed=True,
            push_attempted=True,
            push_acknowledged=True,
            effect_present=True,
            preexisting_effect=False,
            reconciled_after_uncertain_ack=False,
            force_push=False,
            authorized=True,
            authorization_hash="1" * 64,
            authorization_effect_hash="2" * 64,
            authorization_grant_receipt_hash="3" * 64,
        )

    monkeypatch.setenv("NEXUS_GOVERNED_PUSH_REMOTES", "origin")
    monkeypatch.setattr(competition_module.GovernedPushManager, "push", push)

    result = coordinator.push_winner("push-competition", remote="origin")

    assert observed["push"] == {
        "competition_id": "push-competition",
        "winner_task_id": "winner-task",
        "remote": "origin",
        "branch": "nexus/integration/main",
        "expected_sha": "a" * 40,
        "integration_receipt": {
            "integration_branch": "nexus/integration/main",
            "integration_commit_sha": "a" * 40,
            "merge_performed": True,
            "push_performed": False,
        },
    }
    assert result["status"] == "PUSHED"
    assert result["push"]["authorization_hash"] == "1" * 64


def test_push_winner_sink_authority_failure_preserves_integrated_state(monkeypatch, tmp_path):
    class FakeService:
        state_dir = tmp_path / "service-state"

        def get_task(self, task_id):
            return {
                "task_id": task_id,
                "contract": {"controller_repo_root": str(tmp_path / "repo")},
            }

    coordinator = WorkerCompetitionCoordinator(FakeService())
    coordinator._write({
        "schema": "nexus.worker_competition_state.v1",
        "competition_id": "blocked-push",
        "status": "INTEGRATED",
        "winner": {"winner_task_id": "winner-task"},
        "integration": {
            "integration_branch": "nexus/integration/main",
            "integration_commit_sha": "b" * 40,
            "merge_performed": True,
            "push_performed": False,
        },
        "candidates": [],
    })
    def push(_self, **_kwargs):
        raise PermissionError("governed push requires durable Owner authorization")

    monkeypatch.setenv("NEXUS_GOVERNED_PUSH_REMOTES", "origin")
    monkeypatch.setattr(competition_module.GovernedPushManager, "push", push)

    with pytest.raises(PermissionError, match="durable Owner authorization"):
        coordinator.push_winner("blocked-push", remote="origin")

    assert coordinator._read("blocked-push")["status"] == "INTEGRATED"


def test_get_preserves_integrated_and_pushed_terminal_status_on_refresh(tmp_path):
    class FakeService:
        state_dir = tmp_path / "service-state"

        def __init__(self):
            self.states = {}

        def submit_task(self, request):
            self.states[request["task_id"]] = {"task_id": request["task_id"], "status": "SUBMITTED"}
            return self.states[request["task_id"]]

        def get_task(self, task_id):
            return self.states[task_id]

    service = FakeService()
    coordinator = WorkerCompetitionCoordinator(service)
    request = {
        "task_id": "refactor-003",
        "competition_id": "refactor-competition-003",
        "target_repo_root": str(tmp_path / "targets"),
        "target_worktree_root": str(tmp_path / "targets"),
    }
    coordinator.submit(request, ["codex", "opencode"])

    for status in ("INTEGRATED", "PUSHED"):
        state = coordinator._read("refactor-competition-003")
        state["status"] = status
        coordinator._write(state)

        refreshed = coordinator.get("refactor-competition-003")
        assert refreshed["status"] == status
