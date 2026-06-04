import unittest
from nexus.search.diversity import DiversityMeter

class TestDiversityMeter(unittest.TestCase):
    def test_high_similarity_detection(self):
        """[T9] 驗證：內容極度接近的候選者會被判定為低多樣性"""
        meter = DiversityMeter()
        p1 = "def fix(): pass"
        p2 = "def fix():  pass" # 只有空格差異
        score = meter.compute_diversity([p1, p2])
        self.assertLess(score, 0.3) # 低於門檻

    def test_high_diversity_detection(self):
        """[T9] 驗證：全然不同的補丁具備高多樣性"""
        meter = DiversityMeter()
        p1 = "def fix_a(): pass"
        p2 = "def fix_b(): return True"
        score = meter.compute_diversity([p1, p2])
        self.assertGreater(score, 0.7)

if __name__ == "__main__":
    unittest.main()
