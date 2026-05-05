import argparse
import json
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
        "tests/engine/test_completion_contract.py",
        "tests/engine/test_completion_enforcer.py",
        "tests/engine/test_canonical_task_seam.py",
        "tests/engine/test_direct_mode_semantic_audit.py",
        "tests/engine/test_cli_semantic_contract_audit.py",
        "tests/test_cli_output_contract.py",
        "tests/engine/test_cli_runner_async.py",
        "tests/engine/test_cli_research_seams.py",
        "tests/engine/test_cli_work_path_audit.py",
        "tests/engine/test_cli_artifact_gate_audit.py",
        "tests/engine/test_delegate_completion_contract.py",
        "tests/research/test_learn_ingest_channels.py",
        "tests/test_cli_learn_mode.py",
        "tests/services/test_cli_commands_service_runtime.py",
        "tests/engine/test_swarm_command_runtime.py",
        "tests/test_v18_legacy_delivery.py",
    ):
        assert target in seen["cmd"]


def test_run_changed_only_check_uses_selector_targets(monkeypatch, tmp_path, capsys):
    seen = {}
    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)

    def fake_run_step(name, cmd):
        seen["name"] = name
        seen["cmd"] = cmd
        junit_path = tmp_path / ".nexus" / "reports" / "changed_only_junit.xml"
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        junit_path.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<testsuite>
  <testcase classname="tests.ops.test_select_tests" name="test_a" file="tests/ops/test_select_tests.py" time="0.12"/>
</testsuite>
""",
            encoding="utf-8",
        )
        return True, "ok"

    monkeypatch.setattr(ci_gate, "run_step", fake_run_step)

    assert ci_gate.run_changed_only_check(["scripts/ops/select_tests.py"]) is True
    assert seen["name"] == "Changed-Only JIT Tests"
    assert "tests/ops/test_select_tests.py" in seen["cmd"]
    assert "tests/ops " not in seen["cmd"]
    out = capsys.readouterr().out
    assert "confidence=" in out
    assert "risk=" in out
    history = (tmp_path / ".nexus" / "reports" / "test_history.jsonl").read_text(encoding="utf-8")
    assert '"mode": "changed-only"' in history
    assert "tests/ops/test_select_tests.py" in history
    payload = json.loads(history)
    assert payload["target_durations"]["tests/ops/test_select_tests.py"] == 0.12
    assert payload["metadata"]["selected_count"] >= 1
    selection = json.loads((tmp_path / ".nexus" / "reports" / "changed_only_selection.json").read_text(encoding="utf-8"))
    assert selection["selected_count"] >= 1
    assert selection["targets"][0] == "tests/ops/test_select_tests.py"
    observation = json.loads((tmp_path / ".nexus" / "reports" / "jit_observation.jsonl").read_text(encoding="utf-8"))
    assert observation["event"] == "changed_only"
    assert observation["success"] is True
    assert observation["target_durations"]["tests/ops/test_select_tests.py"] == 0.12


def test_extract_junit_target_durations_aggregates_by_file_and_directory(tmp_path):
    junit_path = tmp_path / "junit.xml"
    junit_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite>
  <testcase classname="tests.ops.test_select_tests" name="test_a" file="tests/ops/test_select_tests.py" time="0.10"/>
  <testcase classname="tests.ops.test_select_tests" name="test_b" file="tests/ops/test_select_tests.py" time="0.20"/>
  <testcase classname="tests.services.test_policy_gate" name="test_c" file="tests/services/test_policy_gate.py" time="0.30"/>
</testsuite>
""",
        encoding="utf-8",
    )

    durations = ci_gate._extract_junit_target_durations(
        junit_path,
        ["tests/ops/test_select_tests.py", "tests/services"],
    )

    assert durations == {
        "tests/ops/test_select_tests.py": 0.3,
        "tests/services": 0.3,
    }


def test_run_nightly_full_check_records_history(monkeypatch, tmp_path):
    monkeypatch.setattr(ci_gate, "ROOT", tmp_path)
    monkeypatch.setattr(ci_gate, "run_step", lambda name, cmd: (True, "ok"))

    assert ci_gate.run_nightly_full_check() is True

    history_path = tmp_path / ".nexus" / "reports" / "test_history.jsonl"
    payload = history_path.read_text(encoding="utf-8").strip()
    assert '"mode": "nightly-full"' in payload
    assert '"success": true' in payload


def test_run_changed_scope_wiki_governance_uses_changed_only(monkeypatch):
    seen = {}

    def fake_run_step(name, cmd):
        seen["name"] = name
        seen["cmd"] = cmd
        return True, "ok"

    monkeypatch.setattr(ci_gate, "run_step", fake_run_step)

    assert ci_gate.run_changed_scope_wiki_governance() is True
    assert seen["name"] == "Changed-Scope Wiki Governance Audit"
    assert "--changed-only" in seen["cmd"]


