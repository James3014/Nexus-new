from nexus.pilot_cli.session import PilotSession


def test_api_key_is_masked_in_status_output():
    session = PilotSession(api_key="sk-secret-123456")
    status = session.describe()
    assert "123456" not in status
    assert "sk-s" in status


def test_session_cleanup_removes_api_key():
    session = PilotSession(api_key="sk-secret")
    session.clear_secrets()
    assert session.api_key is None


def test_session_describe_includes_active_task_when_present():
    session = PilotSession(api_key="sk-secret", active_task_id="pilot-task-123")
    status = session.describe()
    assert "Active Task: pilot-task-123" in status


def test_session_describe_shows_gateway_url(monkeypatch):
    monkeypatch.setenv("NEXUS_PILOT_GATEWAY_URL", "http://100.88.1.2:5005")
    session = PilotSession()
    status = session.describe()
    assert "Gateway: http://100.88.1.2:5005" in status
