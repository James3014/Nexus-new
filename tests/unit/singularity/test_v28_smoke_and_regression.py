import unittest
from nexus.state.task_state_store import TaskStateStore, TaskState
from nexus.replay.replay_artifact import ReplayArtifact
from nexus.telemetry.telemetry_models import TelemetryBundle
from nexus.evidence.evidence_chain_service import EvidenceChainService
from nexus.gate.gate_judge import GateJudge, BlockerCodes
from nexus.governance.backfill_service import BackfillService
from nexus.memory.memory_retrieval_service import MemoryRetrievalService
from nexus.memory.memory_models import MemoryHit, FailureSignatureHit

class TestV28SmokeAndRegression(unittest.TestCase):
    """
    🚀 Smoke & 📊 Regression Bundle for v28.2
    """

    def setUp(self):
        self.store = TaskStateStore()
        self.evidence_service = EvidenceChainService()

    def test_shortest_main_path_smoke(self):
        """Task 8: State -> Replay -> Telemetry -> Evidence -> Gate"""
        task_id = "smoke-123"
        # 1. State
        state = self.store.commit(task_id, {"goal": "fix-bug"})
        
        # 2. Replay
        replay = ReplayArtifact(task_id, "SUCCESS", "pytest", "/tmp", 60, ["pass"])
        
        # 3. Telemetry
        tel = TelemetryBundle(wall_time_ms=100, token_usage=50, provider_costs=0.1, overhead_ms=5)
        
        # 4. Evidence
        seal = self.evidence_service.seal("ev-1", {"status": "SUCCESS"})
        barrier = self.evidence_service.barrier(seal, partial_telemetry=not tel.complete, dirty_write=False)
        self.assertEqual(barrier["status"], "PASS")

        # 5. Gate
        verdict = GateJudge.decide(task_id, replay=replay, telemetry=tel, evidence_seal=seal)
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["blocker"], BlockerCodes.NONE)

    def test_backfill_main_path_smoke(self):
        """Task 9: Backfill Path"""
        old_receipt = {"task_id": "v27-001", "allowed": True, "telemetry": {"wall_time_ms": 50}}
        migrated = BackfillService.migrate_receipt(old_receipt)
        
        # 應標記為 BACKFILL_NEEDED 因為缺 tokens
        self.assertEqual(migrated["status"], "BACKFILL_NEEDED")
        self.assertFalse(migrated["is_claimable"])

    def test_memory_causal_retrieval_smoke(self):
        """Task 10: Memory Causal Retrieval Path"""
        h_signature = FailureSignatureHit("h1", "fix race", 0.9, state_version=1, root_cause="locking")
        h_archive = MemoryHit("h2", "old doc", 0.95, state_version=1)
        
        pack = MemoryRetrievalService.rank_and_pack([h_archive, h_signature], current_state_version=1)
        
        # Signature 應進入 actionable
        self.assertEqual(pack.actionable_hits[0].id, "h1")
        self.assertEqual(pack.background_archive[0].id, "h2")

    def test_regression_old_receipt_missing_telemetry(self):
        """Task 11: 舊 receipt 缺 telemetry 案例"""
        old_data = {"task_id": "legacy", "allowed": True, "telemetry": {}} # 全缺
        migrated = BackfillService.migrate_receipt(old_data)
        self.assertEqual(migrated["status"], "BACKFILL_NEEDED")
        self.assertFalse(migrated["telemetry_bundle"].complete)

    def test_regression_memory_false_hit_pollution(self):
        """Task 12: Memory 錯誤命中污染案例 (低相關性應被過濾)"""
        h_low = MemoryHit("bad", "irrelevant", 0.3, state_version=1)
        pack = MemoryRetrievalService.rank_and_pack([h_low], current_state_version=1, relevance_threshold=0.7)
        self.assertEqual(len(pack.background_archive), 0)

    def test_regression_stale_state_drift(self):
        """Task 13: Stale write / state_version 漂移案例"""
        self.store.commit("t1", {"v": 1}) # v1
        self.store.commit("t1", {"v": 2}) # v2
        
        # 嘗試以 v1 基礎進行 stale update
        with self.assertRaises(RuntimeError):
            self.store.reject_if_stale("t1", base_version=1)

if __name__ == "__main__":
    unittest.main()
