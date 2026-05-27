import pytest
import subprocess
import sys
import os
import shlex
from click.testing import CliRunner
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.engine.nexus_cli import nexus

REPO_ROOT = Path(__file__).resolve().parents[1]

def test_cli_command_injection():
    """
    TDD Phase: Verify that passing malicious operators in task_name to delegate command
    is blocked / safely handled or sanitized.
    """
    runner = CliRunner()
    result = runner.invoke(nexus, ["nexus", "delegate", "malicious; rm -rf /"])
    assert result.exit_code != 0
    assert "Invalid task name" in result.output

def test_cli_output_deadlock():
    """
    TDD Phase: Verify that the subprocess runner in nexus_cli handles massive I/O
    without hanging (using subprocess.Popen and communicate).
    """
    runner = CliRunner()
    
    # We write a dummy presets.json
    presets_file = REPO_ROOT / ".nexus" / "presets_test.json"
    presets_file.parent.mkdir(parents=True, exist_ok=True)
    import json
    presets_file.write_text(json.dumps([{"name": "test_preset", "timeout_sec": 1, "max_wall_time_sec": 2, "ab_trials": 1}]), encoding="utf-8")
    
    manifest_file = REPO_ROOT / ".nexus" / "manifest_test.json"
    manifest_file.write_text(json.dumps({"tasks": []}), encoding="utf-8")
    
    report_file = REPO_ROOT / ".nexus" / "reports" / "meta-opt-test.json"
    
    with patch("subprocess.Popen") as mock_popen:
        mock_p = MagicMock()
        mock_p.returncode = 0
        mock_p.communicate.return_value = ("large_output_log" * 10000, "")
        mock_popen.return_value = mock_p
        
        result = runner.invoke(
            nexus,
            [
                "nexus",
                "research:meta-opt",
                "--manifest-file",
                ".nexus/manifest_test.json",
                "--presets-file",
                ".nexus/presets_test.json",
                "--report-file",
                ".nexus/reports/meta-opt-test.json"
            ]
        )
        
        print("EXIT CODE:", result.exit_code)
        print("OUTPUT:", result.output)
        if result.exception:
            print("EXCEPTION:", result.exception)
            import traceback
            traceback.print_exception(type(result.exception), result.exception, result.exception.__traceback__)
        
        # Verify Popen was called and communicate was called to drain output
        mock_popen.assert_called()
        mock_p.communicate.assert_called_once()
        
    # Cleanup files
    if presets_file.exists():
        presets_file.unlink()
    if manifest_file.exists():
        manifest_file.unlink()

def test_cli_command_injection_sanitized_runner():
    """
    TDD Phase (RED): Verify SanitizedRunner and AllowedTaskRegistry correctly
    sanitize inputs, enforce task name allowed formats, and prevent execution.
    """
    from scripts.engine.nexus_cli import SanitizedRunner
    
    # 1. Test validate_task_name
    assert SanitizedRunner.validate_task_name("valid-task_name 123") is True
    assert SanitizedRunner.validate_task_name("bad; rm -rf") is False
    assert SanitizedRunner.validate_task_name("bad$(exec)") is False
    
    # 2. Test sanitize_arg
    assert SanitizedRunner.sanitize_arg("hello") == "hello"
    assert SanitizedRunner.sanitize_arg("hello; world") == "'hello; world'"

