from unittest.mock import MagicMock, patch

from nexus.core.drone_engine import DRONE_ADMITTED_MODEL, LocalBonsaiBrain


def test_gbnf_grammar_injection(monkeypatch):
    monkeypatch.delenv("NEXUS_OLLAMA_URL", raising=False)
    brain = LocalBonsaiBrain()
    assert brain.api_url == "http://127.0.0.1:11434"
    assert brain.model == DRONE_ADMITTED_MODEL == "qwen3.5:9b"

    with patch("nexus.core.drone_engine.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": '{"action": "BASH", "command": "pwd"}'}}
        mock_post.return_value = mock_resp

        result = brain.ask_structured([{"role": "user", "content": "List files"}])

    url = mock_post.call_args.args[0]
    payload = mock_post.call_args.kwargs["json"]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert payload["model"] == "qwen3.5:9b"
    assert payload["format"]["properties"]["action"]["enum"] == ["BASH", "EDIT", "DONE"]
    assert "grammar" not in payload
    assert result["action"] == "BASH"


def test_env_url_override_and_never_retired_model(monkeypatch):
    monkeypatch.setenv("NEXUS_OLLAMA_URL", "http://example:1/")
    brain = LocalBonsaiBrain()
    assert brain.api_url == "http://example:1"
    assert "qwen2.5-s2t-advisor" not in brain.model


def test_health_check_fails_closed_with_reason():
    brain = LocalBonsaiBrain("http://dummy")
    with patch("nexus.core.drone_engine.requests.get", side_effect=OSError("refused")):
        assert brain.health_check() is False
    assert "unreachable" in brain.last_unavailable_reason

    resp = MagicMock(status_code=200)
    resp.json.return_value = {"models": [{"name": "other:1b"}]}
    with patch("nexus.core.drone_engine.requests.get", return_value=resp):
        assert brain.health_check() is False
    assert "not installed" in brain.last_unavailable_reason

    resp.json.return_value = {"models": [{"name": "qwen3.5:9b"}]}
    with patch("nexus.core.drone_engine.requests.get", return_value=resp):
        assert brain.health_check() is True
