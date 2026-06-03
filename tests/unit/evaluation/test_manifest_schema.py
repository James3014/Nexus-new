import unittest
from nexus.evaluation.manifest_manager import ManifestManager

class TestManifestSchema(unittest.TestCase):
    def test_total_count(self):
        """[T1] 驗證：全量清單應包含 123 題 (113 SWE + 10 Concurrency)"""
        inventory = ManifestManager.get_full_inventory()
        # 113 SWE 任務 + 10 Concurrency 任務
        self.assertEqual(len(inventory), 123)

    def test_lane_distribution(self):
        """[T2] 驗證：前 100 題應進入 Baseline Lane"""
        inventory = ManifestManager.get_full_inventory()
        baseline_tasks = [t for t in inventory if t.lane == "baseline"]
        challenge_tasks = [t for t in inventory if t.lane == "challenge"]
        
        # 前 100 題 (swe-bench-verified) 為 baseline
        # 剩餘 13 題 為 challenge
        # 另外 10 題 Concurrency 被分配在 baseline (因已收斂)
        self.assertEqual(len(challenge_tasks), 13)

if __name__ == "__main__":
    unittest.main()
