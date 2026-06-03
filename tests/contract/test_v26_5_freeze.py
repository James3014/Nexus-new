import unittest
from nexus.env.models import EnvVerdict
from nexus.verifiers.contracts import VerifierVerdict
from nexus.selection.contracts import SelectionVerdict

class TestV265Freeze(unittest.TestCase):
    """
    [T1] Task: Freeze contracts (v26.5 Mainline)
    驗證核心 DTO 欄位穩定性，防止在 v26.6 研究支線中發生意外破壞。
    """

    def test_env_verdict_schema(self):
        v = EnvVerdict(kind="ALLOW", reason="x", repair_hints=[])
        self.assertTrue(hasattr(v, "kind"))
        self.assertTrue(hasattr(v, "can_auto_heal"))

    def test_verifier_verdict_schema(self):
        v = VerifierVerdict(verifier_name="x", candidate_id="y", passed=True, score=1.0)
        self.assertTrue(hasattr(v, "evidence_refs"))
        self.assertTrue(hasattr(v, "failure_tags"))

    def test_selection_verdict_schema(self):
        v = SelectionVerdict(winner_id="w", confidence=0.9, gap=5.0, abstained=False, reason="ok")
        self.assertTrue(hasattr(v, "abstained"))
        self.assertTrue(hasattr(v, "failure_bucket"))

if __name__ == "__main__":
    unittest.main()
