import tempfile
import shutil
from pathlib import Path
import unittest
import json
import os
from unittest.mock import patch, MagicMock
from nexus.services.memory import MemoryService, FaultLesson

class TestMemoryService(unittest.TestCase):
    def setUp(self):
        # 使用動態臨時目錄，避免多進程/多測試競態
        self.test_dir = tempfile.mkdtemp(prefix="nexus_test_memory_")
        self.project_root = Path(self.test_dir)
        
        # Create some mock data files
        (self.project_root / "obsidian").mkdir(parents=True, exist_ok=True)
        with open(self.project_root / "obsidian/crystal_lessons.jsonl", "w") as f:
            f.write(json.dumps({"signature": "sig1", "cause": "cause1", "lesson": "lesson1"}) + "\n")
        
        self.service = MemoryService(project_root=str(self.project_root))

    def tearDown(self):
        # 強制清理且忽略錯誤
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_aggregate_memory(self):
        result = self.service.aggregate_memory()
        self.assertIn("reminders", result)
        self.assertIn("total_sources", result)
        self.assertTrue(len(result["reminders"]) > 0)
        
        # Check for our mock data in reminders
        found = False
        for r in result["reminders"]:
            if isinstance(r["content"], dict) and r["content"].get("signature") == "sig1":
                found = True
                break
        self.assertTrue(found, "Mock crystal lesson not found in reminders")
        
        # Check if reminders.json is generated
        self.assertTrue((self.project_root / "reminders.json").exists())

    @patch("nexus.services.memory.redis")
    def test_cached_search(self, mock_redis_module):
        # Mock redis available
        mock_r = MagicMock()
        mock_redis_module.Redis.return_value = mock_r
        mock_r.ping.return_value = True
        mock_r.get.return_value = None # Cache miss
        
        service = MemoryService(project_root=str(self.project_root))
        result = service.cached_search("test_key")
        
        self.assertIn("reminders", result)
        mock_r.setex.assert_called_once()

    def test_semantic_search_returns_rows_instead_of_empty(self):
        import pandas as pd
        service = MemoryService(project_root=str(self.project_root))
        
        mock_repo = MagicMock()
        mock_repo.search_fts.return_value = pd.DataFrame(
            [{"rule_id": "POL-001", "action": "use os.path", "_score": 1.0}]
        )
        service.repo = mock_repo
        
        rows = service.semantic_search("os.path")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "POL-001")

    def test_memory_db_path_can_be_overridden_for_benchmark_isolation(self):
        override = self.project_root / "isolated" / "lancedb"
        with patch.dict(os.environ, {"NEXUS_MEMORY_DB_PATH": str(override)}):
            service = MemoryService(project_root=str(self.project_root))
        self.assertEqual(service.db_path, override)

    def test_fault_lessons_roundtrip_jsonl(self):
        fault_hash = "abc123hash"
        self.service.record_fault_lesson(FaultLesson(
            fault_hash=fault_hash,
            error_type="ModuleNotFoundError",
            diagnosis_kind="environment_failure",
            lesson="Install missing dependency",
            repair_patch="auto.repair.environment",
            audit_pass_rate=0.91,
            metadata={"k": "v"},
        ))
        hits = self.service.lookup_fault_lessons(fault_hash, limit=2)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["source"], "jsonl-fault-lessons")
        self.assertIn("lesson", hits[0]["content"])

if __name__ == "__main__":
    unittest.main()
