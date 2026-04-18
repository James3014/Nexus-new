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
    assert any("scripts/ops/verify_report_claims.py" in c for c in joined)


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
