from pathlib import Path


def test_cli_commands_service_bug_uses_legacy_service_adapter(monkeypatch, tmp_path):
    from nexus.services.cli_commands_service import CliCommandsService

    captured = {}

    class _FakeLegacyService:
        def execute_bug(self, task, **kwargs):
            captured["task"] = task
            captured["kwargs"] = kwargs
            return True

        def execute_feature(self, task, **kwargs):
            raise AssertionError("feature path should not be used")

    monkeypatch.setattr(
        "nexus.services.cli_commands_service.build_legacy_cli_service",
        lambda repo_root: _FakeLegacyService(),
    )

    facade = CliCommandsService(Path(tmp_path))
    assert facade.bug("fix race", dry_run=True) is True
    assert captured["task"] == "fix race"
    assert captured["kwargs"]["plan_only"] is True


def test_cli_commands_service_feature_uses_legacy_service_adapter(monkeypatch, tmp_path):
    from nexus.services.cli_commands_service import CliCommandsService

    captured = {}

    class _FakeLegacyService:
        def execute_bug(self, task, **kwargs):
            raise AssertionError("bug path should not be used")

        def execute_feature(self, task, **kwargs):
            captured["task"] = task
            captured["kwargs"] = kwargs
            return True

    monkeypatch.setattr(
        "nexus.services.cli_commands_service.build_legacy_cli_service",
        lambda repo_root: _FakeLegacyService(),
    )

    facade = CliCommandsService(Path(tmp_path))
    assert facade.feature("build dashboard") is True
    assert captured["task"] == "build dashboard"


def test_cli_commands_service_heartbeat_test_uses_one_pass_snapshot(monkeypatch, tmp_path):
    from nexus.services.cli_commands_service import CliCommandsService

    captured = {}

    class _FakeDaemon:
        def __init__(self, watch_dir):
            captured["watch_dir"] = watch_dir

        def scan_once(self):
            captured["scan_once"] = captured.get("scan_once", 0) + 1
            return {"schema": "nexus.paperclip_heartbeat_snapshot.v1", "status": "OK"}

        def monitor(self):
            raise AssertionError("test heartbeat must not enter monitor")

    monkeypatch.setattr("scripts.ops.paperclip.PaperclipDaemon", _FakeDaemon)
    facade = object.__new__(CliCommandsService)
    facade.repo_root = tmp_path

    result = facade.heartbeat(test=True)

    assert result == {"schema": "nexus.paperclip_heartbeat_snapshot.v1", "status": "OK"}
    assert captured["watch_dir"] == tmp_path / ".nexus" / "heartbeats"
    assert captured["scan_once"] == 1


def test_cli_commands_service_heartbeat_non_test_preserves_monitor_dispatch(monkeypatch, tmp_path):
    from nexus.services.cli_commands_service import CliCommandsService

    captured = {}

    class _FakeDaemon:
        def __init__(self, watch_dir):
            captured["watch_dir"] = watch_dir

        def scan_once(self):
            raise AssertionError("non-test heartbeat must not use one-pass mode")

        def monitor(self):
            captured["monitor"] = captured.get("monitor", 0) + 1
            return "monitor-result"

    monkeypatch.setattr("scripts.ops.paperclip.PaperclipDaemon", _FakeDaemon)
    facade = object.__new__(CliCommandsService)
    facade.repo_root = tmp_path

    assert facade.heartbeat(test=False) == "monitor-result"
    assert captured["monitor"] == 1
