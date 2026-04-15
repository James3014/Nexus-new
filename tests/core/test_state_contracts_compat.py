import pytest
import json
from nexus.core.state_contracts import NexusState

def test_nexus_state_deduplication_integrity():
    # Verify we can instantiate with both new and consolidated legacy fields
    state = NexusState(
        task_id="test-task",
        version="v26.1",
        aos_score=100.0,
        schema_version="2.0.0"
    )
    assert state.task_id == "test-task"
    assert state.version == "v26.1"
    assert state.aos_score == 100.0

def test_legacy_payload_roundtrip():
    legacy_json = {
        "task_id": "legacy-task",
        "version": "v21.0",
        "aos_score": 120.5,
        "active_shards": {"shard1": "./path"},
        "tokens": {"total_usage": 500}
    }
    
    # Load (Migrator should handle missing fields if any)
    state = NexusState(**legacy_json)
    
    # Dump
    dumped = state.model_dump(mode='json')
    
    # Check key preservation
    assert dumped["task_id"] == "legacy-task"
    assert dumped["version"] == "v21.0"
    assert dumped["aos_score"] == 120.5
    assert dumped["tokens"]["total_usage"] == 500
