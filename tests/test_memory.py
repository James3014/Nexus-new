import unittest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from nexus.services.memory import MemoryService

class TestMemoryService(unittest.TestCase):
    def setUp(self):
        self.project_root = Path("/tmp/nexus_test_memory")
        self.project_root.mkdir(parents=True, exist_ok=True)
        # Create some mock data files
        (self.project_root / "obsidian").mkdir(parents=True, exist_ok=True)
        with open(self.project_root / "obsidian/crystal_lessons.jsonl", "w") as f:
            f.write(json.dumps({"signature": "sig1", "cause": "cause1", "lesson": "lesson1"}) + "\n")
        
        self.service = MemoryService(project_root=str(self.project_root))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_root)

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

    @patch("redis.Redis")
    def test_cached_search(self, mock_redis):
        # Mock redis available
        mock_r = MagicMock()
        mock_redis.return_value = mock_r
        mock_r.ping.return_value = True
        mock_r.get.return_value = None # Cache miss
        
        service = MemoryService(project_root=str(self.project_root))
        result = service.cached_search("test_key")
        
        self.assertIn("reminders", result)
        mock_r.setex.assert_called_once()

if __name__ == "__main__":
    unittest.main()
