import pytest
from click.testing import CliRunner
from scripts.engine.nexus_cli import nexus
import os
from unittest.mock import patch


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
