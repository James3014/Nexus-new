import pytest
from click.testing import CliRunner
from scripts.engine.nexus_cli import nexus
import os
from unittest.mock import patch, MagicMock


def test_cli_status_aos():
    runner = CliRunner()
    result = runner.invoke(nexus, ["nexus:status", "--aos"])
    assert result.exit_code == 0
    assert "[Nexus:AOS] Governance Verification" in result.output
    assert "Federation Status" in result.output


def test_cli_hud_daemon():
    runner = CliRunner()
    with patch("nexus.services.cli_commands_service.subprocess.Popen") as mock_popen:
        result = runner.invoke(nexus, ["nexus:hud", "--refresh", "1", "--daemon"])
    assert result.exit_code == 0
    assert "[HUD] Background Daemon STARTING" in result.output
    assert mock_popen.called

def test_cli_spec_lock():
    runner = CliRunner()
    # 建立一個測試規格檔案
    test_spec = "TEST_SPEC.md"
    with open(test_spec, "w") as f:
        f.write("# Test Spec\n\n- Goal: Test Spec Lock")
    
    try:
        # 測試 Spec Lock 指令
        result = runner.invoke(nexus, ["nexus:spec-lock", test_spec])
        assert result.exit_code == 0
        assert f"Auditing {test_spec} against MUSE_ENGINE_SPEC" in result.output
        assert f"{test_spec} PASSED Constitutional Audit" in result.output
    finally:
        if os.path.exists(test_spec):
            os.remove(test_spec)

def test_cli_invalid_command():
    runner = CliRunner()
    # 測試無效指令
    result = runner.invoke(nexus, ["nexus:invalid-cmd"])
    assert result.exit_code != 0


def test_cli_governance_check_pass():
    runner = CliRunner()
    with patch("scripts.engine.nexus_cli.subprocess.run", return_value=MagicMock(returncode=0)):
        result = runner.invoke(nexus, ["nexus:governance-check"])
    assert result.exit_code == 0
    assert "[Governance-Check] PASS" in result.output


def test_cli_governance_check_fail():
    runner = CliRunner()
    with patch("scripts.engine.nexus_cli.subprocess.run", return_value=MagicMock(returncode=1)):
        result = runner.invoke(nexus, ["nexus:governance-check"])
    assert result.exit_code != 0
    assert "Governance gate failed" in result.output


def test_cli_acceptance_check_blocks_when_governance_fails():
    runner = CliRunner()
    with patch("scripts.engine.nexus_cli.subprocess.run", return_value=MagicMock(returncode=2)):
        result = runner.invoke(nexus, ["nexus:acceptance-check", "--window", "10"])
    assert result.exit_code != 0
    assert "Governance gate failed before acceptance-check" in result.output


import json

def test_cli_closeout_pass(tmp_path):
    runner = CliRunner()
    contract_file = tmp_path / "done_contract_test.json"
    data = {
        "linter_exit_code": 0,
        "ci_gate_exit_code": 0,
        "required_tests_passed": True,
        "commit_sha": "abc123def456",
        "changed_files": ["file1.py"]
    }
    contract_file.write_text(json.dumps(data))
    
    result = runner.invoke(nexus, ["nexus:closeout", "--contract", str(contract_file)])
    assert result.exit_code == 0
    assert "Hard-Gate successfully cleared" in result.output

def test_cli_closeout_fail(tmp_path):
    runner = CliRunner()
    contract_file = tmp_path / "fail_contract_test.json"
    data = {
        "linter_exit_code": 1,
        "ci_gate_exit_code": 0,
        "required_tests_passed": True,
        "commit_sha": "abc123def456",
        "changed_files": ["file1.py"]
    }
    contract_file.write_text(json.dumps(data))
    
    result = runner.invoke(nexus, ["nexus:closeout", "--contract", str(contract_file)])
    assert result.exit_code != 0
    # Output should contain the JSON error
    assert '"ok": false' in result.output
    assert '"linter_ok": false' in result.output

def test_cli_closeout_missing_contract():
    runner = CliRunner()
    result = runner.invoke(nexus, ["nexus:closeout", "--contract", "non_existent.json"])
    assert result.exit_code != 0
    assert "Contract file missing" in result.output
