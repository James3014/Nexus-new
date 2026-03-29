import pytest
from unittest.mock import MagicMock, patch
from scripts.nexus_cli import NexusCLI

@pytest.fixture
def cli(tmp_path):
    return NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")

def test_cli_bug_dispatch(cli):
    mock_service = MagicMock()
    mock_service.execute_bug.return_value = True
    mock_service.last_completion_error = None
    cli._service = mock_service
    
    # Run the command
    cli.run_bug(task="test-bug", delivery_mode="high", verify_commands=["/bin/echo ok"])
    
    # Verify dispatch
    mock_service.execute_bug.assert_called_once_with(
        "test-bug",
        False,
        delivery_mode="high",
        verify_commands=["/bin/echo ok"],
        artifact_paths=None,
    )

def test_command_service_exists():
    from nexus.app.command_service import NexusCommandService
    assert NexusCommandService is not None


def test_cli_bug_prints_delivery_summary(cli, capsys, tmp_path):
    mock_service = MagicMock()
    mock_service.execute_bug.return_value = True
    mock_service.last_completion_error = None
    mock_service.last_effective_verify_commands = ["/bin/echo ok"]
    mock_service.last_completion_report_paths = (tmp_path / "r.json", tmp_path / "r.md")
    cli._service = mock_service

    cli.run_bug(task="test-bug", delivery_mode="high", verify_commands=["/bin/echo ok"])

    output = capsys.readouterr().out
    assert "Verification Commands" in output
    assert "/bin/echo ok" in output
    assert "Delivery Reports" in output


def test_cli_phase6_dispatches_runner(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    with patch("scripts.engine.nexus_cli.subprocess.call", return_value=0) as mock_call:
        rc = cli.run_phase6_research(
            workspace="/tmp/autoresearch",
            rounds=50,
            proof_ratio_min=95.0,
            output_prefix="phase6",
            skip_autopilot=True,
        )
    assert rc == 0
    invoked = mock_call.call_args[0][0]
    assert "phase6_research.py" in " ".join(invoked)
    assert "--workspace" in invoked
    assert "--skip-autopilot" in invoked


def test_cli_profile_apply_writes_prod_defaults(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    rc = cli.run_profile(action="apply", name="prod")
    assert rc == 0
    assert cli.profile_path.exists()
    payload = cli.profile_path.read_text(encoding="utf-8")
    assert '"name": "prod"' in payload
    assert '"delivery_mode": "high"' in payload


def test_cli_release_ready_dispatches_gate_script(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    gate_script = tmp_path / "scripts" / "ops" / "nexus_release_gate.sh"
    acceptance_script = tmp_path / "scripts" / "ops" / "nexus_acceptance_check.py"
    gate_script.parent.mkdir(parents=True, exist_ok=True)
    gate_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    acceptance_script.write_text("print('ok')\n", encoding="utf-8")
    with patch("scripts.engine.nexus_cli.subprocess.call", return_value=0) as mock_call:
        rc = cli.run_release_ready()
    assert rc == 0
    first_called = mock_call.call_args_list[0][0][0]
    assert str(gate_script) in first_called[0]


def test_cli_skills_autotune_dispatches_runner(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    with patch("scripts.engine.nexus_cli.subprocess.call", return_value=0) as mock_call:
        rc = cli.run_skills_autotune(
            apply=True,
            min_samples=5,
            baseline=0.6,
            learning_rate=0.4,
        )
    assert rc == 0
    invoked = mock_call.call_args[0][0]
    assert "skills_autotune.py" in " ".join(invoked)
    assert "--apply" in invoked
    assert "--min-samples" in invoked


def test_cli_phase7_dispatches_runner(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    with patch("scripts.engine.nexus_cli.subprocess.call", return_value=0) as mock_call:
        rc = cli.run_phase7_research(
            workspace="/tmp/autoresearch",
            rounds=40,
            proof_ratio_min=95.0,
            output_prefix="phase7",
            skip_autopilot=True,
            autotune_apply=True,
            min_samples=4,
            baseline=0.6,
            learning_rate=0.5,
        )
    assert rc == 0
    invoked = mock_call.call_args[0][0]
    assert "phase7_research.py" in " ".join(invoked)
    assert "--workspace" in invoked
    assert "--skip-autopilot" in invoked
    assert "--autotune-apply" in invoked


def test_cli_skills_health_dispatches_runner(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    with patch("scripts.engine.nexus_cli.subprocess.call", return_value=0) as mock_call:
        rc = cli.run_skills_health(output="json", workspace="/tmp/autoresearch")
    assert rc == 0
    invoked = mock_call.call_args[0][0]
    assert "skills_health.py" in " ".join(invoked)
    assert "--output" in invoked
    assert "--workspace" in invoked


def test_cli_skills_optimize_dispatches_runner(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    with patch("scripts.engine.nexus_cli.subprocess.call", return_value=0) as mock_call:
        rc = cli.run_skills_optimize(max_items=2, rebound=0.2)
    assert rc == 0
    invoked = mock_call.call_args[0][0]
    assert "skills_optimization_runner.py" in " ".join(invoked)
    assert "--max-items" in invoked
    assert "--rebound" in invoked


def test_cli_bug_prod_profile_requires_release_ready(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    cli.runtime_profile = {"name": "prod"}
    mock_service = MagicMock()
    mock_service.execute_bug.return_value = True
    mock_service.last_completion_error = None
    mock_service.last_effective_verify_commands = []
    mock_service.last_completion_report_paths = None
    cli._service = mock_service
    with patch.object(cli, "run_release_ready", return_value=1):
        ok = cli.run_bug(task="test-bug", delivery_mode="standard")
    assert ok is False
    assert cli.service.last_completion_error == "release_ready_gate_failed"
