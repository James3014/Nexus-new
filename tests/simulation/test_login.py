import importlib.util
import sys
from pathlib import Path

# The module was archived in #2373 (repo root -> docs/archive/root-2026-10). Load it by path
# so the archive directory never lands on sys.path (it holds many stale modules).
_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "archive" / "root-2026-10" / "login_service.py"
)
_SPEC = importlib.util.spec_from_file_location("archived_login_service", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE  # dataclasses resolve their module by name
_SPEC.loader.exec_module(_MODULE)
LoginService = _MODULE.LoginService


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
