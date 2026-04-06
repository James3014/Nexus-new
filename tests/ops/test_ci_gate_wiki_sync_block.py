import subprocess
import pytest
import sys
from unittest.mock import MagicMock, patch
from pathlib import Path
from scripts.ops import ci_gate

def test_ci_gate_dry_run_wiki_sync_blocks_rc2(monkeypatch):
    """
    mock wiki_sync_check 回傳 2，驗證 ci_gate dry-run return 1
    """
    def mock_run(cmd, *args, **kwargs):
        class MockRes:
            def __init__(self, returncode):
                self.returncode = returncode
        if "wiki_sync_check.py" in cmd:
            return MockRes(2)
        return MockRes(0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr("scripts.ops.ci_gate.Path.exists", lambda x: True)
    monkeypatch.setattr("scripts.ops.ci_gate.ROOT", Path("/tmp"))
    
    exit_code = ci_gate.run_dry_run()
    assert exit_code == 1

def test_ci_gate_main_wiki_sync_blocks_rc2(monkeypatch):
    """
    mock wiki_sync_check 回傳 2，驗證 non-dry-run 會阻斷
    """
    # Mocking main to capture sys.exit(1)
    
    with patch("sys.exit") as mock_exit:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = lambda cmd, *args, **kwargs: MagicMock(returncode=2 if "wiki_sync_check.py" in cmd else 0)
            
            # Setup arguments
            with patch("argparse.ArgumentParser.parse_args") as mock_args:
                mock_args.return_value = MagicMock(dry_run=False, strict=False, 
                                                 wiki_drift_enforce_level="warn",
                                                 wiki_capability_enforce_level="warn",
                                                 wiki_eval_enforce_level="warn")
                
                # Mock path existence to avoid early failures
                with patch("scripts.ops.ci_gate.Path.exists", return_value=True):
                    # Call main
                    ci_gate.main()
                    
                    # Verify sys.exit(1) was called after wiki_sync_check (which is 0c)
                    mock_exit.assert_called_with(1)
