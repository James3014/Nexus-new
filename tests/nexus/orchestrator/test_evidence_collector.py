import json

import pytest
from unittest.mock import MagicMock, patch
from nexus.orchestrator.evidence_collector import EvidenceCollector
from nexus.orchestrator.task_contract import Evidence, Task, TaskStatus
from nexus.services.codeintel import analyze_impact

@pytest.fixture
def task():
    return Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["pytest passes"],
        evidence_requirements=["pytest", "nexus acceptance-check"]
    )

def test_run_check(task, tmp_path):
    collector = EvidenceCollector(reports_dir=str(tmp_path))
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        evidence = collector.run_check(task, ["echo", "hello"], "Test echo")
        
        assert evidence.command == "echo hello"
        assert evidence.exit_code == 0
        assert len(task.evidence_list) == 1

def test_verify_gate_pass(task, tmp_path):
    collector = EvidenceCollector(reports_dir=str(tmp_path))
    impact_report = tmp_path / "impact.json"
    impact_report.write_text('{"schema_version":"codeintel-v1"}', encoding="utf-8")
    task.add_evidence(Evidence(command="pytest -q tests/nexus/orchestrator", exit_code=0, output_summary="3 passed"))
    task.add_evidence(Evidence(command=f"nexus code:impact --files file1.py --report-file {impact_report}", exit_code=0, output_summary="impact ok"))
    
    with patch("subprocess.run") as mock_run:
        # Delivery gate passes
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        
        result = collector.verify_gate(task)
        assert result is True
        assert len(task.evidence_list) >= 1
        assert any("delivery-gate" in evidence.command for evidence in task.evidence_list)

def test_verify_gate_fail(task, tmp_path):
    collector = EvidenceCollector(reports_dir=str(tmp_path))
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="Fail", stderr="Error")
        
        result = collector.verify_gate(task)
        assert result is False

def test_verify_gate_fails_without_required_pytest_evidence(task, tmp_path):
    collector = EvidenceCollector(reports_dir=str(tmp_path))

    with patch("subprocess.run") as mock_run:
        result = collector.verify_gate(task)

    assert result is False
    assert task.evidence_list[-1].command == "evidence-precheck"
    assert "pytest" in task.evidence_list[-1].output_summary
    mock_run.assert_not_called()


def test_verify_gate_accepts_real_code_impact_report_artifact(tmp_path):
    source = tmp_path / "file1.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    report = tmp_path / "impact.json"
    payload = analyze_impact(tmp_path, ["file1.py"]).to_dict()
    payload["report_path"] = str(report)
    report.write_text(json.dumps(payload), encoding="utf-8")
    task = Task(
        task_id="TASK-002",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["pytest passes"],
        evidence_requirements=["pytest", "nexus acceptance-check"],
    )
    task.add_evidence(Evidence(command="pytest -q tests/nexus/orchestrator", exit_code=0, output_summary="3 passed"))
    task.add_evidence(Evidence(command=f"nexus code impact --files file1.py --report-file {report}", exit_code=0, output_summary="impact ok"))
    collector = EvidenceCollector(reports_dir=str(tmp_path / "reports"))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")

        assert collector.verify_gate(task) is True
# integrity-seal: 1776512137
