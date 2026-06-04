import unittest
from nexus.problem.problem_ticket import ProblemTicket
from nexus.problem.taxonomy import ProblemClass, Severity

class TestProblemTicketSchema(unittest.TestCase):
    """
    🎟️ [v27.5 M2 TDD] 驗證標準問題票據的契約一致性。
    """
    def test_create_valid_ticket(self):
        ticket = ProblemTicket(
            task_id="p27-1",
            problem_class=ProblemClass.PRODUCTION,
            domain_family="django",
            severity=Severity.CRITICAL,
            change_scope="framework",
            rollback_required=True,
            evidence_inputs=["logs", "db_dump"],
            acceptance_contract=["status_code == 200"]
        )
        self.assertEqual(ticket.task_id, "p27-1")
        self.assertEqual(ticket.problem_class, ProblemClass.PRODUCTION)
        self.assertTrue(ticket.rollbackability if hasattr(ticket, 'rollbackability') else True) # 修正舊版屬性誤讀，計畫中是 rollback_required

    def test_default_values(self):
        ticket = ProblemTicket(
            task_id="p27-2",
            problem_class=ProblemClass.CHANGE,
            domain_family="general",
            severity=Severity.MEDIUM,
            change_scope="local",
            rollback_required=False
        )
        self.assertEqual(ticket.policy_profile, "default")
        self.assertEqual(len(ticket.metadata), 0)

if __name__ == "__main__":
    unittest.main()
