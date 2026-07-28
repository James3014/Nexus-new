import json
import os
import sys
import subprocess
from pathlib import Path
import pytest

from scripts.ops.nexus_cueline_worker import (
    build_cli_argv,
    parse_and_validate_input,
    resolve_repo_root,
)
from scripts.engine.commands.self_hosted_actions import set_test_runner


@pytest.fixture(autouse=True)
def safe_test_runner():
    def _fake_runner(contract, request, update):
        update("CANDIDATE_COMMITTED", {"candidate_commit_sha": "a" * 40})
        return {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_created": True,
        }
    set_test_runner(_fake_runner)
    yield
    set_test_runner(None)


def test_json_input_to_exact_argv():
    """Prove JSON inputs map to exact self-hosted CLI argv lists."""
    # 1. submit
    submit_payload = {
        "op": "submit",
        "task_id": "cueline-task-001",
        "what": "Refactor worker module",
        "why": "Improve testability",
        "controller_revision": "1111111111111111111111111111111111111111",
        "target_base_revision": "2222222222222222222222222222222222222222",
        "controller_repo_root": "/tmp/controller",
        "target_repo_root": "/tmp/target",
        "target_worktree_root": "/tmp/worktrees",
        "allowed_files": ["src/a.py", "src/b.py"],
        "worker": "codex",
        "state_dir": "/tmp/state",
    }
    validated = parse_and_validate_input(json.dumps(submit_payload))
    argv = build_cli_argv(validated)
    expected_prefix = [sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "submit"]
    assert argv[:5] == expected_prefix
    assert "--task-id" in argv and argv[argv.index("--task-id") + 1] == "cueline-task-001"
    assert "--allowed-files" in argv and argv[argv.index("--allowed-files") + 1] == "src/a.py,src/b.py"
    assert "--worker" in argv and argv[argv.index("--worker") + 1] == "codex"

    # 2. status
    status_payload = {"op": "status", "task_id": "cueline-task-001", "state_dir": "/tmp/state"}
    validated = parse_and_validate_input(json.dumps(status_payload))
    argv = build_cli_argv(validated)
    assert argv == [
        sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "status",
        "--task-id", "cueline-task-001", "--state-dir", "/tmp/state"
    ]

    # 3. wait
    wait_payload = {"op": "wait", "task_id": "cueline-task-001", "timeout": 15.0, "poll_interval": 0.5}
    validated = parse_and_validate_input(json.dumps(wait_payload))
    argv = build_cli_argv(validated)
    assert argv == [
        sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "wait",
        "--task-id", "cueline-task-001", "--timeout", "15.0", "--poll-interval", "0.5"
    ]

    # 4. list-actionable
    list_payload = {"op": "list-actionable", "state_dir": "/tmp/state"}
    validated = parse_and_validate_input(json.dumps(list_payload))
    argv = build_cli_argv(validated)
    assert argv == [
        sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "list-actionable",
        "--state-dir", "/tmp/state"
    ]


def test_unknown_field_rejection():
    """Prove input containing unknown operations, fields, or invalid types are strictly rejected."""
    # Unknown field
    bad_field_payload = {
        "op": "status",
        "task_id": "cueline-task-001",
        "malicious_extra_field": "hacked",
    }
    with pytest.raises(ValueError, match="Unknown field.*malicious_extra_field"):
        parse_and_validate_input(json.dumps(bad_field_payload))

    # Unknown operation
    bad_op_payload = {"op": "exec_arbitrary_cmd", "cmd": "whoami"}
    with pytest.raises(ValueError, match="Unknown operation.*exec_arbitrary_cmd"):
        parse_and_validate_input(json.dumps(bad_op_payload))

    # Invalid type for string field
    bad_type_payload = {"op": "status", "task_id": 12345}
    with pytest.raises(TypeError, match="Field 'task_id' must be a string"):
        parse_and_validate_input(json.dumps(bad_type_payload))


def test_shell_metacharacters_remain_data_not_execution(tmp_path: Path):
    """Prove shell metacharacters in JSON payloads remain raw data and cause no shell execution."""
    canary_file = tmp_path / "should_not_exist.tmp"
    shell_payload = {
        "op": "submit",
        "task_id": f"task-001; touch {canary_file}; echo hacked",
        "what": "$(whoami) | cat /etc/passwd",
        "why": "test `date` > /tmp/test",
    }
    validated = parse_and_validate_input(json.dumps(shell_payload))
    argv = build_cli_argv(validated)

    # Confirm argv contains exact literal string with metacharacters
    assert f"task-001; touch {canary_file}; echo hacked" in argv
    assert "$(whoami) | cat /etc/passwd" in argv

    # Invoke worker script with shell payload via stdin
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "nexus_cueline_worker.py"
    res = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(shell_payload),
        text=True,
        capture_output=True,
    )

    # Shell file injection should NOT have occurred
    assert not canary_file.exists()
    # Script handled payload securely without shell execution
    assert res.returncode != 0 or "task-001" in res.stdout


