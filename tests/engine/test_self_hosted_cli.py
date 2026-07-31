import json
import sys
from pathlib import Path

repo_root = str(Path(__file__).resolve().parents[2])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

import pytest
from click.testing import CliRunner

from scripts.engine.nexus_cli import nexus
import scripts.engine.commands.self_hosted_actions as self_hosted_actions
from scripts.engine.commands.exception_translation import NexusCliActionError
from scripts.engine.commands.self_hosted_actions import (
    run_self_hosted_cleanup,
    run_self_hosted_workspace_converge,
    run_self_hosted_workspace_inventory,
    run_self_hosted_workspace_plan,
    run_self_hosted_workspace_slot_status,
    set_test_runner,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService


@pytest.fixture(autouse=True)
def safe_test_runner():
    def _fake_runner(contract, request, update):
        update("CANDIDATE_COMMITTED", {"candidate_commit_sha": "c" * 40})
        return {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_created": True,
        }
    set_test_runner(_fake_runner)
    yield
    set_test_runner(None)


import subprocess

def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _valid_request(tmp_path: Path, **overrides) -> dict:
    controller = tmp_path / "controller"
    if not controller.exists():
        controller.mkdir(parents=True)
        _git(controller, "init", "-b", "main")
        _git(controller, "config", "user.name", "Lifecycle Test")
        _git(controller, "config", "user.email", "lifecycle@example.test")
        (controller / "README").write_text("base\n")
        _git(controller, "add", "README")
        _git(controller, "commit", "-m", "base")
    head = _git(controller, "rev-parse", "HEAD")
    target_root = tmp_path / "targets"

    req = {
        "task_id": "test-sh-001",
        "what": "Test self hosted CLI submit",
        "why": "Validate tracer bullet for self hosted CLI",
        "controller_revision": head,
        "target_base_revision": head,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "test-sh-001"),
        "target_worktree_root": str(target_root),
        "allowed_files": "file1.py,file2.py",
        "worker": "codex",
    }
    req.update(overrides)
    return req


def test_self_hosted_submit_and_status_success(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    req = _valid_request(tmp_path)

    cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", req["task_id"],
        "--what", req["what"],
        "--why", req["why"],
        "--controller-revision", req["controller_revision"],
        "--target-base-revision", req["target_base_revision"],
        "--controller-repo-root", req["controller_repo_root"],
        "--target-repo-root", req["target_repo_root"],
        "--target-worktree-root", req["target_worktree_root"],
        "--allowed-files", req["allowed_files"],
        "--worker", req["worker"],
        "--state-dir", state_dir,
    ]
    result = runner.invoke(nexus, cmd)
    assert result.exit_code == 0, f"Submit failed: {result.output}"
    out_data = json.loads(result.output)
    assert out_data["task_id"] == "test-sh-001"
    assert out_data["status"] == "SUBMITTED"

    status_cmd = [
        "nexus", "self-hosted", "status",
        "--task-id", "test-sh-001",
        "--state-dir", state_dir,
    ]
    status_res = runner.invoke(nexus, status_cmd)
    assert status_res.exit_code == 0, f"Status failed: {status_res.output}"
    status_data = json.loads(status_res.output)
    assert status_data["task_id"] == "test-sh-001"
    assert status_data["status"] in {"SUBMITTED", "CANDIDATE_COMMITTED", "CANDIDATE_CAPTURED", "PENDING_HUMAN_APPROVAL"}


