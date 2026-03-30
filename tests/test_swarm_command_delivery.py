from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.engine.commands import swarm


def test_swarm_command_uses_service_with_delivery_args(capsys):
    cli = MagicMock()
    cli.service.execute_bug.return_value = True
    cli._print_delivery_summary = MagicMock()
    args = SimpleNamespace(
        task="repair cluster drift",
        delivery_mode="high",
        verify=["/bin/echo ok"],
        artifact=["dist/report.json"],
        verbose_prompt=False,
    )

    swarm.execute(cli, args)

    cli.service.execute_bug.assert_called_once_with(
        "repair cluster drift",
        delivery_mode="high",
        verify_commands=["/bin/echo ok"],
        artifact_paths=["dist/report.json"],
    )
    cli._print_delivery_summary.assert_called_once_with("Swarm", "high")
    output = capsys.readouterr().out
    assert "Mission Succeeded" in output
