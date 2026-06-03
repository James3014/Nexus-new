import unittest
from nexus.search.shuffler import VariantShuffler

class TestVariantShuffler(unittest.TestCase):
    def test_shuffling_preserves_count(self):
        """[T1.2] 驗證：攪拌後候選者數量不變且內容被修改"""
        shuffler = VariantShuffler()
        base = [{"id": "c1", "content": "x"}]
        res = shuffler.apply_shuffling(base)
        self.assertEqual(len(res), 1)
        self.assertIn("prompt_variant", res[0])

if __name__ == "__main__":
    unittest.main()
