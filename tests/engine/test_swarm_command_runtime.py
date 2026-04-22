import click
from click.testing import CliRunner

from scripts.engine.commands import swarm as swarm_cmd


def test_swarm_run_uses_legacy_service_adapter(monkeypatch, tmp_path):
    captured = {}

    class _FakeLegacyService:
        def execute_bug(self, task, **kwargs):
            captured["task"] = task
            captured["kwargs"] = kwargs
            return True

    monkeypatch.setattr(swarm_cmd, "build_legacy_cli_service", lambda project_root: _FakeLegacyService())

    @click.group()
    def root():
        pass

    swarm_cmd.register(root, tmp_path)

    runner = CliRunner()
    res = runner.invoke(root, ["swarm", "run", "fix queue race", "--delivery-mode", "high"])

    assert res.exit_code == 0, res.output
    assert captured["task"] == "fix queue race"
    assert captured["kwargs"]["delivery_mode"] == "high"
    assert captured["kwargs"]["bug_id"].startswith("swarm_fix_queue_race")
