import pytest
from unittest.mock import MagicMock, patch
from nexus.pilot_cli.commands import handle_command
from nexus.pilot_cli.session import PilotSession

@pytest.fixture
def session():
    return PilotSession(workspace="/tmp/ws")

def test_handle_status_command(session):
    result = handle_command("/status", session)
    assert "Workspace: /tmp/ws" in result

def test_handle_mount_command(session):
    result = handle_command("/mount /another/path", session)
    assert session.workspace == "/another/path"
    assert "Mounted workspace: /another/path" in result

def test_handle_reset_command(session):
    session.mode = "BATTLE"
    result = handle_command("/reset", session)
    assert session.mode == "FAST"
    assert session.workspace is None
    assert "Context reset" in result

def test_handle_unknown_command(session):
    result = handle_command("/foo", session)
    assert "Unknown command" in result

@patch("nexus.pilot_cli.commands.govern_via_gateway")
def test_handle_govern_command(mock_govern, session):
    mock_govern.return_value = {"task_id": "task-1", "summary": "done"}
    result = handle_command("/govern fix bug", session)
    assert "Battle Mode engaged" in result
    assert "task-1" in result
