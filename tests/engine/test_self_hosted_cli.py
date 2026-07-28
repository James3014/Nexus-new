import json
from pathlib import Path
import pytest
from click.testing import CliRunner

from scripts.engine.nexus_cli import nexus
from scripts.engine.commands.self_hosted_actions import set_test_runner


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
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


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

