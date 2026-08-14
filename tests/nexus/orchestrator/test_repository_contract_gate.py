from dataclasses import replace
from datetime import datetime, timedelta, timezone
import re
import subprocess
from pathlib import Path

from nexus.orchestrator.repository_contract_gate import RepositoryContractGate
from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
from nexus.orchestrator.task_contract import MutationMode, SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(root: Path, *, with_policy_inputs: bool) -> tuple[str, str]:
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "repository-contract@example.test")
    _git(root, "config", "user.name", "Repository Contract")
    (root / "bounded.txt").write_text("base\n", encoding="utf-8")
    if with_policy_inputs:
        (root / "AGENTS.md").write_text("agent authority\n", encoding="utf-8")
        (root / "MUSE_PROTO.md").write_text("proto authority\n", encoding="utf-8")
        (root / ".github/workflows").mkdir(parents=True)
        (root / ".github/workflows/pytest.yml").write_text(
            "name: pytest\n",
            encoding="utf-8",
        )
        (root / "docs/arch").mkdir(parents=True)
        (root / "docs/arch/module-inventory.generated.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    target_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(root, "rev-parse", "HEAD")
    return target_sha, controller_sha


def _contract(
    controller_root: Path,
    target_root: Path,
    *,
    task_id: str,
    target_sha: str,
    controller_sha: str,
    allowed_files: list[str],
    verifier_commands: list[str],
) -> SelfHostedTaskContract:
    return SelfHostedTaskContract(
        task_id=task_id,
        objective="Verify repository contract gate",
        controller_revision=controller_sha,
        target_base_revision=target_sha,
        controller_repo_root=str(controller_root),
        target_repo_root=str(target_root / task_id),
        target_worktree_root=str(target_root),
        allowed_files=allowed_files,
        verifier_commands=verifier_commands,
        protected_contracts=["candidate-receipt-v1"],
        preferred_provider="codex",
        maximum_provider_calls=1,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )


def _prepare(contract: SelfHostedTaskContract, target_root: Path):
    controller = SelfHostedDevelopmentController(WorktreeManager(str(target_root)))
    lease = controller.prepare_task(contract)
    return controller, lease


def test_repository_contract_gate_records_shadow_findings_without_blocking(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="shadow-findings",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=[
            "bounded.txt",
            ".github/workflows/new.yml",
            "docs/arch/module-inventory.generated.json",
        ],
        verifier_commands=[],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "bounded.txt").unlink()
    (target / ".github/workflows").mkdir(parents=True)
    (target / ".github/workflows/new.yml").write_text("name: new\n", encoding="utf-8")
    (target / "docs/arch").mkdir(parents=True)
    (target / "docs/arch/module-inventory.generated.json").write_text(
        '{"new": true}\n',
        encoding="utf-8",
    )
    current = controller.collect_candidate(contract, lease)
    candidate = replace(current, contract_hash="0" * 64)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=candidate,
        current=current,
    )

    assert receipt.passed is True
    assert {finding.kind for finding in receipt.findings} >= {
        "ci_workflow_authority_drift",
        "declared_test_verifier_absent",
        "tracked_deletion",
        "candidate_lineage_mismatch",
        "generated_facts_authority_drift",
    }
    assert all(finding.severity == "shadow" for finding in receipt.findings)


