import pytest
from click.testing import CliRunner
from scripts.engine.nexus_cli import nexus
import os

def test_cli_resilient_shell_audit():
    runner = CliRunner()
    # 測試 Audit 模式
    result = runner.invoke(nexus, ["nexus:resilient-shell", "--mode", "audit"])
    assert result.exit_code == 0
    assert "Error Boundary ACTIVE" in result.output
    assert "audit mode" in result.output

def test_cli_resilient_shell_block():
    runner = CliRunner()
    # 測試 Block 模式
    result = runner.invoke(nexus, ["nexus:resilient-shell", "--mode", "block"])
    assert result.exit_code == 0
    assert "block mode" in result.output

def test_cli_hud():
    runner = CliRunner()
    # 測試 HUD 指令 (Mock 啟動文字)
    result = runner.invoke(nexus, ["nexus:hud", "--refresh", "1"])
    assert result.exit_code == 0
    assert "Persistent state monitoring" in result.output
    assert "AOS Score" in result.output

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
        assert f"Locking {test_spec}" in result.output
        assert "Spec-Lock complete" in result.output
    finally:
        if os.path.exists(test_spec):
            os.remove(test_spec)

def test_cli_invalid_command():
    runner = CliRunner()
    # 測試無效指令
    result = runner.invoke(nexus, ["nexus:invalid-cmd"])
    assert result.exit_code != 0
