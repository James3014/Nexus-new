import unittest
from nexus.committee.controller import CommitteeController

class TestCommitteeFlow(unittest.TestCase):
    def test_full_committee_workflow(self):
        """驗證委員會全鏈路流程：註冊 -> 驗證 -> 選優 -> 收據"""
        controller = CommitteeController("task-v26-e2e")
        
        proposals = [
            {"model": "7B", "attempt": 1, "raw_label": "r:0,p:1"},
            {"model": "14B", "attempt": 1, "raw_label": "r:0,p:3"}
        ]
        
        receipt = controller.process_proposals(proposals)
        
        self.assertEqual(receipt.k, 2)
        self.assertIsNotNone(receipt.winner_id)
        self.assertEqual(len(receipt.verdicts), 4) # 2 candidates * 2 critics

if __name__ == "__main__":
    unittest.main()
