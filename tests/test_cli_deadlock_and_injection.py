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
    
    # Define an async mock for AsyncProcessExecutor.run_async
    async def mock_run_async(*args, **kwargs):
        # The arguments are (self, cmd, log_path) or (cmd, log_path)
        log_path = args[2] if len(args) > 2 else args[1]
        log_path.write_text("large_output_log" * 10000, encoding="utf-8")
        return 0, 160000, 0

    with patch("scripts.engine.nexus_cli.AsyncProcessExecutor.run_async", new=mock_run_async):
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
        
        assert result.exit_code == 0
        
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

@pytest.mark.anyio
async def test_cli_async_process_executor_deadlock():
    """
    TDD Phase (RED): Verify AsyncProcessExecutor can execute a subprocess
    and stream massive output (>64KB) asynchronously to a file without deadlocking.
    """
    from scripts.engine.nexus_cli import AsyncProcessExecutor
    import tempfile
    
    # Generate ~200KB output which exceeds 64KB OS pipe buffer
    huge_command = [sys.executable, "-c", "import sys; sys.stdout.write('A' * 200000); sys.stderr.write('B' * 10000)"]
    
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as log_file:
        log_path = Path(log_file.name)
        try:
            executor = AsyncProcessExecutor()
            # We run it asynchronously
            returncode, stdout_len, stderr_len = await executor.run_async(huge_command, log_path)
            
            assert returncode == 0
            assert stdout_len == 200000
            assert stderr_len == 10000
            
            # Verify it actually logged to disk
            content = log_path.read_text()
            assert "A" * 200000 in content
            assert "B" * 10000 in content
        finally:
            if log_path.exists():
                log_path.unlink()


