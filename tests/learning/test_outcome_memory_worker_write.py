from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.learning.outcome_memory import OutcomeMemoryManager


class TestOutcomeMemoryWorkerWrite:

    def test_append_worker_write_validates_required_fields(self, tmp_path: Path):
        with pytest.raises(ValueError, match="task_id"):
            OutcomeMemoryManager.append_worker_write({"worker_name": "w1"}, project_root=tmp_path)
        with pytest.raises(ValueError, match="worker_name"):
            OutcomeMemoryManager.append_worker_write({"task_id": "t1"}, project_root=tmp_path)

    def test_append_worker_write_appends_to_jsonl(self, tmp_path: Path):
        receipt = {"task_id": "t1", "worker_name": "w1", "result": "ok"}
        OutcomeMemoryManager.append_worker_write(receipt, project_root=tmp_path)
        storage = tmp_path / ".nexus" / "memory" / "outcome_history.jsonl"
        assert storage.exists()
        lines = storage.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["task_id"] == "t1"
        assert payload["worker_name"] == "w1"

    def test_append_worker_write_does_not_break_existing_record_outcome(self, tmp_path: Path):
        from nexus.learning.outcome_memory import EpisodeOutcomeRecord

        record = EpisodeOutcomeRecord.from_task(
            task_id="t1",
            task_type="repair",
            task_desc="fix bug",
            solved=True,
            wall_duration_sec=10.0,
            total_tokens_used=100,
            trust_mismatch=False,
        )
        result = OutcomeMemoryManager.save_episode_and_tune_sync(record, project_root=tmp_path)
        assert result["status"] == "PASS"

        receipt = {"task_id": "t2", "worker_name": "w2", "result": "ok"}
        worker_result = OutcomeMemoryManager.append_worker_write(receipt, project_root=tmp_path)
        assert worker_result["status"] == "PASS"

        storage = tmp_path / ".nexus" / "memory" / "outcome_history.jsonl"
        lines = storage.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_append_worker_write_concurrent_safe(self, tmp_path: Path):
        receipt = {"task_id": "t1", "worker_name": "w1", "result": "ok"}
        import threading

        lock = threading.Lock()
        results = []

        def write_with_lock():
            with lock:
                r = OutcomeMemoryManager.append_worker_write(receipt, project_root=tmp_path)
                results.append(r)

        threads = [threading.Thread(target=write_with_lock) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        storage = tmp_path / ".nexus" / "memory" / "outcome_history.jsonl"
        lines = storage.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 5
