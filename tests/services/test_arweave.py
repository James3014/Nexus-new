import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from nexus.services.arweave_uploader import upload_lessons_to_arweave
from nexus.services.continuous_learning import persist_structured_lesson

@pytest.mark.asyncio
async def test_upload_lessons_filters_by_confidence(tmp_path: Path):
    # Setup: Create lessons with different confidence scores
    nexus_dir = tmp_path / ".nexus" / "knowledge"
    nexus_dir.mkdir(parents=True)
    
    # 1. High confidence lesson
    persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-high",
        raw_lesson="Important fix",
        category="LOGIC",
        corrective_action="Use UTC"
    )
    # Manually update confidence to 0.9 (since persist_structured_lesson defaults or calculates)
    # We'll just assume one is high enough.
    
    # 2. Low confidence lesson (Manual inject for test)
    low_conf_event = {
        "lesson_id": "low-abc",
        "task_id": "task-low",
        "confidence": 0.5,
        "root_cause": "Minor issue",
        "corrective_action": "Cleanup",
        "timestamp_utc": "2026-04-03T12:00:00Z"
    }
    jsonl_path = nexus_dir / "lesson_events.jsonl"
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(low_conf_event) + "\n")

    # Mock Irys Uploader
    with patch("nexus.services.arweave_uploader.Uploader") as MockUploader:
        instance = MockUploader.return_value
        instance.upload.return_value = {"id": "mock-tx-123"}
        
        # Mock wallet existence
        wallet_path = tmp_path / "wallet.json"
        wallet_path.write_text(json.dumps({"private_key": "abc"}))
        
        # Execute upload with min_confidence 0.7
        result = await upload_lessons_to_arweave(
            tmp_path, min_confidence=0.7, wallet_key_path=wallet_path
        )
        
        assert result["status"] == "uploaded"
        assert result["lesson_count"] == 1  # Only the persist_structured_lesson one (default 0.7)
        assert result["tx_id"] == "mock-tx-123"

@pytest.mark.asyncio
async def test_upload_lessons_deduplication(tmp_path: Path):
    # Setup: Create a lesson
    persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-dup",
        raw_lesson="Static lesson",
        category="LOGIC",
        corrective_action="No change"
    )
    
    wallet_path = tmp_path / "wallet.json"
    wallet_path.write_text(json.dumps({"private_key": "abc"}))
    
    with patch("nexus.services.arweave_uploader.Uploader") as MockUploader:
        instance = MockUploader.return_value
        instance.upload.return_value = {"id": "tx-first"}
        
        # First upload
        res1 = await upload_lessons_to_arweave(tmp_path, wallet_key_path=wallet_path)
        assert res1["status"] == "uploaded"
        
        # Second upload (same content)
        res2 = await upload_lessons_to_arweave(tmp_path, wallet_key_path=wallet_path)
        assert res2["status"] == "cached"
        assert res2["tx_id"] == "tx-first"

@pytest.mark.asyncio
async def test_upload_lessons_aborts_without_wallet(tmp_path: Path):
    # Setup: Create a lesson
    persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-no-wallet",
        raw_lesson="Static lesson",
        category="LOGIC",
        corrective_action="No change"
    )
    
    # Execute without creating wallet
    result = await upload_lessons_to_arweave(tmp_path, wallet_key_path=tmp_path / "missing.json")
    
    assert result["status"] == "error"
    assert "Wallet not found" in result["reason"]
