import unittest
from nexus.resilience.failure_domains import FailureDomain

class TestIsolation(unittest.TestCase):
    """
    🚧 [v27.7 M3 TDD] 驗證失效域隔離機制。
    """
    def test_isolate(self):
        fd = FailureDomain("test")
        # 預期：拋出異常時應回傳包含 ISOLATED 狀態的字典，而非 None
        result = fd.isolate(lambda: 1/0)
        self.assertEqual(result["status"], "ISOLATED")
        self.assertEqual(result["domain"], "test")

if __name__ == "__main__":
    unittest.main()
