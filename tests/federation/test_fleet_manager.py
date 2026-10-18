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
    # #2637: no name-matching kill; stop_fleet refuses instead of running one.
    with pytest.raises(RuntimeError, match="#2637"):
        stop_fleet()
    assert not mock_run.called
