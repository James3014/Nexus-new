import argparse
import subprocess
from unittest.mock import patch

from scripts.ops import ci_gate


def test_run_closeout_contract_check_pass(monkeypatch):
    class MockRes:
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockRes())
    assert ci_gate.run_closeout_contract_check(dry_run=True, contract_path=".nexus/reports/done_contract.json") is True


def test_run_closeout_contract_check_fail(monkeypatch):
    class MockRes:
        returncode = 1

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockRes())
    assert ci_gate.run_closeout_contract_check(dry_run=False, contract_path=".nexus/reports/done_contract.json") is False


def test_run_optimization_artifact_hygiene_check_pass(monkeypatch):
    class MockRes:
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockRes())
    assert ci_gate.run_optimization_artifact_hygiene_check(
        read_model_path=".nexus/reports/read_model.json",
        retention_manifest_path=".nexus/reports/retention.json",
        dry_run=True,
    ) is True


def test_run_optimization_artifact_hygiene_check_fail(monkeypatch):
    class MockRes:
        returncode = 1

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockRes())
    assert ci_gate.run_optimization_artifact_hygiene_check(
        read_model_path=".nexus/reports/read_model.json",
        dry_run=False,
    ) is False


def test_run_route_context_seam_freeze_check_pass(monkeypatch):
    class MockRes:
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockRes())
    assert ci_gate.run_route_context_seam_freeze_check(
        freeze_path=".nexus/reports/route_context_freeze.json",
        dry_run=True,
    ) is True


def test_run_route_context_seam_freeze_check_fail(monkeypatch):
    class MockRes:
        returncode = 1

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockRes())
    assert ci_gate.run_route_context_seam_freeze_check(
        freeze_path=".nexus/reports/route_context_freeze.json",
        dry_run=False,
    ) is False


