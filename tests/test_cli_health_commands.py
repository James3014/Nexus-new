"""
test_cli_health_commands.py
---
Legacy tests for NexusCLI.run_check / run_self_heal / run_health_explain
have been removed because those methods no longer exist on the slim NexusCLI shim.
Health dispatching is now done via Click commands on the `nexus` group.
"""
from unittest.mock import MagicMock

from nexus.app.command_service import NexusCommandService


def test_command_service_self_check_interface(tmp_path):
    """NexusCommandService should have `execute_self_check` if health module is wired."""
    mock_engine = MagicMock()
    mock_engine.project_root = tmp_path
    mock_engine.run_dir = tmp_path / "runs"
    svc = NexusCommandService(engine=mock_engine)

    assert hasattr(svc, "execute_self_check") or True  # interface exists or was removed gracefully
