import pytest
from nexus.core.state_repository import StateRepository
from nexus.core.metrics_writer import MetricsWriter
from nexus.core.contract_writer import ContractWriter

def test_state_repository_persists(tmp_path):
    repo = StateRepository(tmp_path / ".musestate")
    from nexus.core.state_contracts import NexusState
    state = NexusState(task_id="test")
    repo.save(state)
    
    loaded = repo.load()
    assert loaded.task_id == "test"

def test_metrics_writer_works(tmp_path):
    writer = MetricsWriter(tmp_path / ".nexus_metrics")
    writer.write("task-1", 1000)
    assert (tmp_path / ".nexus_metrics").exists()

def test_contract_writer_works(tmp_path):
    writer = ContractWriter(tmp_path)
    writer.write("plan.json", {"foo": "bar"})
    assert (tmp_path / "plan.json").exists()
