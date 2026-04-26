import pytest
from unittest.mock import MagicMock, patch
from nexus.app.command_service import TaskRequest

def test_command_service_exists():
    from nexus.app.command_service import NexusCommandService
    assert NexusCommandService is not None





def test_command_service_bridges_engine(tmp_path):
    """NexusCommandService 應是 CLI 與 Engine 之間的橋接層。"""
    from nexus.app.command_service import NexusCommandService
    mock_engine = MagicMock()
    mock_engine.run_bug.return_value = True
    mock_engine.project_root = tmp_path
    mock_engine.run_dir = tmp_path / "runs"
    svc = NexusCommandService(engine=mock_engine)

    svc.execute_bug(TaskRequest(task="修復 DB 連線問題"))

    mock_engine.run_bug.assert_called_once()
