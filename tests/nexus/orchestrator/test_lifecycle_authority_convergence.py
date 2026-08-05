from __future__ import annotations

from typing import Any

import pytest

from nexus.contracts.canonical_execution import CanonicalTaskContext
from nexus.engine.canonical_execution import plan_canonical_task_bundle
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.services.unified_runtime import canonical_execution_identity


def _canonical_identity(task_id: str) -> dict[str, Any]:
    bundle = plan_canonical_task_bundle(
        CanonicalTaskContext(
            task_id=task_id,
            task_type="bugfix",
            task_desc="Continue the current canonical execution.",
            execution_channels=("online",),
        )
    )
    return canonical_execution_identity(bundle)


def _direct_request(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_execution_identity": identity,
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
        "allowed_files": ["nexus/example.py"],
        "verifier_commands": ["/usr/bin/true"],
    }


def test_submit_without_current_execution_identity_fails_before_routing(
    tmp_path, monkeypatch
) -> None:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    routed = False

    def route(*_args, **_kwargs):
        nonlocal routed
        routed = True
        raise AssertionError("route selection must not run without an execution identity")

    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.resolve_execution_lane", route
    )

    with pytest.raises(RuntimeError, match="CURRENT_EXECUTION_IDENTITY_REQUIRED"):
        service.submit_task(
            {
                "primary_agent": True,
                "worker": "primary",
                "execution_lane": "DIRECT_CANONICAL",
            }
        )

    assert routed is False
    assert list((tmp_path / "state").glob("*.json")) == []


def test_canonical_identity_task_mismatch_fails_before_routing(
    tmp_path, monkeypatch
) -> None:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    identity = _canonical_identity("worldabc-current")
    routed = False

    def route(*_args, **_kwargs):
        nonlocal routed
        routed = True
        raise AssertionError("route selection must not run after identity mismatch")

    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.resolve_execution_lane", route
    )

    with pytest.raises(RuntimeError, match="CURRENT_EXECUTION_TASK_ID_MISMATCH"):
        service.submit_task(
            {**_direct_request(identity), "task_id": "unexpected-new-route"}
        )

    assert routed is False


def test_canonical_identity_is_resolved_before_active_mutation_routing(
    tmp_path, monkeypatch
) -> None:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    identity = _canonical_identity("worldabc-current")
    service._write_state(
        "worldabc-current",
        {
            "task_id": "worldabc-current",
            "status": "DIRECT_INTENT_RECORDED",
            "canonical_execution_identity": identity,
        },
    )
    observed: dict[str, Any] = {}

    def route(_request, *, active_mutation_tasks):
        observed["active_mutation_tasks"] = active_mutation_tasks
        return {"eligible": True, "execution_lane": "DIRECT_CANONICAL", "blockers": []}

    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.resolve_execution_lane", route
    )
    monkeypatch.setattr(
        service,
        "_submit_direct_canonical",
        lambda request, task_id: {
            "task_id": task_id,
            "canonical_execution_identity": request["canonical_execution_identity"],
        },
    )

    result = service.submit_task(_direct_request(identity))

    assert result["task_id"] == "worldabc-current"
    assert observed["active_mutation_tasks"] == 0
    assert "task_card_path" not in _direct_request(identity)


def test_direct_state_persists_the_exact_canonical_execution_identity(tmp_path) -> None:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    identity = _canonical_identity("worldabc-current")
    request = {
        **_direct_request(identity),
        "task_id": "worldabc-current",
        "action_id": "action-current",
        "attempt_id": "attempt-current",
    }

    result = service._submit_direct_canonical(request, "worldabc-current")
    state = service._read_state("worldabc-current")

    assert result["canonical_execution_identity"] == identity
    assert state["canonical_execution_identity"] == identity
    assert state["canonical_execution_hashes"] == {
        "context_hash": identity["context_hash"],
        "plan_hash": identity["plan_hash"],
        "decision_hash": identity["decision_hash"],
        "projection_hash": identity["projection_hash"],
    }


def test_removed_target_is_not_reported_as_active_lifecycle(tmp_path) -> None:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state(
        "pending-candidate",
        {
            "task_id": "pending-candidate",
            "status": "PENDING_HUMAN_APPROVAL",
            "lease": {"target_worktree": str(tmp_path / "already-removed")},
        },
    )

    status = service.lifecycle_status()

    assert status["active_tasks"] == 1
    assert status["active_targets"] == 0


@pytest.mark.parametrize("status", ["SUBMITTED", "WORKER_COMPLETED", "CANDIDATE_CAPTURED"])
def test_reconcile_never_replays_worker_for_resumable_state(
    tmp_path, monkeypatch, status
) -> None:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state(
        "worldabc-current",
        {
            "task_id": "worldabc-current",
            "status": status,
            "attempt_id": "attempt-current",
            "worker_pid": None,
            "heartbeat_at": "2026-01-01T00:00:00+00:00",
        },
    )
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        service,
        "_launch_worker",
        lambda task_id, attempt_id: calls.append((task_id, attempt_id)),
    )

    result = service.reconcile_task("worldabc-current")

    assert calls == []
    assert result["task_id"] == "worldabc-current"
    assert result["attempt_id"] == "attempt-current"
    assert result["reconciliation_decision"] == "EXPLICIT_RESUME_REQUIRED"
    assert result["mutation_replayed"] is False
    assert result["route_replanned"] is False
    assert result["task_card_created"] is False


def test_explicit_resume_reuses_the_same_task_and_attempt(tmp_path, monkeypatch) -> None:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state(
        "worldabc-current",
        {
            "task_id": "worldabc-current",
            "status": "WORKER_COMPLETED",
            "attempt_id": "attempt-current",
        },
    )
    calls: list[tuple[str, str]] = []

    def launch(task_id: str, attempt_id: str):
        calls.append((task_id, attempt_id))
        return {"task_id": task_id, "attempt_id": attempt_id, "status": "RESUMED"}

    monkeypatch.setattr(service, "_launch_worker", launch)

    result = service.resume_task("worldabc-current")

    assert calls == [("worldabc-current", "attempt-current")]
    assert result == {
        "task_id": "worldabc-current",
        "attempt_id": "attempt-current",
        "status": "RESUMED",
    }
