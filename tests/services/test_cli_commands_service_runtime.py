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
