import pytest
from nexus.orchestrator.task_contract import (
    Evidence,
    EvidenceKind,
    EvidenceRequirement,
    Task,
    TaskStatus,
    TaskStateTransition,
)

def test_task_schema_validation():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest output"]
    )
    assert task.task_id == "TASK-001"
    assert task.current_status == TaskStatus.CREATED

def test_state_transition_validation():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest output"]
    )
    
    # Valid transition
    task.set_status(TaskStatus.ASSIGNED)
    assert task.current_status == TaskStatus.ASSIGNED
    
    # Illegal transition
    with pytest.raises(ValueError, match="Illegal state transition"):
        task.set_status(TaskStatus.INTEGRATED)

def test_claim_guard_incomplete():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest output"]
    )
    # No evidence yet
    assert task.is_done_ready() is False

def test_claim_guard_complete():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest output"]
    )
    task.add_evidence(Evidence(command="pytest", exit_code=0, output_summary="All tests passed"))
    assert task.is_done_ready() is True


def test_evidence_kind_is_inferred_from_command():
    evidence = Evidence(command="pytest -q tests/nexus/orchestrator", exit_code=0, output_summary="ok")
    assert evidence.kind == EvidenceKind.PYTEST


def test_task_normalizes_evidence_requirements():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest output", "nexus acceptance-check"],
    )
    assert task.normalized_evidence_requirements == [
        EvidenceRequirement.PYTEST,
        EvidenceRequirement.ACCEPTANCE_CHECK,
    ]


def test_missing_evidence_requirements_uses_semantic_match():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest", "nexus acceptance-check"],
    )
    task.add_evidence(Evidence(command="pytest -q tests/nexus/orchestrator", exit_code=0, output_summary="ok"))
    assert task.missing_evidence_requirements() == [EvidenceRequirement.ACCEPTANCE_CHECK]

def test_context_report():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest output"],
        branch_name="codex/task/TASK-001",
        last_commit="abc1234",
        working_dir="/tmp/nexus/TASK-001"
    )
    report = task.get_context_report()
    assert report["task_id"] == "TASK-001"
    assert report["branch"] == "codex/task/TASK-001"
    assert report["commit"] == "abc1234"
    assert report["cwd"] == "/tmp/nexus/TASK-001"
# integrity-seal: 1776512137
