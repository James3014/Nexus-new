import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops.nexus_chatgpt_delivery import (
    DEFAULT_INTEGRATION_BRANCH,
    action_command_for_task,
    build_request,
    connector_tool_policy,
    run_delivery_cutover,
    stable_task_id,
)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "controller"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "ChatGPT Delivery Test")
    _git(repo, "config", "user.email", "chatgpt-delivery@example.test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    return repo


def _actionable_task(status: str = "PENDING_HUMAN_APPROVAL") -> dict:
    return {
        "task_id": "chatgpt-cutover",
        "status": status,
        "promotion_status": status,
        "task_action": {
            "task_id": "chatgpt-cutover",
            "action_state": "ACTION_REQUIRED",
            "attention_required": True,
            "next_action": "approve_candidate",
            "recommended_tool": "nexus_self_hosted_approve_promotion",
            "candidate": {
                "candidate_commit_sha": "a" * 40,
                "candidate_tree_sha": "b" * 40,
                "candidate_state_hash": "c" * 64,
                "verified_receipt_hash": "d" * 64,
            },
        },
    }


class FakeSelfHostedService:
    def __init__(self, actionable_after: dict | None = None):
        self.submitted_requests: list[dict] = []
        self.waited: list[str] = []
        self.list_calls = 0
        self.actionable_after = actionable_after or {"schema": "nexus.self_hosted_actionable_tasks.v1", "actionable_count": 0, "tasks": []}

    def list_actionable_tasks(self) -> dict:
        self.list_calls += 1
        if self.list_calls == 1:
            return {"schema": "nexus.self_hosted_actionable_tasks.v1", "actionable_count": 0, "tasks": []}
        return self.actionable_after

    def submit_task(self, request: dict) -> dict:
        self.submitted_requests.append(dict(request))
        return {
            "task_id": request["task_id"],
            "status": "SUBMITTED",
            "task_action": {
                "task_id": request["task_id"],
                "action_state": "IN_PROGRESS",
                "recommended_tool": "nexus_self_hosted_wait_task",
            },
        }

    def wait_task(self, task_id: str, **kwargs) -> dict:
        self.waited.append(task_id)
        return {
            "task_id": task_id,
            "status": "APPROVED",
            "promotion_status": "APPROVED",
            "task_action": {
                "task_id": task_id,
                "action_state": "ACTION_REQUIRED",
                "next_action": "integrate_approved_candidate",
                "recommended_tool": "nexus_self_hosted_integrate_approved",
            },
        }


class ExistingActionableService(FakeSelfHostedService):
    def list_actionable_tasks(self) -> dict:
        self.list_calls += 1
        return {"schema": "nexus.self_hosted_actionable_tasks.v1", "actionable_count": 1, "tasks": [_actionable_task()]}


def test_connector_policy_blocks_direct_edit_write_delivery():
    assert connector_tool_policy("nexus.edit") == {
        "schema": "nexus.chatgpt_connector_tool_policy.v1",
        "tool": "nexus.edit",
        "allowed": False,
        "required_tool": "nexus.bash",
        "reason": "direct_edit_write_delivery_blocked_use_self_hosted_lifecycle",
    }
    assert connector_tool_policy("nexus.bash")["allowed"] is True


def test_stable_task_id_rejects_version_suffix_retry_pattern():
    with pytest.raises(Exception, match="attempt_id"):
        stable_task_id("Do work", ["a.py"], explicit="do-work-v2")


def test_build_request_uses_managed_target_root_and_exact_head(tmp_path: Path):
    repo = _repo(tmp_path)
    target_root = tmp_path / "self-hosted-lifecycle-targets"
    request = build_request(
        what="Cut over ChatGPT delivery",
        why="Prevent direct connector writes",
        task_id="chatgpt-delivery-cutover",
        controller_repo_root=repo,
        target_worktree_root=target_root,
        allowed_files=["scripts/ops/nexus_chatgpt_delivery.py"],
        verifier_commands=["git diff --check"],
    )
    head = _git(repo, "rev-parse", "HEAD")
    assert request["controller_revision"] == head
    assert request["target_base_revision"] == head
    assert request["controller_repo_root"] == str(repo.resolve())
    assert request["target_worktree_root"] == str(target_root.resolve())
    assert request["target_repo_root"] == str((target_root / "chatgpt-delivery-cutover").resolve())
    assert request["direct_delivery_allowed"] is False
    assert request["delivery_channel"] == "chatgpt_connector_nexus_bash"


def test_launch_surfaces_existing_approval_before_new_submission(tmp_path: Path):
    repo = _repo(tmp_path)
    service = ExistingActionableService()
    payload = run_delivery_cutover(
        what="Cut over ChatGPT delivery",
        why="Prevent direct connector writes",
        task_id="chatgpt-delivery-cutover",
        controller_repo_root=repo,
        target_worktree_root=tmp_path / "targets",
        allowed_files=["scripts/ops/nexus_chatgpt_delivery.py"],
        verifier_commands=["git diff --check"],
        service=service,
    )

    assert payload["status"] == "ACTION_REQUIRED"
    assert payload["submission_blocked"] is True
    assert payload["connector_tool"] == "nexus.bash"
    assert payload["direct_delivery_allowed"] is False
    assert service.submitted_requests == []
    command = payload["actionable"]["next_commands"][0]
    assert command["connector_tool"] == "nexus.bash"
    assert command["command"].startswith(f"{sys.executable} -m scripts.engine.nexus_cli self-hosted approve --task-id chatgpt-cutover")


def test_launch_submits_once_then_surfaces_integration_command(tmp_path: Path):
    repo = _repo(tmp_path)
    service = FakeSelfHostedService(
        actionable_after={
            "schema": "nexus.self_hosted_actionable_tasks.v1",
            "actionable_count": 1,
            "tasks": [
                {
                    "task_id": "chatgpt-delivery-cutover",
                    "status": "APPROVED",
                    "promotion_status": "APPROVED",
                    "task_action": {
                        "task_id": "chatgpt-delivery-cutover",
                        "action_state": "ACTION_REQUIRED",
                        "attention_required": True,
                        "next_action": "integrate_approved_candidate",
                        "recommended_tool": "nexus_self_hosted_integrate_approved",
                    },
                }
            ],
        }
    )

    payload = run_delivery_cutover(
        what="Cut over ChatGPT delivery",
        why="Prevent direct connector writes",
        task_id="chatgpt-delivery-cutover",
        controller_repo_root=repo,
        target_worktree_root=tmp_path / "targets",
        allowed_files=["scripts/ops/nexus_chatgpt_delivery.py"],
        verifier_commands=["git diff --check"],
        service=service,
    )

    assert payload["submitted"] is True
    assert service.waited == ["chatgpt-delivery-cutover"]
    assert len(service.submitted_requests) == 1
    request = service.submitted_requests[0]
    assert request["target_worktree_root"] == str((tmp_path / "targets").resolve())
    assert request["target_repo_root"] == str((tmp_path / "targets" / "chatgpt-delivery-cutover").resolve())
    command = payload["actionable"]["next_commands"][0]["command"]
    assert command == (
        f"{sys.executable} -m scripts.engine.nexus_cli self-hosted integrate --task-id chatgpt-delivery-cutover "
        f"--integration-branch {DEFAULT_INTEGRATION_BRANCH}"
    )


def test_action_command_reports_missing_approval_binding():
    task = _actionable_task()
    del task["task_action"]["candidate"]["verified_receipt_hash"]
    command = action_command_for_task(task)
    assert command["command"] is None
    assert command["missing"] == ["verified_receipt_hash"]


def test_cli_guard_tool_returns_blocking_json(capsys):
    from scripts.ops.nexus_chatgpt_delivery import main

    exit_code = main(["guard-tool", "--tool", "write"])
    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert captured["allowed"] is False
    assert captured["required_tool"] == "nexus.bash"


def test_action_command_uses_real_executable_path_and_avoids_nonexistent_nexus_binary():
    task = _actionable_task()
    cmd_info = action_command_for_task(task)
    cmd_str = cmd_info["command"]
    assert cmd_str is not None
    assert not cmd_str.startswith("nexus ")
    exe_path = cmd_str.split()[0]
    assert Path(exe_path).exists()
    assert f"{sys.executable} -m scripts.engine.nexus_cli self-hosted approve" in cmd_str


def test_subcommand_is_list_actionable_not_wrong_actionable():
    from scripts.engine.nexus_cli import self_hosted_group

    assert "list-actionable" in self_hosted_group.commands
    assert "actionable" not in self_hosted_group.commands

    launch_skill = (Path(__file__).resolve().parents[2] / ".agents" / "skills" / "nexus-task-launch" / "SKILL.md").read_text(encoding="utf-8")
    merge_skill = (Path(__file__).resolve().parents[2] / ".agents" / "skills" / "nexus-merge-gate" / "SKILL.md").read_text(encoding="utf-8")

    assert "nexus self-hosted actionable" not in launch_skill
    assert "nexus self-hosted actionable" not in merge_skill
    assert "self-hosted list-actionable" in launch_skill
    assert "self-hosted list-actionable" in merge_skill


def test_skills_do_not_contain_contradictory_connector_blocked_rule_when_nexus_bash_available():
    launch_skill = (Path(__file__).resolve().parents[2] / ".agents" / "skills" / "nexus-task-launch" / "SKILL.md").read_text(encoding="utf-8")
    merge_skill = (Path(__file__).resolve().parents[2] / ".agents" / "skills" / "nexus-merge-gate" / "SKILL.md").read_text(encoding="utf-8")

    assert "If the lifecycle tools are not visible or the existing connector cannot expose them, stop fail-closed with `REPO_READY_CONNECTOR_BLOCKED`." not in launch_skill
    assert "REPO_READY_CONNECTOR_BLOCKED is the terminal result when the required\nconnector tools are unavailable." not in merge_skill

    launch_text = " ".join(launch_skill.replace("`", "").split())
    merge_text = " ".join(merge_skill.replace("`", "").split())

    assert "nexus.bash must be used for governed lifecycle operations" in launch_text
    assert "REPO_READY_CONNECTOR_BLOCKED applies only when neither native lifecycle tools nor nexus.bash with repo-owned CLI wrappers are available." in launch_text
    assert "nexus.bash must be used for governed lifecycle operations" in merge_text
