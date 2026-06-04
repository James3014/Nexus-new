import unittest
import os
from nexus.governance.infrastructure.promotion_writer import PromotionWriter

class TestPromotionWriter(unittest.TestCase):
    """[v27.1 Sprint 3] Atomic Rollback TDD"""
    
    def test_exception_restores_backup(self):
        """[P0] 驗證：例外發生時還原備份"""
        test_file = "test_atomic.txt"
        with open(test_file, "w") as f:
            f.write("original")
            
        def failing_write(path, content):
            raise RuntimeError("Crashed during write")
            
        with self.assertRaises(RuntimeError):
            PromotionWriter.transactional_write(test_file, "new", failing_write)
            
        # 檢查內容是否還原
        with open(test_file, "r") as f:
            self.assertEqual(f.read(), "original")
            
        os.remove(test_file)

if __name__ == "__main__":
    unittest.main()
