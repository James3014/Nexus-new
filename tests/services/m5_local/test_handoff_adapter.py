"""Unit tests for Local -> Online handoff adapter."""

from __future__ import annotations

import pytest

from nexus.services.m5_local.contracts import (
    M5_LOCAL_HANDOFF_SCHEMA,
    HandoffContractError,
    LocalAssistResponse,
    LocalWorkerResponse,
)
from nexus.services.m5_local.handoff_adapter import (
    create_handoff_from_assist,
    create_handoff_from_worker,
)


def test_handoff_from_assist():
    assist_res = LocalAssistResponse(
        task_id="t1",
        status="ESCALATED",
        findings="Partial findings on candidate files",
        candidate_files=["nexus/a.py", "nexus/b.py"],
        evidence_refs=["path:nexus/a.py", "path:nexus/b.py"],
        escalation_reason="LOCAL_CONTEXT_LIMIT",
    )
    packet = create_handoff_from_assist(
        task_id="t1",
        work_id="work-1",
        predecessor_attempt_id="att-local-1",
        predecessor_operation_id="op-local-1",
        repo_identity="James3014/Nexus-new",
        base_sha="5f201a6cb9f7fb7e951642aee3907fec3fd8f39d",
        assist_response=assist_res,
        unresolved_question="Requires Online architectural judgment on concurrency safety",
    )

    assert packet.schema == M5_LOCAL_HANDOFF_SCHEMA
    assert packet.task_id == "t1"
    assert packet.predecessor_attempt_id == "att-local-1"
    assert packet.transition_type == "LOCAL_TO_ONLINE"
    assert packet.inspected_paths == ["nexus/a.py", "nexus/b.py"]
    assert "concurrency safety" in packet.unresolved_questions[0]
    assert packet.escalation_reason == "LOCAL_CONTEXT_LIMIT"
    assert packet.remaining_gate == "ONLINE_REASONING_REQUIRED"


def test_handoff_from_worker():
    worker_res = LocalWorkerResponse(
        task_id="t2",
        attempt_id="att-local-2",
        operation_id="op-local-2",
        status="FAILED",
        diff="--- a/file.py\n+++ b/file.py\n",
        touched_paths=["file.py"],
        escalation_reason="LOCAL_ROLE_NOT_QUALIFIED",
        write_performed=False,
    )
    packet = create_handoff_from_worker(
        task_id="t2",
        work_id="work-2",
        predecessor_attempt_id="att-local-2",
        predecessor_operation_id="op-local-2",
        repo_identity="James3014/Nexus-new",
        base_sha="5f201a6cb9f7fb7e951642aee3907fec3fd8f39d",
        worker_response=worker_res,
        unresolved_question="Online code patch required",
        tests_executed=["tests/test_file.py"],
    )

    assert packet.task_id == "t2"
    assert packet.tests_executed == ["tests/test_file.py"]
    assert packet.escalation_reason == "LOCAL_ROLE_NOT_QUALIFIED"


def test_handoff_missing_required_evidence_fails_closed():
    assist_res = LocalAssistResponse(task_id="t3")
    with pytest.raises(HandoffContractError):
        create_handoff_from_assist(
            task_id="",  # Empty task id
            work_id="w3",
            predecessor_attempt_id="att-3",
            predecessor_operation_id="op-3",
            repo_identity="repo",
            base_sha="sha",
            assist_response=assist_res,
            unresolved_question="q",
        )
