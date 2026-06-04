import unittest
from nexus.lanes.base_lane import BaseLane
from nexus.problem.problem_ticket import ProblemTicket
from nexus.problem.taxonomy import ProblemClass, Severity

class MockLane(BaseLane):
    def plan(self, ticket): return "plan_ok"
    def guard(self, patch): return True
    def execute(self, plan): return "patch_ok"
    def verify(self, patch): return True
    def emit_evidence(self): return {"status": "evidence_ok"}

class TestLaneContractV275(unittest.TestCase):
    """
    🏗️ [v27.5 M5 TDD] 驗證統一車道介面的執行流。
    """

    def test_standard_execution_flow(self):
        ticket = ProblemTicket(
            task_id="t1", problem_class=ProblemClass.CHANGE,
            domain_family="general", severity=Severity.LOW,
            change_scope="local", rollback_required=True
        )
        lane = MockLane()
        
        # 執行標準生命週期
        plan = lane.plan(ticket)
        patch = lane.execute(plan)
        self.assertTrue(lane.guard(patch))
        self.assertTrue(lane.verify(patch))
        evidence = lane.emit_evidence()
        
        self.assertEqual(evidence["status"], "evidence_ok")

if __name__ == "__main__":
    unittest.main()
