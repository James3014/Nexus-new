import unittest
from nexus.memory.memory_models import MemoryHit, FailureSignatureHit, MemoryContextPack
from nexus.memory.memory_retrieval_service import MemoryRetrievalService

class TestMemoryRetrievalService(unittest.TestCase):
    def test_failure_signature_ranked_above_archive(self):
        # 準備混合命中
        h1 = MemoryHit("h1", "generic background", 0.9)
        h2 = FailureSignatureHit("h2", "exact signature", 0.8, root_cause="race")
        
        pack = MemoryRetrievalService.rank_and_pack([h1, h2], current_state_version=1)
        
        # 驗證物理隔離
        self.assertEqual(len(pack.actionable_hits), 1)
        self.assertEqual(pack.actionable_hits[0].id, "h2")
        self.assertEqual(pack.background_archive[0].id, "h1")
        self.assertTrue(pack.is_actionable)

    def test_low_relevance_archive_filtered_out(self):
        h1 = MemoryHit("h1", "low relevance", 0.5)
        pack = MemoryRetrievalService.rank_and_pack([h1], current_state_version=1, relevance_threshold=0.7)
        self.assertEqual(len(pack.background_archive), 0)

    def test_stale_memory_filtered_by_state_version(self):
        # 模擬一個來自未來版本的記憶（不可能，除非 state drift）
        h1 = MemoryHit("h1", "stale", 0.9, state_version=5)
        pack = MemoryRetrievalService.rank_and_pack([h1], current_state_version=2)
        self.assertEqual(len(pack.background_archive), 0)

    def test_neutral_memory_does_not_become_action_plan(self):
        # 只有 Archive 命中
        h1 = MemoryHit("h1", "just an archive", 0.9)
        pack = MemoryRetrievalService.rank_and_pack([h1], current_state_version=1)
        
        self.assertFalse(pack.is_actionable)
        self.assertEqual(len(pack.actionable_hits), 0)
        self.assertEqual(len(pack.background_archive), 1)

if __name__ == "__main__":
    unittest.main()
