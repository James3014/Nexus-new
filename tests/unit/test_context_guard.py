import unittest
from nexus.services.local_heal.context_guard import ContextGuard

class TestContextGuard(unittest.TestCase):
    def setUp(self):
        self.guard = ContextGuard()

    def test_truncate_files_logic(self):
        files = [("file1.py", "content1" * 100), ("file2.py", "content2" * 100), ("file3.py", "content3" * 100), ("file4.py", "content4" * 100)]
        # 假設限制 3 個檔案
        truncated = self.guard.limit_localized_files(files, max_files=3, max_total_chars=10000)
        self.assertEqual(len(truncated), 3)
        self.assertEqual(truncated[0][0], "file1.py")

    def test_truncate_files_by_size(self):
        files = [("file1.py", "a" * 6000), ("file2.py", "b" * 6000)]
        # 假設限制總長度 10000
        truncated = self.guard.limit_localized_files(files, max_files=5, max_total_chars=10000)
        # 雖然有 2 個檔案，但第二個會讓總長度超過 10000 (假設簡單切法是超過就丟掉後面的檔案，或者按比例切)
        # 目前 HealOrchestrator 是丟掉後面的檔案
        self.assertEqual(len(truncated), 1)

if __name__ == "__main__":
    unittest.main()
