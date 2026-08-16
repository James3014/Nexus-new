from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.external_intelligence_service import (
    ServiceConfig,
    ServiceError,
    load_config,
    plist_xml,
    render_comment,
    run_once,
)


class FakeGh:
    def __init__(self, issues):
        self.issues = issues
        self.comments = []
        self.calls = []

    def list_open_labeled(self, repository, label):
        self.calls.append((repository, label))
        return list(self.issues.get(repository, []))

    def comment(self, repository, issue_number, body):
        self.comments.append((repository, issue_number, body))


class FakeAutomation:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run_issue(self, repository, issue_number, title, body):
        self.calls.append((repository, issue_number, title, body))
        return dict(self.result)


def _config(tmp_path, **overrides):
    values = dict(
        repositories=("o/r",),
        repository_roots={"o/r": str(tmp_path / "repo")},
        state_root=tmp_path / "state",
        workspace_root=tmp_path / "workspaces",
        opencli_profile="test-profile",
        opencode_executable="/tmp/opencode",
    )
    values.update(overrides)
    return ServiceConfig(**values)


def _complete(reuse=False):
    return {
        "state": "COMPLETE",
        "reuse": reuse,
        "publication": {
            "task_id": "t1",
            "candidate_commit": "a" * 40,
            "candidate_tree": "b" * 40,
            "verification_state": "PASS",
            "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
            "acceptance_packet_ref": "state/a.json",
            "acceptance_packet_sha256": "c" * 64,
            "next_action": "independent_acceptance",
            "stop_condition": "acceptance_failed",
            "claim_ceiling": "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE",
        },
    }


def test_load_config_is_strict_and_profile_is_configurable(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "repositories": ["o/r"],
        "repository_roots": {"o/r": str(tmp_path / "repo")},
        "state_root": str(tmp_path / "state"),
        "workspace_root": str(tmp_path / "workspaces"),
        "opencli_profile": "profile-alias",
    }), encoding="utf-8")
    loaded = load_config(cfg)
    assert loaded.opencli_profile == "profile-alias"
    assert loaded.opencode_executable == "opencode"
    raw = json.loads(cfg.read_text())
    raw["secret_surprise"] = True
    cfg.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ServiceError):
        load_config(cfg)


def test_run_once_processes_at_most_one_issue_and_publishes_compact_result(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": [
        {"number": 2, "title": "later", "body": "b"},
        {"number": 1, "title": "first", "body": "a"},
    ]})
    automation = FakeAutomation(_complete())
    result = run_once(config, gh=gh, automation_factory=lambda _c, _r: automation)
    assert result["issue_number"] == 1
    assert len(automation.calls) == 1
    assert len(gh.comments) == 1
    body = gh.comments[0][2]
    assert "External Intelligence automation completed" in body
    assert "envelope" not in body.lower()
    assert "prompt" not in body.lower()


def test_reused_completion_does_not_duplicate_comment(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": [{"number": 1, "title": "first", "body": "a"}]})
    automation = FakeAutomation(_complete(reuse=True))
    result = run_once(config, gh=gh, automation_factory=lambda _c, _r: automation)
    assert result["status"] == "COMPLETE"
    assert gh.comments == []


def test_run_once_skips_reused_issue_to_reach_eligible_next(tmp_path):
    config = _config(tmp_path)
    calls = []

    class SequencedAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return _complete(reuse=True)
            return _complete()

    gh = FakeGh({"o/r": [
        {"number": 2, "title": "eligible", "body": "b"},
        {"number": 1, "title": "already-done", "body": "a"},
    ]})
    result = run_once(config, gh=gh, automation_factory=lambda _c, _r: SequencedAutomation())
    assert calls == [1, 2]
    assert result["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2


def test_run_once_skips_pre_dispatch_blocked_issue_to_reach_eligible_next(tmp_path):
    config = _config(tmp_path)
    calls = []

    class SequencedAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return {"state": "BLOCKED", "error": "TASK_CARD_HASH_MISMATCH", "semantic_dispatched": False}
            return _complete()

    gh = FakeGh({"o/r": [
        {"number": 2, "title": "eligible", "body": "b"},
        {"number": 1, "title": "blocked", "body": "a"},
    ]})
    result = run_once(config, gh=gh, automation_factory=lambda _c, _r: SequencedAutomation())
    assert calls == [1, 2]
    assert result["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2


def test_run_once_skips_source_lineage_blocked_issue_to_reach_eligible_next(tmp_path):
    config = _config(tmp_path)
    calls = []

    class SequencedAutomation:
        def run_issue(self, repository, issue_number, title, body):
            calls.append(issue_number)
            if issue_number == 1:
                return {"state": "BLOCKED", "error": "MAIN_SHA_LINEAGE_MISMATCH", "semantic_dispatched": False}
            return _complete()

    gh = FakeGh({"o/r": [
        {"number": 2, "title": "eligible", "body": "b"},
        {"number": 1, "title": "blocked-lineage", "body": "a"},
    ]})
    result = run_once(config, gh=gh, automation_factory=lambda _c, _r: SequencedAutomation())
    assert calls == [1, 2]
    assert result["issue_number"] == 2
    assert len(gh.comments) == 1
    assert gh.comments[0][1] == 2


def test_idle_when_no_labeled_issue(tmp_path):
    config = _config(tmp_path)
    gh = FakeGh({"o/r": []})
    assert run_once(config, gh=gh, automation_factory=lambda _c, _r: None) == {"status": "IDLE"}
    assert gh.calls == [("o/r", "nexus:external-intelligence")]


def test_publication_disabled_never_comments(tmp_path):
    config = _config(tmp_path, publication_enabled=False)
    gh = FakeGh({"o/r": [{"number": 1, "title": "first", "body": "a"}]})
    automation = FakeAutomation(_complete())
    run_once(config, gh=gh, automation_factory=lambda _c, _r: automation)
    assert gh.comments == []


def test_plist_is_local_launchagent_daemon_and_has_no_hardcoded_profile(tmp_path):
    xml = plist_xml(tmp_path / "config.json")
    assert "com.nexus.external-intelligence" in xml
    assert "external_intelligence_service" in xml
    assert "daemon" in xml
    assert "64b57tak" not in xml
    assert "/Users/jameschen/.opencode/bin" in xml


def test_render_comment_contains_only_compact_fields():
    result = _complete()
    result["raw_prompt"] = "SECRET_PROMPT"
    result["envelope"] = {"secret": "SECRET_ENVELOPE"}
    body = render_comment(result)
    assert "SECRET_PROMPT" not in body
    assert "SECRET_ENVELOPE" not in body
    assert "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE" in body
