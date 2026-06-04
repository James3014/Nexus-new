import unittest
from nexus.problem_ingress.problem_ticket import ProblemTicket, ProblemClass
from nexus.policy.policy_engine import PolicyEngine

class TestAdmissionPolicy(unittest.TestCase):
    """
    🛡️ [v27.5 M3 TDD: RED]
    驗證 Policy Engine 能否集中評估准入政策。
    """

    def test_block_unauthorized_source(self):
        ticket = ProblemTicket(
            source="untrusted-bot",
            task_id="ext-1",
            problem_class=ProblemClass.CORRECTNESS,
            domain_family="general",
            risk_level="HIGH",
            repro_steps=[], acceptance_checks=[], rollbackability=False
        )
        
        # 預期：應被阻斷
        decision = PolicyEngine.evaluate_admission(ticket)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "UNAUTHORIZED_SOURCE")

if __name__ == "__main__":
    unittest.main()
