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
    req = _valid_request(tmp_path, task_id="test-sh-subproc-001")

    # Submit task first via python -m scripts.engine.nexus_cli
    sub_cmd = [
        sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "submit",
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
    sub_res = subprocess.run(sub_cmd, capture_output=True, text=True)
    assert sub_res.returncode == 0, f"Subprocess submit failed: {sub_res.stderr}"

    # Subprocess wait
    wait_cmd = [
        sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "wait",
        "--task-id", "test-sh-subproc-001",
        "--timeout", "1.0",
        "--poll-interval", "0.05",
        "--state-dir", state_dir,
    ]
    wait_res = subprocess.run(wait_cmd, capture_output=True, text=True)
    assert wait_res.returncode == 0, f"Subprocess wait failed: {wait_res.stderr}"
    wait_data = json.loads(wait_res.stdout)
    assert wait_data["task_id"] == "test-sh-subproc-001"

    # Set promotion_status in state file so attention_required becomes True
    state_file = Path(state_dir) / "test-sh-subproc-001.json"
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    state_data["promotion_status"] = "PENDING_HUMAN_APPROVAL"
    state_file.write_text(json.dumps(state_data), encoding="utf-8")

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


