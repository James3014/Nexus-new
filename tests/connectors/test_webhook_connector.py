import pytest
from unittest.mock import patch, MagicMock
from nexus.connectors.base import NexusEvent
from nexus.connectors.webhook_connector import WebhookConnector

@pytest.fixture
def test_event():
    """建立測試事件。"""
    return NexusEvent(
        event_type="improvement",
        task="P5-Testing",
        round_id=7,
        score=92.5,
        message="FlashJudge detected massive gain."
    )

def test_event_serialization(test_event):
    """驗證事件序列化 JSON。"""
    data = test_event.to_json()
    assert data["type"] == "improvement"
    assert data["score"] == 92.5
    assert "P5-Testing" in data["task"]

@patch("requests.post")
def test_webhook_send_success(mock_post, test_event):
    """驗證 Webhook 推送成功場景。"""
    mock_post.return_value.status_code = 200
    
    connector = WebhookConnector(url="https://fake-webhook.io/test")
    success = connector.send(test_event)
    
    assert success
    mock_post.assert_called_once()
    # 驗證 POST 參數
    args, kwargs = mock_post.call_args
    assert "https://fake-webhook.io/test" == args[0]
    assert "json" in kwargs["headers"]["Content-Type"]

@patch("requests.post")
def test_webhook_send_failure(mock_post, test_event):
    """驗證 Webhook 伺服器錯誤場景。"""
    mock_post.return_value.status_code = 500
    
    connector = WebhookConnector(url="https://fake-webhook.io/error")
    success = connector.send(test_event)
    
    assert not success

@patch("requests.post")
def test_webhook_connection_error(mock_post, test_event):
    """驗證網路逾時或連線中斷場景。"""
    mock_post.side_effect = Exception("Timeout")
    
    connector = WebhookConnector(url="https://fake-webhook.io/timeout")
    success = connector.send(test_event)
    
    assert not success

def test_connector_disabled(test_event):
    """驗證 Connector 停用時不會發送。"""
    connector = WebhookConnector(url="http://any.com", enabled=False)
    with patch("requests.post") as mock_post:
        success = connector.send(test_event)
        assert not success
        mock_post.assert_not_called()
