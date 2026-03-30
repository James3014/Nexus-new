import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from nexus.federation.node_launcher import NodeLauncher

def test_node_launcher_native_fallback():
    launcher = NodeLauncher(repo_path="/tmp/nexus", wasm_mode=False)
    
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 1234
        proc = launcher.launch("scripts/test.py", ["--arg1"])
        
        assert proc.pid == 1234
        args, _ = mock_popen.call_args
        cmd = args[0]
        assert cmd[0] == sys.executable
        assert cmd[1].endswith("/tmp/nexus/scripts/test.py")
        assert "--arg1" in cmd

@patch("subprocess.Popen")
def test_node_launcher_wasm_mode(mock_popen):
    launcher = NodeLauncher(repo_path="/tmp/nexus", wasm_mode=True)
    mock_popen.return_value.pid = 5678
    
    proc = launcher.launch("scripts/test.py", ["--wasm-arg"])
    
    assert proc.pid == 5678
    args, _ = mock_popen.call_args
    cmd = args[0]
    assert cmd[0] == "wasmer"
    assert "wasmer/python" in cmd
    assert "--volume" in cmd
    assert "/tmp/nexus:/workspace" in cmd