def test_self_hosted_submit_from_request_file(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    req = _valid_request(tmp_path, task_id="test-sh-file-002", allowed_files=["file1.py"])
    req_file = tmp_path / "request.json"
    req_file.write_text(json.dumps(req))

    cmd = [
        "nexus", "self-hosted", "submit",
        "--request-file", str(req_file),
        "--state-dir", state_dir,
    ]
    result = runner.invoke(nexus, cmd)
    assert result.exit_code == 0
    out_data = json.loads(result.output)
    assert out_data["task_id"] == "test-sh-file-002"


def test_self_hosted_submit_missing_required_fields_fails(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")

    cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", "test-sh-fail",
        "--state-dir", state_dir,
    ]
    result = runner.invoke(nexus, cmd)
    assert result.exit_code != 0


def test_self_hosted_submit_no_fabricated_zero_sha_fallback(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")

    cmd = [
        "nexus", "self-hosted", "submit",
        "--what", "some task",
        "--why", "some reason",
        "--controller-repo-root", str(tmp_path / "c"),
        "--target-repo-root", str(tmp_path / "t"),
        "--target-worktree-root", str(tmp_path / "w"),
        "--allowed-files", "a.py",
        "--state-dir", state_dir,
    ]
    result = runner.invoke(nexus, cmd)
    assert result.exit_code != 0


def test_self_hosted_status_nonexistent_task_fails(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")

    cmd = [
        "nexus", "self-hosted", "status",
        "--task-id", "nonexistent-task-9999",
        "--state-dir", state_dir,
    ]
    result = runner.invoke(nexus, cmd)
    assert result.exit_code != 0
    assert "not found" in result.output


def test_self_hosted_cli_subgroup_invocation(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    req = _valid_request(tmp_path, task_id="test-sh-subgroup")

    cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", req["task_id"],
        "--what", req["what"],
        "--why", req["why"],
        "--controller-revision", req["controller_revision"],
        "--target-base-revision", req["target_base_revision"],
        "--controller-repo-root", req["controller_repo_root"],
        "--target-repo-root", req["target_repo_root"],
        "--target-worktree-root", req["target_worktree_root"],
        "--allowed-files", req["allowed_files"],
        "--worker", req["worker"],
        "--state-dir", state_dir,
    ]
    res1 = runner.invoke(nexus, cmd)
    assert res1.exit_code == 0

    res2 = runner.invoke(nexus, ["nexus", "self-hosted", "status", "--task-id", "test-sh-subgroup", "--state-dir", state_dir])
    assert res2.exit_code == 0


def test_self_hosted_wait_success(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    req = _valid_request(tmp_path, task_id="test-sh-wait-001")

    submit_cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", req["task_id"],
        "--what", req["what"],
        "--why", req["why"],
        "--controller-revision", req["controller_revision"],
        "--target-base-revision", req["target_base_revision"],
        "--controller-repo-root", req["controller_repo_root"],
        "--target-repo-root", req["target_repo_root"],
        "--target-worktree-root", req["target_worktree_root"],
        "--allowed-files", req["allowed_files"],
        "--worker", req["worker"],
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, submit_cmd)

    wait_cmd = [
        "nexus", "self-hosted", "wait",
        "--task-id", "test-sh-wait-001",
        "--timeout", "1.0",
        "--poll-interval", "0.05",
        "--state-dir", state_dir,
    ]
    res = runner.invoke(nexus, wait_cmd)
    assert res.exit_code == 0, f"Wait failed: {res.output}"
    out_data = json.loads(res.output)
    assert out_data["task_id"] == "test-sh-wait-001"
    assert "wait" in out_data or "task_action" in out_data


def test_self_hosted_wait_nonexistent_task_fails(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")

    wait_cmd = [
        "nexus", "self-hosted", "wait",
        "--task-id", "nonexistent-wait-9999",
        "--state-dir", state_dir,
    ]
    res = runner.invoke(nexus, wait_cmd)
    assert res.exit_code != 0
    assert "not found" in res.output


def test_self_hosted_list_actionable_empty_and_populated(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")

    # Empty list-actionable
    list_cmd = [
        "nexus", "self-hosted", "list-actionable",
        "--state-dir", state_dir,
    ]
    res_empty = runner.invoke(nexus, list_cmd)
    assert res_empty.exit_code == 0, f"List actionable failed: {res_empty.output}"
    empty_data = json.loads(res_empty.output)
    assert empty_data["schema"] == "nexus.self_hosted_actionable_tasks.v1"
    assert empty_data["actionable_count"] == 0
    assert empty_data["tasks"] == []

    # Submit a task so there's an actionable item
    req = _valid_request(tmp_path, task_id="test-sh-actionable-001")
    submit_cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", req["task_id"],
        "--what", req["what"],
        "--why", req["why"],
        "--controller-revision", req["controller_revision"],
        "--target-base-revision", req["target_base_revision"],
        "--controller-repo-root", req["controller_repo_root"],
        "--target-repo-root", req["target_repo_root"],
        "--target-worktree-root", req["target_worktree_root"],
        "--allowed-files", req["allowed_files"],
        "--worker", req["worker"],
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, submit_cmd)

    res_pop = runner.invoke(nexus, list_cmd)
    assert res_pop.exit_code == 0
    pop_data = json.loads(res_pop.output)
    assert pop_data["actionable_count"] >= 1
    assert any(t["task_id"] == "test-sh-actionable-001" for t in pop_data["tasks"])


def test_self_hosted_wait_and_list_actionable_subprocess(tmp_path: Path):
    import sys
    state_dir = str(tmp_path / "state")
    task_id = "test-sh-subproc-001"

    # Seed a legal quiescent task state directly via SelfHostedTaskService
    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    service._write_state(task_id, {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": task_id,
        "status": "CANDIDATE_CAPTURED",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "target_worktree": str(tmp_path / "targets" / task_id),
        "worker_pid": None,
    })

    # Subprocess wait
    wait_cmd = [
        sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "wait",
        "--task-id", task_id,
        "--timeout", "1.0",
        "--poll-interval", "0.05",
        "--state-dir", state_dir,
    ]
    wait_res = subprocess.run(wait_cmd, capture_output=True, text=True)
    assert wait_res.returncode == 0, f"Subprocess wait failed: {wait_res.stderr}"
    wait_data = json.loads(wait_res.stdout)
    assert wait_data["task_id"] == task_id
    assert wait_data["status"] == "CANDIDATE_CAPTURED"
    assert wait_data["promotion_status"] == "PENDING_HUMAN_APPROVAL"

    # Subprocess list-actionable
    list_cmd = [
        sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "list-actionable",
        "--state-dir", state_dir,
    ]
    list_res = subprocess.run(list_cmd, capture_output=True, text=True)
    assert list_res.returncode == 0, f"Subprocess list-actionable failed: {list_res.stderr}"
    list_data = json.loads(list_res.stdout)
    assert list_data["schema"] == "nexus.self_hosted_actionable_tasks.v1"
    assert list_data["actionable_count"] >= 1
    assert any(t["task_id"] == task_id for t in list_data["tasks"])


def test_self_hosted_approve_exact_binding_and_mismatch(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    req = _valid_request(tmp_path, task_id="test-sh-approve-001")

    submit_cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", req["task_id"],
        "--what", req["what"],
        "--why", req["why"],
        "--controller-revision", req["controller_revision"],
        "--target-base-revision", req["target_base_revision"],
        "--controller-repo-root", req["controller_repo_root"],
        "--target-repo-root", req["target_repo_root"],
        "--target-worktree-root", req["target_worktree_root"],
        "--allowed-files", req["allowed_files"],
        "--worker", req["worker"],
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, submit_cmd)

    wait_cmd = [
        "nexus", "self-hosted", "wait",
        "--task-id", req["task_id"],
        "--timeout", "2.0",
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, wait_cmd)

    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    def _mutate_approve(s):
        s["promotion_status"] = "PENDING_HUMAN_APPROVAL"
        s["promotion_packet"] = {
            "candidate_commit_sha": "a" * 40,
            "candidate_tree_sha": "b" * 40,
            "candidate_state_hash": "c" * 64,
            "verified_receipt_hash": "d" * 64,
        }
    service._mutate_state(req["task_id"], _mutate_approve)

    approve_mismatch_cmd = [
        "nexus", "self-hosted", "approve",
        "--task-id", "test-sh-approve-001",
        "--candidate-commit-sha", "x" * 40,
        "--candidate-tree-sha", "b" * 40,
        "--candidate-state-hash", "c" * 64,
        "--verified-receipt-hash", "d" * 64,
        "--state-dir", state_dir,
    ]
    res_mismatch = runner.invoke(nexus, approve_mismatch_cmd)
    assert res_mismatch.exit_code == 0
    mismatch_data = json.loads(res_mismatch.output)
    assert mismatch_data["promotion_status"] == "APPROVAL_INVALIDATED"
    assert mismatch_data["approved_binding"] is None

    approve_cmd = [
        "nexus", "self-hosted", "approve",
        "--task-id", "test-sh-approve-001",
        "--candidate-commit-sha", "a" * 40,
        "--candidate-tree-sha", "b" * 40,
        "--candidate-state-hash", "c" * 64,
        "--verified-receipt-hash", "d" * 64,
        "--state-dir", state_dir,
    ]
    res = runner.invoke(nexus, approve_cmd)
    assert res.exit_code == 0
    out_data = json.loads(res.output)
    assert out_data["promotion_status"] == "APPROVED"
    assert out_data["approved_binding"]["candidate_commit_sha"] == "a" * 40


def test_self_hosted_integrate_requires_approved(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    req = _valid_request(tmp_path, task_id="test-sh-integrate-001")

    submit_cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", req["task_id"],
        "--what", req["what"],
        "--why", req["why"],
        "--controller-revision", req["controller_revision"],
        "--target-base-revision", req["target_base_revision"],
        "--controller-repo-root", req["controller_repo_root"],
        "--target-repo-root", req["target_repo_root"],
        "--target-worktree-root", req["target_worktree_root"],
        "--allowed-files", req["allowed_files"],
        "--worker", req["worker"],
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, submit_cmd)

    wait_cmd = [
        "nexus", "self-hosted", "wait",
        "--task-id", req["task_id"],
        "--timeout", "2.0",
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, wait_cmd)

    integrate_cmd = [
        "nexus", "self-hosted", "integrate",
        "--task-id", "test-sh-integrate-001",
        "--state-dir", state_dir,
    ]
    res_before = runner.invoke(nexus, integrate_cmd)
    assert res_before.exit_code != 0
    assert "exact approved binding is required" in res_before.output


def test_self_hosted_dispose_candidate(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    req = _valid_request(tmp_path, task_id="test-sh-dispose-001")

    submit_cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", req["task_id"],
        "--what", req["what"],
        "--why", req["why"],
        "--controller-revision", req["controller_revision"],
        "--target-base-revision", req["target_base_revision"],
        "--controller-repo-root", req["controller_repo_root"],
        "--target-repo-root", req["target_repo_root"],
        "--target-worktree-root", req["target_worktree_root"],
        "--allowed-files", req["allowed_files"],
        "--worker", req["worker"],
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, submit_cmd)

    wait_cmd = [
        "nexus", "self-hosted", "wait",
        "--task-id", req["task_id"],
        "--timeout", "2.0",
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, wait_cmd)

    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    service._mutate_state(req["task_id"], lambda s: s.update({"promotion_status": "PENDING_HUMAN_APPROVAL"}))

    dispose_cmd = [
        "nexus", "self-hosted", "dispose",
        "--task-id", "test-sh-dispose-001",
        "--disposition", "REJECTED",
        "--state-dir", state_dir,
    ]
    res = runner.invoke(nexus, dispose_cmd)
    assert res.exit_code == 0
    out_data = json.loads(res.output)
    assert out_data["promotion_status"] == "REJECTED"
    assert out_data["status"] == "REJECTED"


def test_self_hosted_cancel_task(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    req = _valid_request(tmp_path, task_id="test-sh-cancel-001")

    submit_cmd = [
        "nexus", "self-hosted", "submit",
        "--task-id", req["task_id"],
        "--what", req["what"],
        "--why", req["why"],
        "--controller-revision", req["controller_revision"],
        "--target-base-revision", req["target_base_revision"],
        "--controller-repo-root", req["controller_repo_root"],
        "--target-repo-root", req["target_repo_root"],
        "--target-worktree-root", req["target_worktree_root"],
        "--allowed-files", req["allowed_files"],
        "--worker", req["worker"],
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, submit_cmd)

    wait_cmd = [
        "nexus", "self-hosted", "wait",
        "--task-id", req["task_id"],
        "--timeout", "2.0",
        "--state-dir", state_dir,
    ]
    runner.invoke(nexus, wait_cmd)

    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    service._mutate_state(req["task_id"], lambda s: s.update({"worker_pid": None}))

    cancel_cmd = [
        "nexus", "self-hosted", "cancel",
        "--task-id", "test-sh-cancel-001",
        "--state-dir", state_dir,
    ]
    res = runner.invoke(nexus, cancel_cmd)
    assert res.exit_code == 0
    out_data = json.loads(res.output)
    assert out_data["status"] == "CANCELLED"

    cancel_bad = [
        "nexus", "self-hosted", "cancel",
        "--task-id", "nonexistent-cancel-999",
        "--state-dir", state_dir,
    ]
    res_bad = runner.invoke(nexus, cancel_bad)
    assert res_bad.exit_code != 0


def test_self_hosted_close_without_candidate_cmd(tmp_path: Path):
    runner = CliRunner()
    state_dir = str(tmp_path / "state")
    task_id = "test-sh-close-001"

    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    service._write_state(task_id, {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": task_id,
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(tmp_path / "targets" / task_id),
        "worker_pid": None,
    })

    close_cmd = [
        "nexus", "self-hosted", "close-without-candidate",
        "--task-id", task_id,
        "--superseded-by", "ref-evidence-999",
        "--state-dir", state_dir,
    ]
    res = runner.invoke(nexus, close_cmd)
    assert res.exit_code == 0, f"close-without-candidate failed: {res.output}"
    out_data = json.loads(res.output)
    assert out_data["status"] == "SUPERSEDED"
    assert out_data["superseded_by"] == "ref-evidence-999"
    assert out_data["promotion_status"] == "NOT_CREATED"


@pytest.mark.parametrize("apply", [False, True])
def test_run_self_hosted_cleanup_forwards_exact_task_and_dry_run(apply: bool):
    calls = []
    expected = {"schema": "cleanup-result", "dry_run": not apply}

    class FakeService:
        def cleanup_tasks(self, **kwargs):
            calls.append(kwargs)
            return expected

    result = run_self_hosted_cleanup(
        task_id="exact-cleanup-task-001",
        apply=apply,
        state_dir="/tmp/unused-state",
        service=FakeService(),
    )

    assert result is expected
    assert calls == [{"task_id": "exact-cleanup-task-001", "dry_run": not apply}]


def test_run_self_hosted_cleanup_rejects_blank_task_id():
    with pytest.raises(NexusCliActionError, match="task_id is required"):
        run_self_hosted_cleanup(" ", service=object())


def test_self_hosted_cleanup_cli_registered_json_and_apply(monkeypatch):
    calls = []
    expected = {"schema": "cleanup-result", "decisions": []}

    class FakeService:
        def cleanup_tasks(self, **kwargs):
            calls.append(kwargs)
            return {**expected, "dry_run": kwargs["dry_run"]}

    service = FakeService()
    monkeypatch.setattr(self_hosted_actions, "get_self_hosted_service", lambda **_: service)
    runner = CliRunner()

    dry_run = runner.invoke(nexus, ["nexus", "self-hosted", "cleanup", "--task-id", "cleanup-cli-001"])
    assert dry_run.exit_code == 0, dry_run.output
    assert json.loads(dry_run.output) == {**expected, "dry_run": True}

    applied = runner.invoke(nexus, ["nexus", "self-hosted", "cleanup", "--task-id", "cleanup-cli-001", "--apply"])
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output) == {**expected, "dry_run": False}
    assert calls == [
        {"task_id": "cleanup-cli-001", "dry_run": True},
        {"task_id": "cleanup-cli-001", "dry_run": False},
    ]


def test_self_hosted_cleanup_requires_one_task_id():
    result = CliRunner().invoke(nexus, ["nexus", "self-hosted", "cleanup"])

    assert result.exit_code != 0
    assert "Missing option '--task-id'" in result.output


def test_workspace_action_wrappers_forward_exact_read_and_apply_contract():
    calls = []

    class FakeService:
        def workspace_inventory(self, **kwargs):
            calls.append(("inventory", kwargs))
            return {"schema": "inventory"}

        def workspace_convergence_plan(self, **kwargs):
            calls.append(("plan", kwargs))
            return {"schema": "plan"}

        def workspace_slot_status(self, **kwargs):
            calls.append(("slot", kwargs))
            return {"schema": "slot"}

        def apply_workspace_convergence(self, **kwargs):
            calls.append(("converge", kwargs))
            return {"schema": "converge", "applied": kwargs["apply"]}

    service = FakeService()
    assert run_self_hosted_workspace_inventory("/controller", service=service) == {"schema": "inventory"}
    assert run_self_hosted_workspace_plan("/controller", "a" * 40, service=service) == {"schema": "plan"}
    assert run_self_hosted_workspace_slot_status("campaign", 2, "/controller", service=service) == {"schema": "slot"}
    assert run_self_hosted_workspace_converge("a" * 40, "b" * 64, apply=False, service=service) == {"schema": "converge", "applied": False}
    assert calls == [
        ("inventory", {"controller_root": "/controller"}),
        ("plan", {"controller_root": "/controller", "expected_controller_revision": "a" * 40}),
        ("slot", {"campaign_id": "campaign", "slot_index": 2, "controller_root": "/controller"}),
        ("converge", {
            "controller_root": None,
            "expected_controller_revision": "a" * 40,
            "expected_plan_hash": "b" * 64,
            "apply": False,
        }),
    ]


def test_workspace_cli_surfaces_are_registered_and_dry_run_first(monkeypatch):
    class FakeService:
        def workspace_inventory(self, **kwargs):
            return {"schema": "inventory", "controller_root": kwargs.get("controller_root")}

        def workspace_convergence_plan(self, **kwargs):
            return {"schema": "plan", "controller_revision": kwargs.get("expected_controller_revision")}

        def workspace_slot_status(self, **kwargs):
            return {"schema": "slot", "status": "READY", "slot_index": kwargs.get("slot_index")}

        def apply_workspace_convergence(self, **kwargs):
            return {"schema": "converge", "applied": kwargs["apply"]}

    monkeypatch.setattr(self_hosted_actions, "get_self_hosted_service", lambda **_: FakeService())
    runner = CliRunner()

    inventory = runner.invoke(nexus, [
        "nexus", "self-hosted", "workspace-inventory", "--controller-root", "/controller",
    ])
    assert inventory.exit_code == 0, inventory.output
    assert json.loads(inventory.output)["schema"] == "inventory"

    plan = runner.invoke(nexus, [
        "nexus", "self-hosted", "workspace-plan", "--expected-controller-revision", "a" * 40,
    ])
    assert plan.exit_code == 0, plan.output
    assert json.loads(plan.output)["schema"] == "plan"

    slot = runner.invoke(nexus, [
        "nexus", "self-hosted", "workspace-slot-status", "--campaign-id", "campaign", "--slot-index", "3",
    ])
    assert slot.exit_code == 0, slot.output
    assert json.loads(slot.output)["slot_index"] == 3

    converge = runner.invoke(nexus, [
        "nexus", "self-hosted", "workspace-converge",
        "--expected-controller-revision", "a" * 40,
        "--expected-plan-hash", "b" * 64,
    ])
    assert converge.exit_code == 0, converge.output
    assert json.loads(converge.output)["applied"] is False


def test_self_hosted_cleanup_translates_service_error(monkeypatch):
    class BrokenService:
        def cleanup_tasks(self, **kwargs):
            raise RuntimeError("cleanup blocked by governed contract")

    monkeypatch.setattr(self_hosted_actions, "get_self_hosted_service", lambda **_: BrokenService())
    result = CliRunner().invoke(
        nexus,
        ["nexus", "self-hosted", "cleanup", "--task-id", "cleanup-error-001"],
    )

    assert result.exit_code == 1
    assert "cleanup blocked by governed contract" in result.output


def test_self_hosted_cleanup_subprocess_json_and_explicit_apply(tmp_path: Path):
    state_dir = str(tmp_path / "state")
    task_id = "cleanup-subprocess-001"
    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    service._write_state(task_id, {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": task_id,
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(tmp_path / "targets" / task_id),
        "worker_pid": None,
    })

    command = [
        sys.executable, "-m", "scripts.engine.nexus_cli", "nexus", "self-hosted", "cleanup",
        "--task-id", task_id, "--state-dir", state_dir,
    ]
    dry_run = subprocess.run(command, capture_output=True, text=True)
    assert dry_run.returncode == 0, dry_run.stderr
    assert json.loads(dry_run.stdout)["dry_run"] is True

    applied = subprocess.run(command + ["--apply"], capture_output=True, text=True)
    assert applied.returncode == 0, applied.stderr
    applied_data = json.loads(applied.stdout)
    assert applied_data["dry_run"] is False
    assert applied_data["decisions"][0]["task_id"] == task_id


def test_self_hosted_recover_verified_uncommitted_cli_command(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(tmp_path / "targets"))
    state_dir = str(tmp_path / "state")
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    task_id = "recover-cli-001"
    req = _valid_request(tmp_path, task_id=task_id, allowed_files=["README"], target_repo_root=str(tmp_path / "targets" / task_id), target_worktree_root=str(tmp_path / "targets"))
    contract = svc.build_contract(req)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt

    wm = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = wm.create_lease(contract)
    (Path(lease.target_worktree) / "README").write_text("modified content for recovery\n")
    current = wm.capture_candidate(contract, lease)

    receipt = VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt/v1",
        task_id=task_id,
        contract_hash=contract.contract_hash,
        lease_id=lease.lease_id,
        candidate_state_hash=current.candidate_state_hash,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=True,
        verified=True,
        candidate_commit_allowed=True,
        public_claim_allowed=False,
        production_ready=False,
        failure_reasons=[],
        verifier_evidence=(),
        candidate_commit_created=False,
        merge_performed=False,
    )
    svc._write_state(contract.task_id, {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "attempt_id": "a" * 32,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "candidate_state_hash": current.candidate_state_hash,
        "verified_receipt": receipt.__dict__,
        "lease": lease.__dict__,
        "contract": contract.model_dump(mode="json"),
        "request": req,
        "execution": {"outcome": "EXECUTION_COMPLETED"},
        "attempt_resolution": {"verdict": "PROVEN"},
    })

    runner = CliRunner()
    result = runner.invoke(
        nexus,
        [
            "self-hosted", "recover-verified-uncommitted",
            "--task-id", contract.task_id,
            "--state-dir", state_dir,
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "PENDING_HUMAN_APPROVAL"
    assert data["promotion_status"] == "PENDING_HUMAN_APPROVAL"


def test_self_hosted_recover_verified_uncommitted_fail_closed_non_verified(tmp_path: Path):
    state_dir = str(tmp_path / "state")
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    for status in ["SUBMITTED", "WORKER_RUNNING", "PENDING_HUMAN_APPROVAL", "APPROVED", "INTEGRATED"]:
        task_id = f"non-verified-{status.lower()}"
        svc._write_state(task_id, {
            "task_id": task_id,
            "status": status,
            "promotion_status": status,
        })
        runner = CliRunner()
        result = runner.invoke(
            nexus,
            [
                "self-hosted", "recover-verified-uncommitted",
                "--task-id", task_id,
                "--state-dir", state_dir,
            ],
        )
        assert result.exit_code == 1
        assert "status must be RETAINED_FOR_REVIEW or FINAL_BLOCK" in result.output
