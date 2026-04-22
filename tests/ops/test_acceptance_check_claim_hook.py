from __future__ import annotations

import json
from click.testing import CliRunner
from pathlib import Path


def test_acceptance_check_runs_claim_verifier(monkeypatch):
    from scripts.engine.nexus_cli import nexus

    calls = []

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = b"ok"
            self.stderr = b""

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _Res(0)

    # Skip hallucination dependency in this focused unit test.
    monkeypatch.setattr("scripts.engine.nexus_cli.check_hallucination", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.run", _fake_run)

    result = CliRunner().invoke(nexus, ["nexus", "acceptance-check"])
    assert result.exit_code == 0
    joined = [" ".join(map(str, c)) for c in calls]
    assert any("scripts/ops/nexus_acceptance_check.py" in c for c in joined)
    acceptance_cmd = next(c for c in joined if "scripts/ops/nexus_acceptance_check.py" in c)
    assert "--report-file .nexus/reports/agent_report.json" in acceptance_cmd
    verify_cmd = next(c for c in joined if "scripts/ops/verify_report_claims.py" in c)
    assert "--report-file .nexus/reports/agent_report.json" in verify_cmd
    assert "--require-test-evidence" in verify_cmd


def test_delivery_gate_runs_shell_gate(monkeypatch):
    from scripts.engine.nexus_cli import nexus

    calls = []

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = b"ok"
            self.stderr = b""

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _Res(0)

    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.run", _fake_run)

    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".nexus/reports").mkdir(parents=True, exist_ok=True)
        Path(".nexus/reports/hallucination_evidence.json").write_text("{}", encoding="utf-8")
        result = runner.invoke(nexus, ["nexus", "delivery-gate", "--evidence", ".nexus/reports/hallucination_evidence.json"])
    assert result.exit_code == 0
    joined = [" ".join(map(str, c)) for c in calls]
    assert any("scripts/ops/nexus_delivery_gate.sh" in c for c in joined)


def test_acceptance_check_allows_cold_start_in_dev_policy(monkeypatch):
    from scripts.engine.nexus_cli import nexus

    calls = []

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = b"ok"
            self.stderr = b""

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        joined = " ".join(map(str, cmd))
        if "scripts/ops/nexus_acceptance_check.py" in joined:
            return _Res(1)
        return _Res(0)

    monkeypatch.setattr("scripts.engine.nexus_cli.check_hallucination", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.run", _fake_run)
    monkeypatch.setenv("NEXUS_ACCEPTANCE_POLICY", "dev")

    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".nexus/reports").mkdir(parents=True, exist_ok=True)
        Path(".nexus/reports/acceptance_check.json").write_text(
            json.dumps({"status": "UNVERIFIED_COLD_START", "gate_passed": False}),
            encoding="utf-8",
        )
        Path(".nexus/reports/acceptance_check.md").write_text("# check", encoding="utf-8")
        result = runner.invoke(nexus, ["nexus", "acceptance-check"])

    assert result.exit_code == 0
    joined = [" ".join(map(str, c)) for c in calls]
    verify_cmd = next(c for c in joined if "scripts/ops/verify_report_claims.py" in c)
    assert "--require-acceptance-pass" not in verify_cmd


def test_acceptance_check_blocks_cold_start_in_prod_policy(monkeypatch):
    from scripts.engine.nexus_cli import nexus

    class _Res:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = b"ok"
            self.stderr = b""

    def _fake_run(cmd, *args, **kwargs):
        joined = " ".join(map(str, cmd))
        if "scripts/ops/nexus_acceptance_check.py" in joined:
            return _Res(1)
        return _Res(0)

    monkeypatch.setattr("scripts.engine.nexus_cli.check_hallucination", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.run", _fake_run)
    monkeypatch.setenv("NEXUS_ACCEPTANCE_POLICY", "prod")

    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".nexus/reports").mkdir(parents=True, exist_ok=True)
        Path(".nexus/reports/acceptance_check.json").write_text(
            json.dumps({"status": "UNVERIFIED_COLD_START", "gate_passed": False}),
            encoding="utf-8",
        )
        Path(".nexus/reports/acceptance_check.md").write_text("# check", encoding="utf-8")
        result = runner.invoke(nexus, ["nexus", "acceptance-check"])

    assert result.exit_code != 0


