import pytest
from unittest.mock import patch, MagicMock
from nexus.federation.fleet_manager import get_node_id, start_fleet, stop_fleet

def test_get_node_id():
    assert get_node_id(8001, "us-east-1") == "node-8001-us-east-1"

@patch("subprocess.Popen")
def test_start_fleet(mock_popen):
    start_fleet(5, "secret-token")
    assert mock_popen.call_count == 5
    
    # Check one call
    args, kwargs = mock_popen.call_args
    cmd = args[0]
    assert "--swarm-mode" in cmd
    assert "--swarm-token" in cmd
    assert "secret-token" in cmd

@patch("subprocess.run")
def test_stop_fleet(mock_run):
    stop_fleet()
    assert mock_run.called
    args, _ = mock_run.call_args
    assert "pkill" in args[0]
