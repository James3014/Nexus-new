import pytest
from nexus.pilot_cli.session import PilotSession

@pytest.fixture
def session():
    return PilotSession(active_task_id="test-task", workspace="/tmp/ws")

def test_session_initialization(session):
    assert session.mode == "FAST"
    assert session.workspace == "/tmp/ws"

def test_session_describe(session):
    description = session.describe()
    assert "Workspace: /tmp/ws" in description
    assert "Mode: FAST" in description

def test_session_reset(session):
    session.mode = "BATTLE"
    session.reset_context()
    assert session.mode == "FAST"
    assert session.workspace is None