def test_delivery_receipt_renders_json(tmp_path, monkeypatch):
    from scripts.engine.nexus_cli import nexus

    receipt = tmp_path / "delivery_gate.json"
    receipt.write_text('{"head":"abc123","branch":"feat/x","delivery_gate_passed":true}', encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(nexus, ["nexus", "delivery-receipt", "--receipt", str(receipt), "--json"])
    assert result.exit_code == 0
    assert '"head": "abc123"' in result.output


def test_contract_snapshot_writes_current_head(tmp_path, monkeypatch):
    from scripts.engine.nexus_cli import nexus

    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)

    def _fake_check_output(cmd, cwd=None):
        if cmd[:3] == ["git", "rev-parse", "--short"]:
            return b"abc123\n"
        if cmd[:4] == ["git", "show", "--name-only", "--format="]:
            return b"nexus/orchestrator/orchestrator.py\ntests/nexus/orchestrator/test_task_contract.py\n"
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.check_output", _fake_check_output)
    out = tmp_path / ".nexus" / "reports" / "closeout_contract.json"
    result = CliRunner().invoke(nexus, ["nexus", "contract-snapshot", "--output", str(out)])
    assert result.exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["commit_sha"] == "abc123"
    assert payload["changed_files"] == [
        "nexus/orchestrator/orchestrator.py",
        "tests/nexus/orchestrator/test_task_contract.py",
    ]


def test_multi_agent_submit_uses_delivery_receipt(tmp_path, monkeypatch):
    from scripts.engine.nexus_cli import nexus

    receipt = tmp_path / ".nexus" / "reports" / "delivery_gate.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({
        "delivery_gate_passed": True,
        "acceptance_result": {"gate_passed": True},
    }), encoding="utf-8")

    class _Task:
        task_id = "T1"
        owner = "codex"

    class _Collector:
        def generate_hallucination_evidence(self, task, final_response):
            ev = tmp_path / ".nexus" / "reports" / "hallucination_evidence.json"
            ev.write_text(json.dumps({"claim_state": "VERIFIED", "confidence_level": "HIGH"}), encoding="utf-8")
            return ev

    class _Orch:
        evidence_collector = _Collector()
        state_store = type("S", (), {"load_task": staticmethod(lambda _task_id: _Task())})()
        def verify_task(self, task_id):
            return True

    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.check_output", lambda *args, **kwargs: b"abc123\n")
    monkeypatch.setattr("nexus.orchestrator.orchestrator.NexusOrchestrator", lambda: _Orch())
    monkeypatch.setattr("nexus.orchestrator.governance_bridge.append_governance_event", lambda *args, **kwargs: None)

    result = CliRunner().invoke(nexus, ["nexus", "multi-agent", "submit", "--task-id", "T1"])
    assert result.exit_code == 0
    assert '"delivery_gate": "PASS"' in result.output
    assert '"acceptance_check": "PASS"' in result.output
    assert '"contract_check": "UNRUN"' in result.output
    assert '"ci_gate": "UNRUN"' in result.output


def test_multi_agent_submit_fails_closed_without_acceptance_receipt(tmp_path, monkeypatch):
    from scripts.engine.nexus_cli import nexus

    receipt = tmp_path / ".nexus" / "reports" / "delivery_gate.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"delivery_gate_passed": True}), encoding="utf-8")

    class _Task:
        task_id = "T1"
        owner = "codex"

    class _Collector:
        def generate_hallucination_evidence(self, task, final_response):
            ev = tmp_path / ".nexus" / "reports" / "hallucination_evidence.json"
            ev.write_text(json.dumps({"claim_state": "VERIFIED", "confidence_level": "HIGH"}), encoding="utf-8")
            return ev

    class _Orch:
        evidence_collector = _Collector()
        state_store = type("S", (), {"load_task": staticmethod(lambda _task_id: _Task())})()
        def verify_task(self, task_id):
            return True

    monkeypatch.setattr("scripts.engine.nexus_cli.repo_root", tmp_path)
    monkeypatch.setattr("scripts.engine.nexus_cli.subprocess.check_output", lambda *args, **kwargs: b"abc123\n")
    monkeypatch.setattr("nexus.orchestrator.orchestrator.NexusOrchestrator", lambda: _Orch())
    monkeypatch.setattr("nexus.orchestrator.governance_bridge.append_governance_event", lambda *args, **kwargs: None)

    result = CliRunner().invoke(nexus, ["nexus", "multi-agent", "submit", "--task-id", "T1"])
    assert result.exit_code != 0
    assert "Submission blocked" in result.output
