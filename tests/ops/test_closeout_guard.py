import json
import pytest
import subprocess
import sys
from pathlib import Path

# Path to the script under test
GUARD_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "closeout_guard.py"

@pytest.fixture
def valid_contract(tmp_path):
    contract_file = tmp_path / "done_contract.json"
    data = {
        "linter_exit_code": 0,
        "ci_gate_exit_code": 0,
        "required_tests_passed": True,
        "commit_sha": "abc123def456",
        "changed_files": ["file1.py", "file2.py"]
    }
    contract_file.write_text(json.dumps(data))
    return contract_file

def test_guard_pass_with_valid_contract(valid_contract):
    result = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), "--contract", str(valid_contract)],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["ok"] is True
    assert output["checks"]["linter_ok"] is True
    assert output["checks"]["ci_gate_ok"] is True
    assert output["checks"]["tests_ok"] is True
    assert output["checks"]["commit_ok"] is True
    assert output["checks"]["files_ok"] is True

def test_guard_fail_with_missing_linter_exit_code(tmp_path):
    contract_file = tmp_path / "invalid_contract.json"
    data = {
        "ci_gate_exit_code": 0,
        "required_tests_passed": True,
        "commit_sha": "abc123def456",
        "changed_files": ["file1.py"]
    }
    contract_file.write_text(json.dumps(data))
    
    result = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), "--contract", str(contract_file)],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert "Missing required fields: linter_exit_code" in output["error"]

def test_guard_fail_with_linter_failure(tmp_path):
    contract_file = tmp_path / "fail_contract.json"
    data = {
        "linter_exit_code": 1,
        "ci_gate_exit_code": 0,
        "required_tests_passed": True,
        "commit_sha": "abc123def456",
        "changed_files": ["file1.py"]
    }
    contract_file.write_text(json.dumps(data))
    
    result = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), "--contract", str(contract_file)],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert output["checks"]["linter_ok"] is False

def test_guard_fail_with_empty_commit_sha(tmp_path):
    contract_file = tmp_path / "fail_contract.json"
    data = {
        "linter_exit_code": 0,
        "ci_gate_exit_code": 0,
        "required_tests_passed": True,
        "commit_sha": "",
        "changed_files": ["file1.py"]
    }
    contract_file.write_text(json.dumps(data))
    
    result = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), "--contract", str(contract_file)],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert output["checks"]["commit_ok"] is False

def test_guard_fail_with_empty_changed_files(tmp_path):
    contract_file = tmp_path / "fail_contract.json"
    data = {
        "linter_exit_code": 0,
        "ci_gate_exit_code": 0,
        "required_tests_passed": True,
        "commit_sha": "abc123def456",
        "changed_files": []
    }
    contract_file.write_text(json.dumps(data))
    
    result = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), "--contract", str(contract_file)],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert output["checks"]["files_ok"] is False

def test_guard_fail_missing_contract():
    result = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), "--contract", "non_existent_contract.json"],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["ok"] is False
    assert "Contract file missing" in output["error"]
