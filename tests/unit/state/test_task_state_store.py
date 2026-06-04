import unittest
from nexus.state.task_state_store import TaskStateStore

class TestTaskStateStore(unittest.TestCase):
    """
    🏛️ [v28.1] TaskStateStore 契約測試
    驗證狀態的單一真實來源、版本遞增與回滾正確性。
    """

    def test_commit_increments_version(self):
        store = TaskStateStore()
        s1 = store.commit("t1", {"data": "v1"})
        s2 = store.commit("t1", {"data": "v2"})
        
        self.assertEqual(s1.version, 1)
        self.assertEqual(s2.version, 2)
        self.assertEqual(s2.parent_version, 1)
        self.assertEqual(store.get_latest("t1").payload["data"], "v2")

    def test_checkpoint_roundtrip_restore(self):
        store = TaskStateStore()
        store.commit("t1", {"data": "v1"})
        cp = store.checkpoint("t1", "milestone-1")
        
        self.assertEqual(cp.checkpoint_label, "milestone-1")
        self.assertEqual(store.get_latest("t1").checkpoint_label, "milestone-1")

    def test_reject_stale_write_against_newer_version(self):
        store = TaskStateStore()
        store.commit("t1", {"data": "v1"}) # v1
        store.commit("t1", {"data": "v2"}) # v2
        
        # 模擬一個持舊版 v1 的 Agent 企圖寫入
        with self.assertRaises(RuntimeError) as cm:
            store.reject_if_stale("t1", 1)
        self.assertIn("Stale state detected", str(cm.exception))

    def test_rollback_restores_latest_valid_user_definition(self):
        store = TaskStateStore()
        store.commit("t1", {"data": "good"}) # v1
        store.commit("t1", {"data": "bad"})  # v2
        
        # 回滾至 v1
        s3 = store.rollback("t1", 1)
        self.assertEqual(s3.version, 3) # 回滾產生的新版本
        self.assertEqual(s3.payload["data"], "good")

if __name__ == "__main__":
    unittest.main()
