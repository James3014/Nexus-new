import unittest
from nexus.ops.risk_tiering import get_risk_tier, RiskTier
from nexus.problem.taxonomy import ProblemClass, Severity
class TestRisk(unittest.TestCase):
    def test_risk(self):
        tier = get_risk_tier(ProblemClass.PRODUCTION, Severity.CRITICAL)
        self.assertEqual(tier, RiskTier.P0_ULTRA)