def test_repository_contract_gate_policy_hash_is_deterministic(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=True)
    contract = _contract(
        controller_root,
        target_root,
        task_id="deterministic-hash",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    Path(lease.target_worktree, "bounded.txt").write_text("candidate\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)
    gate = RepositoryContractGate(controller.worktree_manager)

    first = gate.evaluate(contract, lease, current, current)
    second = gate.evaluate(contract, lease, current, current)

    assert first.policy_revision_hash == second.policy_revision_hash
    assert re.fullmatch(r"[0-9a-f]{64}", first.policy_revision_hash)
    assert first.findings == second.findings
    assert first.passed is True


def test_committed_candidate_recheck_binds_exact_commit_tree_and_policy(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=True)
    contract = _contract(
        controller_root,
        target_root,
        task_id="committed-recheck",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    (controller_root / "bounded.txt").write_text("candidate\n", encoding="utf-8")
    _git(controller_root, "add", "bounded.txt")
    _git(controller_root, "commit", "-m", "candidate")
    candidate_commit = _git(controller_root, "rev-parse", "HEAD")
    candidate_tree = _git(controller_root, "rev-parse", "HEAD^{tree}")
    gate = RepositoryContractGate(WorktreeManager(str(target_root)))
    policy_hash = gate._policy_revision_hash(
        target_sha,
        gate._policy_input_hashes(controller_root, target_sha),
    )

    accepted = gate.evaluate_committed_candidate(
        contract=contract,
        candidate_commit=candidate_commit,
        candidate_tree_sha=candidate_tree,
        expected_policy_revision_hash=policy_hash,
    )
    tampered = gate.evaluate_committed_candidate(
        contract=contract,
        candidate_commit=candidate_commit,
        candidate_tree_sha="0" * 40,
        expected_policy_revision_hash=policy_hash,
    )

    assert accepted.passed is True
    assert accepted.blocking_reasons == ()
    assert tampered.passed is False
    assert "integration_candidate_identity_mismatch" in tampered.blocking_reasons


def test_committed_candidate_recheck_rejects_rename_even_when_both_paths_are_allowed(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=True)
    contract = _contract(
        controller_root,
        target_root,
        task_id="committed-rename-recheck",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "renamed.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    _git(controller_root, "mv", "bounded.txt", "renamed.txt")
    _git(controller_root, "commit", "-m", "rename candidate")
    candidate_commit = _git(controller_root, "rev-parse", "HEAD")
    gate = RepositoryContractGate(WorktreeManager(str(target_root)))
    policy_hash = gate._policy_revision_hash(
        target_sha,
        gate._policy_input_hashes(controller_root, target_sha),
    )

    receipt = gate.evaluate_committed_candidate(
        contract=contract,
        candidate_commit=candidate_commit,
        candidate_tree_sha=_git(controller_root, "rev-parse", "HEAD^{tree}"),
        expected_policy_revision_hash=policy_hash,
    )

    assert receipt.passed is False
    assert (
        "integration_candidate_rename_copy_forbidden:bounded.txt->renamed.txt"
        in receipt.blocking_reasons
    )


def test_new_persistent_markdown_outside_tasks_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-md-frozen",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "docs/reports/new_report.md"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "docs/reports").mkdir(parents=True)
    (target / "docs/reports/new_report.md").write_text("# New Report\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_persistent_markdown_frozen:docs/reports/new_report.md" in receipt.blocking_reasons
    findings = [f for f in receipt.findings if f.kind == "new_persistent_markdown_frozen"]
    assert len(findings) == 1
    assert findings[0].severity == "blocking"
    assert findings[0].path == "docs/reports/new_report.md"


def test_new_policy_markdown_cannot_bypass_freeze(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-policy-md-frozen",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "AGENTS.md"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "AGENTS.md").write_text("# New AGENTS\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_persistent_markdown_frozen:AGENTS.md" in receipt.blocking_reasons


def test_new_markdown_under_tasks_allowed_if_in_allowed_files(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-md-tasks-allowed",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "tasks/my-campaign/00-task.md"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "tasks/my-campaign").mkdir(parents=True)
    (target / "tasks/my-campaign/00-task.md").write_text("# Task\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is True
    assert not [f for f in receipt.findings if f.kind == "new_persistent_markdown_frozen"]


def test_new_markdown_under_tasks_blocked_if_not_in_allowed_files(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-md-tasks-unallowed",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "tasks/my-campaign").mkdir(parents=True)
    (target / "tasks/my-campaign/00-unallowed.md").write_text("# Unallowed\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_persistent_markdown_frozen:tasks/my-campaign/00-unallowed.md" in receipt.blocking_reasons


def test_existing_non_policy_markdown_update_permitted(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "verifier@example.test")
    _git(controller_root, "config", "user.name", "Verifier")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    (controller_root / "docs").mkdir()
    (controller_root / "docs/README.md").write_text("# Base Readme\n", encoding="utf-8")
    _git(controller_root, "add", ".")
    _git(controller_root, "commit", "-m", "base with docs/README.md")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")

    contract = _contract(
        controller_root,
        target_root,
        task_id="update-existing-non-policy-md",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "docs/README.md"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "docs/README.md").write_text("# Updated Readme\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is True
    assert not [f for f in receipt.findings if f.kind == "new_persistent_markdown_frozen"]


def test_new_production_python_module_denoting_agent_router_wrapper_is_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-python-module-frozen",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "nexus/core/custom_agent.py"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "nexus/core").mkdir(parents=True)
    (target / "nexus/core/custom_agent.py").write_text("x = 1\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_component_module_frozen:nexus/core/custom_agent.py" in receipt.blocking_reasons


def test_new_ast_class_ending_agent_router_wrapper_is_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="new-ast-class-frozen",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "nexus/core/helper.py"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "nexus/core").mkdir(parents=True)
    (target / "nexus/core/helper.py").write_text(
        "class NewWrapper:\n    pass\n",
        encoding="utf-8",
    )
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is False
    assert "new_component_class_frozen:nexus/core/helper.py:NewWrapper" in receipt.blocking_reasons


def test_existing_ast_class_modification_permitted(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "verifier@example.test")
    _git(controller_root, "config", "user.name", "Verifier")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    (controller_root / "nexus/core").mkdir(parents=True)
    (controller_root / "nexus/core/router.py").write_text(
        "class CoreRouter:\n    def run(self):\n        pass\n",
        encoding="utf-8",
    )
    _git(controller_root, "add", ".")
    _git(controller_root, "commit", "-m", "base with router")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")

    contract = _contract(
        controller_root,
        target_root,
        task_id="modify-existing-ast-class",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["bounded.txt", "nexus/core/router.py"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    (target / "nexus/core/router.py").write_text(
        "class CoreRouter:\n    def run(self):\n        return True\n",
        encoding="utf-8",
    )
    current = controller.collect_candidate(contract, lease)

    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract=contract,
        lease=lease,
        candidate=current,
        current=current,
    )

    assert receipt.passed is True
    assert not [f for f in receipt.findings if f.kind in ("new_component_class_frozen", "new_component_module_frozen")]


def test_effective_route_module_names_are_blocked(tmp_path):
    names = ("planner", "controller", "gateway", "selector", "dispatcher")
    for name in names:
        (tmp_path / name).mkdir()
        controller_root = tmp_path / name / "controller"
        target_root = tmp_path / name / "targets"
        target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
        contract = _contract(
            controller_root, target_root, task_id=f"new-{name}", target_sha=target_sha,
            controller_sha=controller_sha, allowed_files=["bounded.txt", f"nexus/core/{name}.py"],
            verifier_commands=["python3 -c 'print(\"pass\")'"],
        )
        controller, lease = _prepare(contract, target_root)
        path = Path(lease.target_worktree, f"nexus/core/{name}.py")
        path.parent.mkdir(parents=True)
        path.write_text("x = 1\n", encoding="utf-8")
        current = controller.collect_candidate(contract, lease)
        receipt = RepositoryContractGate(controller.worktree_manager).evaluate(contract, lease, current, current)
        assert any(reason.startswith("effective_route_authority_change:") for reason in receipt.blocking_reasons)


def test_authority_change_marker_remains_pending_human_verification(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root, target_root, task_id="marked-authority-change", target_sha=target_sha,
        controller_sha=controller_sha, allowed_files=["bounded.txt", "nexus/core/planner.py"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    ).model_copy(update={"protected_contracts": ["repository-authority-change.v1"]})
    controller, lease = _prepare(contract, target_root)
    path = Path(lease.target_worktree, "nexus/core/planner.py")
    path.parent.mkdir(parents=True)
    path.write_text("x = 1\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)
    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(contract, lease, current, current)
    assert receipt.passed is True
    assert receipt.mode == "enforced"
    assert receipt.authority_change_required is True
    assert receipt.authority_findings_sha256
    assert any(f.severity == "approval_required" for f in receipt.findings)
    assert any(f.kind == "authority_change_pending_human_verification" for f in receipt.findings)


def test_committed_authority_change_requires_exact_approval_and_replay_is_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root, target_root, task_id="committed-authority", target_sha=target_sha,
        controller_sha=controller_sha, allowed_files=["bounded.txt", "nexus/core/planner.py"], verifier_commands=[]
    ).model_copy(update={"protected_contracts": ["repository-authority-change.v1"]})
    controller, lease = _prepare(contract, target_root)
    target = Path(lease.target_worktree)
    planner = target / "nexus/core/planner.py"
    planner.parent.mkdir(parents=True)
    planner.write_text("x = 1\n", encoding="utf-8")
    _git(target, "add", "nexus/core/planner.py")
    _git(target, "commit", "-m", "authority change")
    candidate_commit = _git(target, "rev-parse", "HEAD")
    candidate_tree = _git(target, "rev-parse", "HEAD^{tree}")
    gate = RepositoryContractGate(controller.worktree_manager)
    policy_inputs = gate._policy_input_hashes(controller_root, contract.target_base_revision)
    policy_hash = gate._policy_revision_hash(contract.target_base_revision, policy_inputs)
    initial = gate.evaluate_committed_candidate(contract=contract, candidate_commit=candidate_commit, candidate_tree_sha=candidate_tree, expected_policy_revision_hash=policy_hash, task_id=contract.task_id, attempt_id="attempt-1")
    assert not initial.passed
    assert "architecture_approval_binding_mismatch" in initial.blocking_reasons
    now = datetime.now(timezone.utc)
    approval = {"schema":"nexus.architecture_approval.v1","approval_id":"arch","approved_by":"owner","issued_at":(now - timedelta(minutes=2)).isoformat(),"expires_at":(now - timedelta(seconds=30)).isoformat(),"approval_scope":"ALLOW_ACTION_ONCE","bound_task_id":contract.task_id,"bound_attempt_id":"attempt-1","candidate_commit_sha":candidate_commit,"candidate_tree_sha":candidate_tree,"authority_findings_sha256":initial.authority_findings_sha256,"consumed_at":(now - timedelta(minutes=1)).isoformat()}
    accepted = gate.evaluate_committed_candidate(contract=contract, candidate_commit=candidate_commit, candidate_tree_sha=candidate_tree, expected_policy_revision_hash=policy_hash, architecture_approval=approval, task_id=contract.task_id, attempt_id="attempt-1")
    assert accepted.passed is True
    replay = gate.evaluate_committed_candidate(contract=contract, candidate_commit=candidate_commit, candidate_tree_sha=candidate_tree, expected_policy_revision_hash=policy_hash, architecture_approval=approval, task_id=contract.task_id, attempt_id="attempt-2")
    assert replay.passed is False
    assert "architecture_approval_binding_mismatch" in replay.blocking_reasons
    tree_replay = gate.evaluate_committed_candidate(contract=contract, candidate_commit=candidate_commit, candidate_tree_sha="f" * 40, expected_policy_revision_hash=policy_hash, architecture_approval=approval, task_id=contract.task_id, attempt_id="attempt-1")
    assert tree_replay.passed is False
    assert "integration_candidate_identity_mismatch" in tree_replay.blocking_reasons
    out_of_scope_contract = contract.model_copy(update={"allowed_files": ["bounded.txt"]})
    out_of_scope = gate.evaluate_committed_candidate(contract=out_of_scope_contract, candidate_commit=candidate_commit, candidate_tree_sha=candidate_tree, expected_policy_revision_hash=policy_hash, architecture_approval=approval, task_id=contract.task_id, attempt_id="attempt-1")
    assert out_of_scope.passed is False
    assert any(reason.startswith("integration_candidate_out_of_scope:") for reason in out_of_scope.blocking_reasons)


def test_identity_recheck_blocks_candidate_head_drift(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root, target_root, task_id="identity-recheck", target_sha=target_sha,
        controller_sha=controller_sha, allowed_files=["bounded.txt"], verifier_commands=[],
    )
    controller, lease = _prepare(contract, target_root)
    current = controller.collect_candidate(contract, lease)
    drifted = replace(current, target_head="1" * 40)
    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(contract, lease, drifted, current)
    assert receipt.passed is False
    assert "integration_identity_recheck:target_head" in receipt.blocking_reasons


def test_existing_authority_file_route_branch_is_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "repository-contract@example.test")
    _git(controller_root, "config", "user.name", "Repository Contract")
    path = controller_root / "nexus/orchestrator/controller.py"
    path.parent.mkdir(parents=True)
    path.write_text("def run(value):\n    return value\n", encoding="utf-8")
    _git(controller_root, "add", ".")
    _git(controller_root, "commit", "-m", "base")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")
    contract = _contract(
        controller_root, target_root, task_id="existing-route-branch", target_sha=target_sha,
        controller_sha=controller_sha, allowed_files=["nexus/orchestrator/controller.py"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    Path(lease.target_worktree, "nexus/orchestrator/controller.py").write_text(
        "def run(value, fallback=False):\n    if fallback:\n        return value\n    return value\n", encoding="utf-8"
    )
    current = controller.collect_candidate(contract, lease)
    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(contract, lease, current, current)
    assert any(reason.startswith("effective_route_authority_change:") for reason in receipt.blocking_reasons)


def test_new_execution_topology_config_is_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root, target_root, task_id="new-execution-topology", target_sha=target_sha,
        controller_sha=controller_sha, allowed_files=["bounded.txt", "nexus/config/execution_topology.yaml"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    controller, lease = _prepare(contract, target_root)
    path = Path(lease.target_worktree, "nexus/config/execution_topology.yaml")
    path.parent.mkdir(parents=True)
    path.write_text("execution_lane: alternate\nRouteMode: fallback\n", encoding="utf-8")
    current = controller.collect_candidate(contract, lease)
    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(contract, lease, current, current)
    assert any(reason.startswith("effective_route_authority_change:") for reason in receipt.blocking_reasons)


def test_tampered_topology_bypass_remains_blocked(tmp_path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    target_sha, controller_sha = _init_repo(controller_root, with_policy_inputs=False)
    contract = _contract(
        controller_root,
        target_root,
        task_id="topology-tamper",
        target_sha=target_sha,
        controller_sha=controller_sha,
        allowed_files=["nexus/config/execution_topology.yaml"],
        verifier_commands=[],
    )
    controller, lease = _prepare(contract, target_root)
    path = Path(lease.target_worktree, "nexus/config/execution_topology.yaml")
    path.parent.mkdir(parents=True)
    path.write_text("execution_lane: alternate\nroute_authority: forged\n", encoding="utf-8")
    receipt = RepositoryContractGate(controller.worktree_manager).evaluate(
        contract,
        lease,
        controller.collect_candidate(contract, lease),
        controller.collect_candidate(contract, lease),
    )
    assert receipt.passed is False