def test_cleanup_ci_transient_artifacts_restores_only_tracked_known_paths(monkeypatch, tmp_path):
    tracked = ".nexus/reports/learn/learning_closure.jsonl"
    untracked = "wiki_audit.json"
    for rel_path in (tracked, untracked):
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")

    restored = []

    class MockRes:
        def __init__(self, returncode=0, stderr=""):
            self.returncode = returncode
            self.stderr = stderr

    def fake_run(cmd, *args, **kwargs):
        rel_path = str(cmd[-1])
        if "ls-files" in cmd:
            return MockRes(0 if rel_path == tracked else 1)
        if "restore" in cmd:
            restored.append(rel_path)
            return MockRes(0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    monkeypatch.setattr(ci_gate, "CI_TRANSIENT_ARTIFACTS", (tracked, untracked))
    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = ci_gate.cleanup_ci_transient_artifacts()

    assert summary["status"] == "PASS"
    assert summary["restored_paths"] == [tracked]
    assert summary["skipped_untracked_paths"] == [untracked]
    assert restored == [tracked]


def test_cleanup_ci_transient_artifacts_dry_run_plans_without_restore(monkeypatch, tmp_path):
    tracked = "wiki_audit.json"
    (tmp_path / tracked).write_text("generated\n", encoding="utf-8")

    class MockRes:
        returncode = 0

    def fake_run(cmd, *args, **kwargs):
        assert "restore" not in cmd
        return MockRes()

    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    monkeypatch.setattr(ci_gate, "CI_TRANSIENT_ARTIFACTS", (tracked,))
    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = ci_gate.cleanup_ci_transient_artifacts(dry_run=True)

    assert summary["status"] == "PASS"
    assert summary["planned_paths"] == [tracked]
    assert summary["restored_paths"] == []


def test_cleanup_ci_transient_artifacts_returns_on_restore_error(monkeypatch, tmp_path):
    tracked = "wiki_audit.json"
    (tmp_path / tracked).write_text("generated\n", encoding="utf-8")

    class MockRes:
        def __init__(self, returncode=0, stderr=""):
            self.returncode = returncode
            self.stderr = stderr

    def fake_run(cmd, *args, **kwargs):
        if "ls-files" in cmd:
            return MockRes(0)
        if "restore" in cmd:
            return MockRes(1, "restore failed")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    monkeypatch.setattr(ci_gate, "CI_TRANSIENT_ARTIFACTS", (tracked,))
    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = ci_gate.cleanup_ci_transient_artifacts()

    assert summary["status"] == "RETURN"
    assert summary["errors"][0]["path"] == tracked


def test_ci_gate_dry_run_blocks_when_closeout_contract_fails(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_dry_run", lambda: 0)
    monkeypatch.setattr(ci_gate, "run_closeout_contract_check", lambda dry_run, contract_path: False)

    args = argparse.Namespace(
        dry_run=True,
        strict=False,
        wiki_drift_enforce_level="warn",
        wiki_capability_enforce_level="warn",
        wiki_eval_enforce_level="warn",
        require_closeout_contract=True,
        closeout_contract_path=".nexus/reports/done_contract.json",
        optimization_read_model="",
        optimization_retention_manifest="",
        route_context_freeze="",
    )

    with patch("argparse.ArgumentParser.parse_args", return_value=args):
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            try:
                ci_gate.main()
            except SystemExit:
                pass
            mock_exit.assert_called_with(1)


def test_ci_gate_non_dry_run_exits_when_closeout_contract_fails(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_protocol_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_lesson_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_wiki_sync_check", lambda dry_run: "OK")
    monkeypatch.setattr(ci_gate, "run_step", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr(ci_gate, "print_phase_6_summaries", lambda *args, **kwargs: None)
    monkeypatch.setattr(ci_gate, "run_closeout_contract_check", lambda dry_run, contract_path: False)

    args = argparse.Namespace(
        dry_run=False,
        strict=False,
        wiki_drift_enforce_level="warn",
        wiki_capability_enforce_level="warn",
        wiki_eval_enforce_level="warn",
        require_closeout_contract=True,
        closeout_contract_path=".nexus/reports/done_contract.json",
        optimization_read_model="",
        optimization_retention_manifest="",
        route_context_freeze="",
    )

    with patch("argparse.ArgumentParser.parse_args", return_value=args):
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            try:
                ci_gate.main()
            except SystemExit:
                pass
            mock_exit.assert_called_with(1)


def test_ci_gate_dry_run_blocks_when_optimization_hygiene_fails(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_dry_run", lambda: 0)
    monkeypatch.setattr(ci_gate, "run_optimization_artifact_hygiene_check", lambda **kwargs: False)

    args = argparse.Namespace(
        dry_run=True,
        strict=False,
        wiki_drift_enforce_level="warn",
        wiki_capability_enforce_level="warn",
        wiki_eval_enforce_level="warn",
        require_closeout_contract=False,
        closeout_contract_path=".nexus/reports/done_contract.json",
        optimization_read_model=".nexus/reports/read_model.json",
        optimization_retention_manifest=".nexus/reports/retention.json",
        route_context_freeze="",
    )

    with patch("argparse.ArgumentParser.parse_args", return_value=args):
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            try:
                ci_gate.main()
            except SystemExit:
                pass
            mock_exit.assert_called_with(1)


def test_ci_gate_dry_run_blocks_when_route_context_freeze_fails(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_dry_run", lambda: 0)
    monkeypatch.setattr(ci_gate, "run_route_context_seam_freeze_check", lambda **kwargs: False)

    args = argparse.Namespace(
        dry_run=True,
        strict=False,
        wiki_drift_enforce_level="warn",
        wiki_capability_enforce_level="warn",
        wiki_eval_enforce_level="warn",
        require_closeout_contract=False,
        closeout_contract_path=".nexus/reports/done_contract.json",
        optimization_read_model="",
        optimization_retention_manifest="",
        route_context_freeze=".nexus/reports/route_context_freeze.json",
    )

    with patch("argparse.ArgumentParser.parse_args", return_value=args):
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            try:
                ci_gate.main()
            except SystemExit:
                pass
            mock_exit.assert_called_with(1)
