import pytest
from login_service import LoginService

def test_login_success():
    service = LoginService()
    result = service.login("admin", "password123")
    assert result["status"] == "success"
    assert result["message"] == "Welcome back"
    assert result["redirect"] == "/dashboard"

def test_login_invalid_credentials():
    service = LoginService()
    result = service.login("admin", "wrongpassword")
    assert result["status"] == "error"
    assert "Invalid" in result["message"]
