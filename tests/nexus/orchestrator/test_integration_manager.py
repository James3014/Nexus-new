import pytest
from unittest.mock import MagicMock, patch
from nexus.orchestrator.integration_manager import IntegrationManager
from nexus.orchestrator.task_contract import Task, TaskStatus

@pytest.fixture
def mock_state_store():
    store = MagicMock()
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["file1.py"],
        done_criteria=["pytest passes"],
        evidence_requirements=["pytest"],
        current_status=TaskStatus.READY_FOR_REVIEW,
        branch_name="codex/task/TASK-001"
    )
    store.load_task.return_value = task
    return store

@pytest.fixture
def mock_evidence_collector():
    return MagicMock()

def test_batch_integrate_success(mock_state_store, mock_evidence_collector):
    im = IntegrationManager(mock_state_store, mock_evidence_collector)
    
    with patch.object(im, "_run_git") as mock_git:
        mock_git.return_value = MagicMock(returncode=0, stdout="Success")
        mock_evidence_collector.verify_gate.return_value = True
        
        success, failed = im.batch_integrate(["TASK-001"])
        
        assert success == ["TASK-001"]
        assert not failed
        assert mock_state_store.save_task.called

def test_batch_integrate_conflict(mock_state_store, mock_evidence_collector):
    im = IntegrationManager(mock_state_store, mock_evidence_collector)
    
    with patch.object(im, "_run_git") as mock_git:
        # Checkout success (0), rev-parse success (1), cherry-pick fail (2), abort success (3)
        mock_git.side_effect = [
            MagicMock(returncode=0), # checkout
            MagicMock(returncode=0, stdout="sha123"), # rev-parse
            MagicMock(returncode=1), # cherry-pick fail
            MagicMock(returncode=0)  # abort
        ]
        
        success, failed = im.batch_integrate(["TASK-001"])
        
        assert not success
        assert failed == ["TASK-001"]
        # Check if status was set to CONFLICTED
        task = mock_state_store.load_task("TASK-001")
        assert task.current_status == TaskStatus.CONFLICTED
# v24.13 final validation
