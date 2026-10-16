import sys
from pathlib import Path

# The module was archived in #2373 (repo root -> docs/archive/root-2026-10).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs" / "archive" / "root-2026-10"))
from login_service import LoginService  # noqa: E402


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
