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
    )

    with patch("argparse.ArgumentParser.parse_args", return_value=args):
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            try:
                ci_gate.main()
            except SystemExit:
                pass
            mock_exit.assert_called_with(1)
