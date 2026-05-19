import pytest
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from nexus.services.federated_lessons import (
    fetch_remote_lessons,
    sync_federated_lessons, 
    FederatedPeer, 
    validate_and_filter_lessons,
    wrap_envelope
)

@pytest.fixture
def mock_lesson_v1():
    return {
        "lesson_id": "sha-abc",
        "task_id": "task-123",
        "category": "LOGIC",
        "root_cause": "Test issue",
        "corrective_action": "Fix it",
        "confidence": 0.9,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "schema_version": "lesson_event.v1",
        "outcome": "success"
    }

def test_validate_and_filter_lessons_rejects_old_schema(mock_lesson_v1):
    mock_lesson_v1["schema_version"] = "lesson_event.v0"
    result = validate_and_filter_lessons([mock_lesson_v1])
    assert len(result) == 0

def test_validate_and_filter_lessons_rejects_low_confidence(mock_lesson_v1):
    mock_lesson_v1["confidence"] = 0.5
    result = validate_and_filter_lessons([mock_lesson_v1], min_confidence=0.7)
    assert len(result) == 0

def test_validate_and_filter_lessons_rejects_missing_fields(mock_lesson_v1):
    del mock_lesson_v1["root_cause"]
    result = validate_and_filter_lessons([mock_lesson_v1])
    assert len(result) == 0

def test_validate_and_filter_lessons_rejects_failure_outcomes(mock_lesson_v1):
    mock_lesson_v1["outcome"] = "failure"
    result = validate_and_filter_lessons([mock_lesson_v1])
    assert len(result) == 0

def test_wrap_envelope_preserves_provenance(mock_lesson_v1):
    peer = FederatedPeer(name="ws-primary", source_type="p2p", locator="url", trust_tier="peer")
    envelope = wrap_envelope(mock_lesson_v1, peer)
    
    assert envelope["source_repo"] == "ws-primary"
    assert envelope["trust_tier"] == "peer"
    assert envelope["lesson"]["lesson_id"] == "sha-abc"
    assert "cache_id" in envelope

@pytest.mark.asyncio
async def test_fetch_remote_lessons_blocks_private_network_source():
    class Session:
        async def get(self, *_args, **_kwargs):
            raise AssertionError("network fetch should be blocked before session.get")

    result = await fetch_remote_lessons(Session(), "http://127.0.0.1/lessons.jsonl")

    assert result == []

@pytest.mark.asyncio
async def test_sync_federated_lessons_idempotency(tmp_path, mock_lesson_v1):
    # Setup peers config
    peer_cfg = {
        "version": "federated_peers.v1",
        "peers": [
            {"name": "peer-a", "source_type": "p2p", "locator": "http://peer-a", "trust_tier": "peer", "enabled": True}
        ]
    }
    (tmp_path / ".nexus" / "learning").mkdir(parents=True)
    (tmp_path / ".nexus" / "learning" / "federated_peers.json").write_text(json.dumps(peer_cfg))
    
    with patch("nexus.services.federated_lessons.fetch_remote_lessons", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [mock_lesson_v1]
        
        # First sync
        res1 = await sync_federated_lessons(tmp_path)
        assert res1["new_lessons"] == 1
        
        # Second sync (same lesson)
        res2 = await sync_federated_lessons(tmp_path)
        assert res2["new_lessons"] == 0
        assert res2["total_cache"] == 1
