import argparse
from unittest.mock import patch

from scripts.ops import ci_gate


def test_run_report_trust_audit_uses_expected_pytest_suite(monkeypatch):
    seen = {}

    def fake_run_step(name, cmd):
        seen["name"] = name
        seen["cmd"] = cmd
        return True, "ok"

    monkeypatch.setattr(ci_gate, "run_step", fake_run_step)

    assert ci_gate.run_report_trust_audit(dry_run=False) is True
    assert seen["name"] == "Report Trust Audit"
    for target in (
        "tests/engine/test_canonical_task_seam.py",
        "tests/test_cli_output_contract.py",
        "tests/engine/test_cli_runner_async.py",
        "tests/engine/test_cli_research_seams.py",
        "tests/engine/test_cli_work_path_audit.py",
        "tests/engine/test_cli_artifact_gate_audit.py",
        "tests/research/test_learn_ingest_channels.py",
        "tests/test_cli_learn_mode.py",
        "tests/services/test_cli_commands_service_runtime.py",
        "tests/engine/test_swarm_command_runtime.py",
        "tests/test_v18_legacy_delivery.py",
    ):
        assert target in seen["cmd"]


def test_run_dry_run_blocks_when_report_trust_audit_fails(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_integrity_check", lambda: True)
    monkeypatch.setattr(ci_gate, "run_protocol_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_lesson_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_delivery_tracked_check", lambda dry_run=True: True)
    monkeypatch.setattr(ci_gate, "run_wiki_sync_check", lambda dry_run: "OK")
    monkeypatch.setattr(ci_gate, "print_phase_6_summaries", lambda *args, **kwargs: None)
    monkeypatch.setattr(ci_gate, "run_report_trust_audit", lambda dry_run: False)

    exit_code = ci_gate.run_dry_run()
    assert exit_code == 1


def test_ci_gate_main_blocks_when_report_trust_audit_fails(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_protocol_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_lesson_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_wiki_sync_check", lambda dry_run: "OK")
    monkeypatch.setattr(ci_gate, "run_step", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr(ci_gate, "run_report_trust_audit", lambda dry_run: False)
    monkeypatch.setattr(ci_gate, "print_phase_6_summaries", lambda *args, **kwargs: None)

    args = argparse.Namespace(
        dry_run=False,
        strict=False,
        benchmark_mode="off",
        learn_mode="off",
        learn_topic="nexus",
        wiki_drift_enforce_level="warn",
        wiki_capability_enforce_level="warn",
        wiki_eval_enforce_level="warn",
        require_closeout_contract=False,
        closeout_contract_path=".nexus/reports/done_contract.json",
        auto_heal=False,
    )

    with patch("argparse.ArgumentParser.parse_args", return_value=args):
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            try:
                ci_gate.main()
            except SystemExit:
                pass
            mock_exit.assert_called_with(1)
