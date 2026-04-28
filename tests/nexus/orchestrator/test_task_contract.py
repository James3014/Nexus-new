import pytest
from nexus.orchestrator.task_contract import (
    Evidence,
    EvidenceKind,
    EvidenceRequirement,
    DeliveryProfile,
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


def test_code_impact_evidence_is_inferred_from_command():
    evidence = Evidence(command="nexus code:impact --files nexus/orchestrator/task_contract.py", exit_code=0, output_summary="ok")
    assert evidence.kind == EvidenceKind.CODE_IMPACT
    assert evidence.satisfies(EvidenceRequirement.CODE_IMPACT)


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


def test_task_rejects_more_than_two_consulted_agents():
    with pytest.raises(ValueError, match="consulted_agents must contain at most 2 agents"):
        Task(
            task_id="TASK-001",
            owner="Agent-1",
            consulted_agents=["Agent-2", "Agent-3", "Agent-4"],
            allowed_files=["file1.py"],
            done_criteria=["tests pass"],
            evidence_requirements=["pytest output"],
        )


def test_task_rejects_owner_as_consulted_agent():
    with pytest.raises(ValueError, match="owner cannot also be a consulted agent"):
        Task(
            task_id="TASK-001",
            owner="Agent-1",
            consulted_agents=["Agent-1"],
            allowed_files=["file1.py"],
            done_criteria=["tests pass"],
            evidence_requirements=["pytest output"],
        )


def test_task_requires_proposal_ref_when_proposal_gate_is_enabled():
    with pytest.raises(ValueError, match="proposal_ref is required"):
        Task(
            task_id="TASK-001",
            owner="Agent-1",
            requires_proposal=True,
            allowed_files=["file1.py"],
            done_criteria=["tests pass"],
            evidence_requirements=["pytest output"],
        )


def test_live_delivery_profile_requires_human_approval_evidence():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        delivery_profile=DeliveryProfile.LIVE_API,
        allowed_files=["file1.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest output"],
    )
    task.add_evidence(Evidence(command="pytest -q tests/unit", exit_code=0, output_summary="ok"))

    assert task.missing_evidence_requirements() == [EvidenceRequirement.HUMAN_APPROVAL]

    task.add_evidence(Evidence(command="human-approval approved-by:james", exit_code=0, output_summary="approved"))
    assert task.missing_evidence_requirements() == []
# integrity-seal: 1776512137
