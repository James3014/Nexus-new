import json

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
    report_path = tmp_path / "reports" / "swarm_report.json"
    res = runner.invoke(root, ["swarm", "run", "fix queue race", "--delivery-mode", "high", "--report-file", str(report_path)])

    assert res.exit_code == 0, res.output
    assert captured["task"] == "fix queue race"
    assert captured["kwargs"]["delivery_mode"] == "high"
    assert captured["kwargs"]["bug_id"].startswith("swarm_fix_queue_race")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["semantic_status"] == "VERIFIED"
    assert report["runtime_classification"] == "verified_pass"
    assert report["execution_path"] == "cli->legacy_cli_service->command_service->engine"


def test_swarm_run_exception_still_writes_completion_contract(monkeypatch, tmp_path):
    class _FakeLegacyService:
        def execute_bug(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(swarm_cmd, "build_legacy_cli_service", lambda project_root: _FakeLegacyService())

    @click.group()
    def root():
        pass

    swarm_cmd.register(root, tmp_path)

    runner = CliRunner()
    report_path = tmp_path / "reports" / "swarm_report_fail.json"
    res = runner.invoke(root, ["swarm", "run", "fix queue race", "--report-file", str(report_path)])

    assert res.exit_code != 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["semantic_status"] == "UNVERIFIED"
    assert report["blocker_type"] == "runtime_defect"
    assert "swarm_exception:RuntimeError" in report["semantic_failures"]


def test_swarm_quiet_moment_cli_emits_non_mutating_packet(tmp_path):
    @click.group()
    def root():
        pass

    swarm_cmd.register(root, tmp_path)

    runner = CliRunner()
    res = runner.invoke(
        root,
        [
            "swarm",
            "quiet-moment",
            "--reason",
            "shadow promotion boundary",
            "--node",
            "pilot-a",
            "--resume-after",
            "12",
            "--output-json",
        ],
    )

    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["schema_version"] == "nexus_quiet_moment.v1"
    assert payload["production_writes_allowed"] is False
    assert payload["allowed_actions"] == ["observe", "report", "rollback"]
    assert payload["affected_nodes"] == ["pilot-a"]
    assert payload["resume_after_seconds"] == 12
