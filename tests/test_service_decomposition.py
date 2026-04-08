import pytest
from pathlib import Path

def test_aos_service_standalone():
    # 嘗試導入尚未建立的子服務
    try:
        from nexus.services.aos_service import AosService
        service = AosService(Path("."))
        assert hasattr(service, "get_status")
    except ImportError:
        pytest.fail("AosService module does not exist yet")

def test_cli_facade_redirection():
    # 驗證原本的 CliCommandsService 是否能透過 Facade 模式調用子服務
    from nexus.services.cli_commands_service import CliCommandsService
    facade = CliCommandsService(Path("."))
    # 目前 get_status 是實作在 CliCommandsService 內的，我們要重構它
    assert facade.status is not None
