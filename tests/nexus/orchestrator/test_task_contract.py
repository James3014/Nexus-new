import json

import pytest
from nexus.orchestrator.task_contract import (
    ApprovalStatus,
    AcceptanceProfile,
    ArchitectureDecision,
    ArchitectTaskContract,
    DevelopmentGoal,
    Evidence,
    EvidenceKind,
    EvidenceRequirement,
    DeliveryProfile,
    HumanApprovalPolicy,
    MutationMode,
    SelfHostedTaskContract,
    Task,
    TaskStatus,
    TaskStateTransition,
)


EXACT_CONTROLLER_SHA = "a" * 40
EXACT_TARGET_SHA = "b" * 40


def _self_hosted_contract(tmp_path, **overrides):
    values = {
        "task_id": "sh2-contract",
        "objective": "Capture a bounded candidate diff",
        "controller_revision": EXACT_CONTROLLER_SHA,
        "target_base_revision": EXACT_TARGET_SHA,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / "sh2-contract"),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["nexus/orchestrator/task_contract.py"],
        "forbidden_files": ["secrets/"],
        "verifier_commands": ["python3 -m pytest -q"],
        "protected_contracts": ["receipt-v1"],
        "preferred_provider": "codex",
        "fallback_provider": None,
        "maximum_provider_calls": 0,
        "maximum_replans": 0,
        "mutation_mode": MutationMode.WORKING_TREE_ONLY,
        "human_approval_required": True,
    }
    values.update(overrides)
    return SelfHostedTaskContract(**values)

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


def test_self_hosted_contract_requires_exact_controller_sha(tmp_path):
    with pytest.raises(ValueError, match="controller_revision"):
        _self_hosted_contract(tmp_path, controller_revision="abc123")


def test_self_hosted_contract_requires_exact_target_sha(tmp_path):
    with pytest.raises(ValueError, match="target_base_revision"):
        _self_hosted_contract(tmp_path, target_base_revision="B" * 40)


def test_self_hosted_contract_rejects_absolute_allowed_path(tmp_path):
    with pytest.raises(ValueError, match="repository-relative"):
        _self_hosted_contract(tmp_path, allowed_files=["/etc/passwd"])


def test_self_hosted_contract_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError, match="traversal"):
        _self_hosted_contract(tmp_path, allowed_files=["nexus/../secrets.txt"])


def test_self_hosted_contract_requires_human_approval(tmp_path):
    with pytest.raises(ValueError, match="human approval"):
        _self_hosted_contract(tmp_path, human_approval_required=False)


def test_self_hosted_contract_hash_is_deterministic(tmp_path):
    first = _self_hosted_contract(tmp_path)
    second = _self_hosted_contract(tmp_path)

    assert first.schema == "nexus.self_hosted_task_contract.v1"
    assert first.contract_hash == second.contract_hash
    assert len(first.contract_hash) == 64
    assert json.loads(first.model_dump_json())["schema"] == first.schema
    assert ApprovalStatus.PENDING.value == "PENDING"


def _architect_contract(tmp_path, **overrides):
    values = {
        "task_id": "architect-contract",
        "objective": "Build the governed worker vertical",
        "goal": DevelopmentGoal(
            what="Build the governed worker vertical",
            why="Remove unsafe manual agent handoff",
        ),
        "architecture_decisions": [
            ArchitectureDecision(
                decision_id="worker-boundary",
                selected_option="Target-only mutation",
                rationale="Keep the Controller immutable",
                rejected_alternatives=["Controller working-tree mutation"],
            )
        ],
        "acceptance_profile": AcceptanceProfile(
            verifier_commands=["python3 -m pytest -q"],
            protected_contracts=["candidate-receipt-v1"],
            required_evidence=["candidate_state_hash", "controller_unchanged"],
        ),
        "human_approval_policy": HumanApprovalPolicy(
            decision_approval_required=True,
            promotion_approval_required=True,
            approver_roles=["James"],
        ),
        "controller_revision": EXACT_CONTROLLER_SHA,
        "target_base_revision": EXACT_TARGET_SHA,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / "architect-contract"),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["nexus/"],
        "forbidden_files": ["secrets/"],
        "verifier_commands": ["python3 -m pytest -q"],
        "protected_contracts": ["candidate-receipt-v1"],
        "preferred_provider": "codex",
        "fallback_provider": None,
        "maximum_provider_calls": 1,
        "maximum_replans": 0,
        "mutation_mode": MutationMode.WORKING_TREE_ONLY,
        "human_approval_required": True,
    }
    values.update(overrides)
    return ArchitectTaskContract(**values)


def test_architect_goal_requires_non_empty_why(tmp_path):
    with pytest.raises(ValueError, match="why"):
        _architect_contract(
            tmp_path,
            goal=DevelopmentGoal(
                what="Build the governed worker vertical",
                why=" ",
            ),
        )


def test_architecture_decision_requires_rationale(tmp_path):
    with pytest.raises(ValueError, match="rationale"):
        _architect_contract(
            tmp_path,
            architecture_decisions=[
                ArchitectureDecision(
                    decision_id="worker-boundary",
                    selected_option="Target-only mutation",
                    rationale=" ",
                    rejected_alternatives=["Controller mutation"],
                )
            ],
        )


def test_architect_contract_requires_acceptance_profile(tmp_path):
    with pytest.raises(ValueError, match="acceptance_profile"):
        _architect_contract(tmp_path, acceptance_profile=None)


def test_architect_contract_requires_human_approval_policy(tmp_path):
    with pytest.raises(ValueError, match="human_approval_policy"):
        _architect_contract(tmp_path, human_approval_policy=None)


def test_architect_contract_binds_objective_to_goal(tmp_path):
    with pytest.raises(ValueError, match="objective.*goal"):
        _architect_contract(
            tmp_path,
            objective="Different objective",
        )


def test_architect_contract_hash_is_deterministic_and_serializable(tmp_path):
    first = _architect_contract(tmp_path)
    second = _architect_contract(tmp_path)

    assert first.schema == "nexus.self_hosted_task_contract.v2"
    assert first.contract_hash == second.contract_hash
    payload = json.loads(first.model_dump_json())
    assert payload["goal"]["why"] == "Remove unsafe manual agent handoff"
    assert payload["human_approval_policy"]["promotion_approval_required"] is True


def test_v1_contract_remains_available_for_sh2_replay(tmp_path):
    contract = _self_hosted_contract(tmp_path)

    assert contract.schema == "nexus.self_hosted_task_contract.v1"
    assert json.loads(contract.model_dump_json())["schema"] == contract.schema
# integrity-seal: 1776512137
