import pytest
from unittest.mock import MagicMock, patch
from nexus.orchestrator.evidence_collector import EvidenceCollector
from nexus.orchestrator.task_contract import Task, TaskStatus

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
    
    with patch("subprocess.run") as mock_run:
        # Both pytest and acceptance-check pass
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        
        result = collector.verify_gate(task)
        assert result is True
        assert len(task.evidence_list) >= 2

def test_verify_gate_fail(task, tmp_path):
    collector = EvidenceCollector(reports_dir=str(tmp_path))
    
    with patch("subprocess.run") as mock_run:
        # First check passes, second fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="Success", stderr=""),
            MagicMock(returncode=1, stdout="Fail", stderr="Error")
        ]
        
        result = collector.verify_gate(task)
        assert result is False
# v24.13 final validation
