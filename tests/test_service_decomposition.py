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
    # ARCHIVED 2026-10-13 legacy-engine (ARCHIVED_2026-10-13-legacy-engine.md): the facade wrapped
    # the retired legacy NexusEngine and now fails closed at construction.
    from nexus.engine.canonical_task_seam import LegacyEngineArchivedError
    from nexus.services.cli_commands_service import CliCommandsService
    with pytest.raises(LegacyEngineArchivedError):
        CliCommandsService(Path("."))
