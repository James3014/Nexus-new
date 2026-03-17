import pytest
from unittest.mock import MagicMock, patch
from scripts.nexus_cli import NexusCLI

@pytest.fixture
def cli(tmp_path):
    return NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")

def test_cli_bug_dispatch(cli):
    # Mock the engine
    mock_engine = MagicMock()
    cli._engine = mock_engine
    
    # Run the command
    cli.run_bug(task="test-bug")
    
    # Verify dispatch
    mock_engine.run_bug.assert_called_once()
    args, kwargs = mock_engine.run_bug.call_args
    assert kwargs["desc"] == "test-bug"

def test_command_service_exists():
    from nexus.app.command_service import NexusCommandService
    assert NexusCommandService is not None
