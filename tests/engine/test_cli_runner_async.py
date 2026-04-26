from pathlib import Path


def test_execute_tactical_node_routes_bug_tasks_to_canonical_service(monkeypatch, tmp_path):
    from nexus.engine.cli_runner_async import execute_tactical_node

    captured = {}

    class _FakeService:
        def __init__(self, _engine):
            pass

        def execute_bug(self, request):
            captured["kind"] = "bug"
            captured["task"] = request.task
            return True

        def execute_feature(self, request):
            captured["kind"] = "feature"
            captured["task"] = request.task
            return True

    monkeypatch.setattr("nexus.app.command_service.NexusCommandService", _FakeService)
    monkeypatch.setattr("nexus.engine.coordinator.NexusEngine", lambda _config: object())

    class _Node:
        node_id = "T1"
        intent = "fix deadlock"
        envelope = None

    ok = execute_tactical_node(_Node(), Path(tmp_path))
    assert ok is True
    assert captured == {"kind": "bug", "task": "fix deadlock"}


def test_execute_tactical_node_routes_feature_tasks_to_canonical_service(monkeypatch, tmp_path):
    from nexus.engine.cli_runner_async import execute_tactical_node

    captured = {}

    class _FakeService:
        def __init__(self, _engine):
            pass

        def execute_bug(self, request):
            captured["kind"] = "bug"
            captured["task"] = request.task
            return True

        def execute_feature(self, request):
            captured["kind"] = "feature"
            captured["task"] = request.task
            return True

    monkeypatch.setattr("nexus.app.command_service.NexusCommandService", _FakeService)
    monkeypatch.setattr("nexus.engine.coordinator.NexusEngine", lambda _config: object())

    class _Node:
        node_id = "T2"
        intent = "build a dashboard"
        envelope = None

    ok = execute_tactical_node(_Node(), Path(tmp_path))
    assert ok is True
    assert captured == {"kind": "feature", "task": "build a dashboard"}