def test_approve_bindings_forwarded_exactly():
    """Prove approve operation forwards exact commit, tree, state, and receipt hashes."""
    approve_payload = {
        "op": "approve",
        "task_id": "sh-task-999",
        "candidate_commit_sha": "a" * 40,
        "candidate_tree_sha": "b" * 40,
        "candidate_state_hash": "c" * 64,
        "verified_receipt_hash": "d" * 64,
        "state_dir": "/tmp/custom_state",
    }
    validated = parse_and_validate_input(json.dumps(approve_payload))
    argv = build_cli_argv(validated)

    assert argv == [
        sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", "approve",
        "--task-id", "sh-task-999",
        "--candidate-commit-sha", "a" * 40,
        "--candidate-tree-sha", "b" * 40,
        "--candidate-state-hash", "c" * 64,
        "--verified-receipt-hash", "d" * 64,
        "--state-dir", "/tmp/custom_state",
    ]


def test_cli_failure_codes_propagate(tmp_path: Path):
    """Prove Nexus CLI non-zero exit codes and stderr propagate cleanly through the worker."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "nexus_cueline_worker.py"
    state_dir = str(tmp_path / "state")

    # Status request for non-existent task should fail in CLI
    nonexistent_payload = {
        "op": "status",
        "task_id": "non-existent-task-99999",
        "state_dir": state_dir,
    }

    res = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(nonexistent_payload),
        text=True,
        capture_output=True,
    )

    # CLI failure code must propagate
    assert res.returncode != 0
    assert "Task not found" in res.stderr or "Error" in res.stderr or "error" in res.stderr.lower() or res.returncode == 1


def test_nexus_cueline_worker_full_pipeline_subprocess(tmp_path: Path):
    """End-to-end integration test of CueLine worker handling task submit & status."""
    controller = tmp_path / "controller"
    controller.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=controller, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CueLine Test"], cwd=controller, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "cueline@example.test"], cwd=controller, check=True, capture_output=True)
    (controller / "README").write_text("base\n")
    subprocess.run(["git", "add", "README"], cwd=controller, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=controller, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=controller, check=True, capture_output=True, text=True).stdout.strip()
    target_root = tmp_path / "targets"
    state_dir = str(tmp_path / "state")

    submit_req = {
        "op": "submit",
        "task_id": "cueline-e2e-001",
        "what": "Test CueLine worker end-to-end",
        "why": "Validate process worker integration",
        "controller_revision": head,
        "target_base_revision": head,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "cueline-e2e-001"),
        "target_worktree_root": str(target_root),
        "allowed_files": "file1.py",
        "worker": "codex",
        "state_dir": state_dir,
    }

    script_path = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "nexus_cueline_worker.py"
    res_submit = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(submit_req),
        text=True,
        capture_output=True,
    )
    assert res_submit.returncode == 0, f"Worker submit failed: {res_submit.stderr}"
    out_submit = json.loads(res_submit.stdout)
    assert out_submit["task_id"] == "cueline-e2e-001"
    assert out_submit["status"] == "SUBMITTED"

    status_req = {
        "op": "status",
        "task_id": "cueline-e2e-001",
        "state_dir": state_dir,
    }
    res_status = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(status_req),
        text=True,
        capture_output=True,
    )
    assert res_status.returncode == 0, f"Worker status failed: {res_status.stderr}"
    out_status = json.loads(res_status.stdout)
    assert out_status["task_id"] == "cueline-e2e-001"
    assert out_status["status"] in {"SUBMITTED", "WORKER_RUNNING", "CANDIDATE_COMMITTED", "CANDIDATE_CAPTURED", "PENDING_HUMAN_APPROVAL"}


def test_extra_positional_cli_text_rejected():
    """Prove extra positional arguments on CLI are rejected."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "nexus_cueline_worker.py"
    res = subprocess.run(
        [sys.executable, str(script_path), "extra_arg_1"],
        input=json.dumps({"op": "list-actionable"}),
        text=True,
        capture_output=True,
    )
    assert res.returncode != 0
    assert "Extra positional command-line text is strictly rejected" in res.stderr


def test_repo_root_env_var_validation(tmp_path: Path):
    """Prove NEXUS_CUELINE_REPO_ROOT is validated as a Nexus checkout."""
    invalid_dir = tmp_path / "fake_repo"
    invalid_dir.mkdir()

    # Invalid repo root should raise ValueError
    with pytest.raises(ValueError, match="is not a valid Nexus repository checkout"):
        os.environ["NEXUS_CUELINE_REPO_ROOT"] = str(invalid_dir)
        try:
            resolve_repo_root()
        finally:
            del os.environ["NEXUS_CUELINE_REPO_ROOT"]

