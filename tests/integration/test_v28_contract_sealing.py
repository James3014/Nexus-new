import unittest
from nexus.state.task_state_store import TaskStateStore
from nexus.memory.memory_retrieval_service import MemoryRetrievalService
from nexus.memory.memory_models import MemoryHit, FailureSignatureHit
from nexus.gate.gate_judge import GateJudge
from nexus.telemetry.telemetry_models import TelemetryBundle
from nexus.replay.replay_artifact import ReplayArtifact
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
        """驗證 Pure Judge：Memory 檢索結果改變，判決應保持不變"""
        # 準備穩定的輸入
        t = TelemetryBundle(100, 500, 0.1, 10)
        r = ReplayArtifact(self.ticket_id, "SUCCESS", "pytest", "/tmp", 60, ["pass"])
        
        # 判決 1 (無 Memory)
        res1 = GateJudge.decide(self.ticket_id, telemetry=t, replay=r)
        
        # 模擬 Memory 檢索出大量數據 (Volatility)
        h1 = MemoryHit("h1", "distraction", 0.95)
        pack = MemoryRetrievalService.rank_and_pack([h1], current_state_version=1)
        
        # 判決 2 (帶入 Memory Pack)
        # 注意：雖然傳入 pack，但 GateJudge 不應讀取 memory 來改動 allowed 狀態
        res2 = GateJudge.decide(self.ticket_id, telemetry=t, replay=r, evidence_seal={"sealed": True, "memory": pack})
        
        self.assertEqual(res1["allowed"], res2["allowed"])
        self.assertEqual(res1["blocker"], res2["blocker"])

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
