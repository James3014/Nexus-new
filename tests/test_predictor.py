import unittest
from nexus.services.predictor import Predictor

class TestPredictor(unittest.TestCase):
    def setUp(self):
        self.predictor = Predictor()

    def test_predict_risk_high(self):
        task = "Update the main engine core logic and delete old files"
        context = {"files_count": 100}
        result = self.predictor.predict(task, context)
        
        self.assertEqual(result["risk_score"], 0.9)
        self.assertEqual(result["risk_level"], "CRITICAL")
        self.assertTrue(any("Complexity" in r or "Delete" in r for r in result["reasons"]))

    def test_predict_risk_low(self):
        task = "Fix typo in readme"
        context = {"files_count": 1}
        result = self.predictor.predict(task, context)
        
        self.assertEqual(result["risk_score"], 0.2)
        self.assertEqual(result["risk_level"], "LOW")

if __name__ == "__main__":
    unittest.main()
