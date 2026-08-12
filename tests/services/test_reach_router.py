import json
from pathlib import Path


def test_cli_reach_dispatches_to_bound_router_once(monkeypatch, tmp_path):
    from nexus.services.cli_commands_service import CliCommandsService
    from nexus.services.reach.ucc_router import ReachResult

    calls = {}

    class FakeRouter:
        def __init__(self, repo_root=None):
            calls["repo_root"] = repo_root

        def reach(self, url, tier=1):
            calls["reach"] = (url, tier)
            return ReachResult(url=url, resolver="fake", content_type="markdown")

    monkeypatch.setattr("nexus.services.reach.ucc_router.UCCRouter", FakeRouter)
    facade = object.__new__(CliCommandsService)
    facade.repo_root = tmp_path

    result = facade.reach("https://example.test", tier=2)

    assert result.resolver == "fake"
    assert calls == {"repo_root": tmp_path, "reach": ("https://example.test", 2)}


def test_router_persists_snapshot_and_outcome_under_repo_root(monkeypatch, tmp_path):
    from nexus.services.reach.ucc_router import ReachResult, UCCRouter

    captured = {}

    def fake_append(root, event):
        captured["root"] = root
        captured["event"] = event

    monkeypatch.setattr("nexus.core.skill_outcomes.append_skill_outcome_event", fake_append)
    router = UCCRouter(tmp_path)
    result = ReachResult(
        decision_id="decision-145",
        url="https://example.test",
        resolver="fake",
        content_type="markdown",
    )

    router._persist_result(result)
    router._log_outcome(result)

    snapshot = tmp_path / ".nexus" / "reach" / "decision-145.json"
    assert snapshot.is_file()
    assert json.loads(snapshot.read_text())["decision_id"] == "decision-145"
    assert captured["root"] == tmp_path
    assert not (Path.cwd() / ".nexus" / "reach" / snapshot.name).exists()


def test_router_no_arg_compatibility_uses_current_root(monkeypatch, tmp_path):
    from nexus.services.reach.ucc_router import UCCRouter

    monkeypatch.chdir(tmp_path)
    router = UCCRouter()

    assert router.repo_root == tmp_path
