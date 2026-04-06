import pytest
import subprocess
from pathlib import Path
from scripts.ops.ci_gate import run_lesson_check, main
import sys

def test_run_lesson_check_pass(monkeypatch):
    class MockRes:
        returncode = 0
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockRes())
    assert run_lesson_check(dry_run=False) is True

def test_run_lesson_check_fail(monkeypatch):
    class MockRes:
        returncode = 1
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockRes())
    assert run_lesson_check(dry_run=False) is False

def test_ci_gate_blocks_on_lesson_fail(monkeypatch):
    # Mock subprocess.run for all steps
    def mock_run(cmd, *args, **kwargs):
        class MockRes:
            returncode = 0
            stdout = "PASSED"
            stderr = ""
        
        # If it's the lesson check, make it fail
        if "lesson_writeback_check.py" in str(cmd):
            MockRes.returncode = 1
            MockRes.stdout = "FAILED"
        return MockRes()

    monkeypatch.setattr(subprocess, "run", mock_run)
    
    # Mock sys.exit to catch it
    exit_codes = []
    monkeypatch.setattr(sys, "exit", lambda code: exit_codes.append(code))
    
    # Mock other requirements for main() to run
    monkeypatch.setattr(Path, "exists", lambda x: True)
    
    # Run main with some arguments
    monkeypatch.setattr(sys, "argv", ["ci_gate.py"])
    
    try:
        main()
    except SystemExit:
        pass
    
    assert 1 in exit_codes
