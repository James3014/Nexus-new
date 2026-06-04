import unittest
from dataclasses import asdict
from nexus.problem_ingress.problem_ticket import ProblemTicket, ProblemClass

class TestProblemTicketSchema(unittest.TestCase):
    """
    🎟️ [v27.5 M1 TDD: RED] 
    驗證 ProblemTicket 能否涵蓋全量治理所需的標準欄位。
    """

    def test_problem_ticket_fields(self):
        ticket = ProblemTicket(
            source="swe-bench",
            task_id="t1",
            problem_class=ProblemClass.CORRECTNESS,
            domain_family="django",
            risk_level="MEDIUM",
            repro_steps=["run tests/t1.py"],
            acceptance_checks=["Status == 200"],
            rollbackability=True
        )
        
        self.assertEqual(ticket.task_id, "t1")
        self.assertEqual(ticket.problem_class, ProblemClass.CORRECTNESS)
        self.assertTrue(ticket.rollbackability)
        
        # 驗證必要屬性是否存在
        data = asdict(ticket)
        expected_keys = {
            "source", "task_id", "problem_class", "domain_family", 
            "risk_level", "repro_steps", "acceptance_checks", 
            "rollbackability", "evidence_refs", "metadata"
        }
        self.assertTrue(expected_keys.issubset(data.keys()))

if __name__ == "__main__":
    unittest.main()
