import importlib.util
import unittest
from nexus.state.task_state_store import TaskStateStore
from nexus.memory.memory_retrieval_service import MemoryRetrievalService
from nexus.memory.memory_models import MemoryHit, FailureSignatureHit
from nexus.governance.backfill_service import BackfillService

class TestV28ContractSealing(unittest.TestCase):
    """
    🔐 Task 1: Cross-Module Integration Tests
    驗證 Memory 檢索與 Gate 判決的物理隔離。
    """

    def setUp(self):
        self.store = TaskStateStore()
        self.ticket_id = "ticket-v28-int"
        self.store.commit(self.ticket_id, {"desc": "test task"}) # v1

    def test_memory_volatility_does_not_affect_gate_verdict(self):
        """nexus.gate (GateJudge) was retired in Phase-2 batch C (#2584); the memory side of
        the original check stays: packing the same hits twice gives the same pack."""
        self.assertIsNone(importlib.util.find_spec("nexus.gate"))
        h1 = MemoryHit("h1", "distraction", 0.95)
        pack1 = MemoryRetrievalService.rank_and_pack([h1], current_state_version=1)
        pack2 = MemoryRetrievalService.rank_and_pack([h1], current_state_version=1)
        self.assertEqual(pack1, pack2)

    def test_state_version_physical_filtering(self):
        """驗證版本鎖：高版本狀態下的 Memory 不得污染低版本決策"""
        # 當前版本 v1
        # 準備一個來自 v2 (未來) 的記憶
        h_future = MemoryHit("future-hit", "from version 2", 0.99, state_version=2)
        
        pack = MemoryRetrievalService.rank_and_pack([h_future], current_state_version=1)
        
        # 預期未來記憶被物理過濾
        self.assertEqual(len(pack.background_archive), 0)
        self.assertFalse(pack.is_actionable)

    def test_backfill_needed_semantics(self):
        """Task 2: 驗證 Backfill 語義，不假造 claimable"""
        old_receipt = {
            "task_id": "v27-task",
            "allowed": True,
            "telemetry": {"wall_time_ms": 100} # 缺失 token_usage 等
        }
        
        migrated = BackfillService.migrate_receipt(old_receipt)
        
        self.assertEqual(migrated["status"], "BACKFILL_NEEDED")
        self.assertFalse(migrated["is_claimable"])
        self.assertFalse(migrated["telemetry_bundle"].complete)

if __name__ == "__main__":
    unittest.main()