def test_selected_code_reality_audits_maps_changed_paths():
    selected = ci_gate.selected_code_reality_audits(
        [
            "docs/ops/brain_hub_manifest.json",
            "nexus/core/state_contracts.py",
            "nexus/schemas/hallucination_index_v1.json",
        ]
    )

    assert "Brain Hub Manifest Audit" in selected
    assert "--manifest docs/ops/brain_hub_manifest.json" in selected["Brain Hub Manifest Audit"]
    assert "Strategic Map Audit" in selected
    assert "Hallucination Guard Drift Audit" in selected


def test_run_code_reality_audits_skips_unrelated_changed_paths(monkeypatch):
    calls = []
    monkeypatch.setattr(ci_gate, "run_step", lambda name, cmd: calls.append((name, cmd)) or (True, "ok"))

    assert ci_gate.run_code_reality_audits(["README.md"]) is True

    assert calls == []


def test_run_code_reality_audits_blocks_selected_failure(monkeypatch):
    calls = []

    def fake_run_step(name, cmd):
        calls.append(name)
        return (False, "bad") if name == "Strategic Map Audit" else (True, "ok")

    monkeypatch.setattr(ci_gate, "run_step", fake_run_step)

    assert ci_gate.run_code_reality_audits(["nexus/core/context_hub.py"]) is False
    assert calls == ["Strategic Map Audit"]


def test_ci_gate_main_strict_runs_changed_only_preflight(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_changed_only_check", lambda changed_paths: False)

    args = argparse.Namespace(
        dry_run=False,
        changed_only=None,
        changed_paths=["scripts/ops/select_tests.py"],
        nightly=False,
        strict=True,
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


def test_ci_gate_main_strict_high_risk_runs_ultra_review(monkeypatch):
    calls = []
    monkeypatch.setattr(ci_gate, "run_changed_only_check", lambda changed_paths: True)
    monkeypatch.setattr(ci_gate, "run_ultra_review_check", lambda: calls.append("ultra") or False)
    monkeypatch.setattr(ci_gate, "run_code_reality_audits", lambda changed_paths=None: calls.append("code-reality") or True)

    args = argparse.Namespace(
        dry_run=False,
        changed_only=None,
        changed_paths=["nexus/engine/ultra_review_service.py"],
        nightly=False,
        strict=True,
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
            assert calls == ["ultra"]
            mock_exit.assert_called_with(1)


def test_ci_gate_main_strict_blocks_when_code_reality_audit_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(ci_gate, "run_changed_only_check", lambda changed_paths: True)
    monkeypatch.setattr(ci_gate, "requires_ultra_review", lambda changed_paths: False)
    monkeypatch.setattr(ci_gate, "run_code_reality_audits", lambda changed_paths=None: calls.append(changed_paths) or False)

    args = argparse.Namespace(
        dry_run=False,
        changed_only=None,
        changed_paths=["docs/ops/brain_hub_manifest.json"],
        nightly=False,
        strict=True,
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
            assert calls == [["docs/ops/brain_hub_manifest.json"]]
            mock_exit.assert_called_with(1)


def test_run_dry_run_blocks_when_report_trust_audit_fails(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_integrity_check", lambda: True)
    monkeypatch.setattr(ci_gate, "run_protocol_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_lesson_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_delivery_tracked_check", lambda dry_run=True: True)
    monkeypatch.setattr(ci_gate, "run_wiki_sync_check", lambda dry_run: "OK")
    monkeypatch.setattr(ci_gate, "print_phase_6_summaries", lambda *args, **kwargs: None)
    monkeypatch.setattr(ci_gate, "run_report_trust_audit", lambda dry_run: False)
    monkeypatch.setattr(ci_gate, "run_code_reality_audits", lambda changed_paths=None: True)

    exit_code = ci_gate.run_dry_run()
    assert exit_code == 1


def test_ci_gate_main_blocks_when_report_trust_audit_fails(monkeypatch):
    monkeypatch.setattr(ci_gate, "run_protocol_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_lesson_check", lambda dry_run: True)
    monkeypatch.setattr(ci_gate, "run_wiki_sync_check", lambda dry_run: "OK")
    monkeypatch.setattr(ci_gate, "run_step", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr(ci_gate, "run_report_trust_audit", lambda dry_run: False)
    monkeypatch.setattr(ci_gate, "run_code_reality_audits", lambda changed_paths=None: True)
    monkeypatch.setattr(ci_gate, "print_phase_6_summaries", lambda *args, **kwargs: None)

    args = argparse.Namespace(
        dry_run=False,
        changed_only=None,
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
