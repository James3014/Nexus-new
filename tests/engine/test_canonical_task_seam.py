from pathlib import Path


def test_build_command_service_constructs_engine_once(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import build_command_service

    captured = {}

    class _FakeEngineConfig:
        def __init__(self, project_root):
            captured["config_project_root"] = project_root

    class _FakeEngine:
        def __init__(self, config):
            captured["engine_config"] = config

    class _FakeService:
        def __init__(self, engine):
            captured["service_engine"] = engine

    monkeypatch.setattr("nexus.engine.config.EngineConfig", _FakeEngineConfig)
    monkeypatch.setattr("nexus.engine.coordinator.NexusEngine", _FakeEngine)
    monkeypatch.setattr("nexus.app.command_service.NexusCommandService", _FakeService)

    service = build_command_service(tmp_path)

    assert isinstance(service, _FakeService)
    assert captured["config_project_root"] == tmp_path
    assert captured["service_engine"] is not None


def test_build_engine_passes_config_overrides(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import build_engine

    captured = {}

    class _FakeEngineConfig:
        def __init__(self, project_root, **kwargs):
            captured["project_root"] = project_root
            captured["kwargs"] = kwargs

    class _FakeEngine:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr("nexus.engine.config.EngineConfig", _FakeEngineConfig)
    monkeypatch.setattr("nexus.engine.coordinator.NexusEngine", _FakeEngine)

    engine = build_engine(tmp_path, benchmark_mode=True, silent=True)

    assert isinstance(engine, _FakeEngine)
    assert captured["project_root"] == tmp_path
    assert captured["kwargs"] == {"benchmark_mode": True, "silent": True}


def test_execute_single_task_via_service_uses_build_command_service(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import execute_single_task_via_service

    called = {}

    class _FakeService:
        def execute_bug(self, request):
            called["kind"] = "bug"
            called["task"] = request.task
            return True

        def execute_feature(self, request):
            called["kind"] = "feature"
            called["task"] = request.task
            return True

    def _fake_build_command_service(project_root):
        called["project_root"] = project_root
        return _FakeService()

    monkeypatch.setattr("nexus.engine.canonical_task_seam.build_command_service", _fake_build_command_service)

    ok = execute_single_task_via_service("fix race", tmp_path)

    assert ok is True
    assert called["project_root"] == tmp_path
    assert called["kind"] == "bug"
    assert called["task"] == "fix race"


def test_build_legacy_cli_service_shapes_bug_request(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import build_legacy_cli_service

    captured = {}

    class _FakeCommandService:
        def execute_bug(self, request):
            captured["request"] = request
            return True

        def execute_feature(self, request):
            raise AssertionError("feature path should not be used")

    monkeypatch.setattr(
        "nexus.engine.canonical_task_seam.build_command_service",
        lambda project_root: _FakeCommandService(),
    )

    service = build_legacy_cli_service(tmp_path)
    ok = service.execute_bug(
        "fix bug",
        delivery_mode="high",
        bug_id="BUG-1",
        verify_commands=["pytest -q"],
        artifact_paths=["report.json"],
        plan_only=True,
    )

    assert ok is True
    request = captured["request"]
    assert request.task == "fix bug"
    assert request.task_id == "BUG-1"
    assert request.delivery_mode == "high"
    assert request.verify_commands == ["pytest -q"]
    assert request.artifact_paths == ["report.json"]
    assert request.plan_only is True


def test_build_legacy_cli_service_shapes_feature_request(monkeypatch, tmp_path):
    from nexus.engine.canonical_task_seam import build_legacy_cli_service

    captured = {}

    class _FakeCommandService:
        def execute_bug(self, request):
            raise AssertionError("bug path should not be used")

        def execute_feature(self, request):
            captured["request"] = request
            return True

    monkeypatch.setattr(
        "nexus.engine.canonical_task_seam.build_command_service",
        lambda project_root: _FakeCommandService(),
    )

    service = build_legacy_cli_service(tmp_path)
    ok = service.execute_feature(
        "build dashboard",
        domain="frontend",
        delivery_mode="standard",
        verify_commands=["pytest -q tests/ui"],
    )

    assert ok is True
    request = captured["request"]
    assert request.task == "build dashboard"
    assert request.domain == "frontend"
    assert request.delivery_mode == "standard"
    assert request.verify_commands == ["pytest -q tests/ui"]
