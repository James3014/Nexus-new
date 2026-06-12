import pytest
import urllib.error
from unittest.mock import MagicMock, patch
from nexus.services.local_heal.client import OllamaClient
from nexus.services.local_heal.model_result import classify_model_exception, MODEL_PROVIDER_ERROR

def test_ollama_client_http_error_bubbles_up():
    """驗證 OllamaClient 在遇到 HTTP 500 時會拋出異常，而不是回傳空字串。"""
    client = OllamaClient(model="test-model", endpoint="http://localhost:11434")
    
    # 模擬 HTTP 500 錯誤
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"error": "llama-server binary not found"}'
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=mock_response
        )
        
        with pytest.raises(RuntimeError) as excinfo:
            client.generate("system", "user")
        
        assert "MODEL_PROVIDER_ERROR" in str(excinfo.value)
        assert "llama-server binary not found" in str(excinfo.value)

def test_exception_classification_provider_error():
    """驗證異常分類器會將 RuntimeError 識別為 PROVIDER_ERROR。"""
    exc = RuntimeError("MODEL_PROVIDER_ERROR: something went wrong")
    reason = classify_model_exception(exc)
    assert reason == MODEL_PROVIDER_ERROR
