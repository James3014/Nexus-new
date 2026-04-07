import unittest
from unittest.mock import MagicMock, patch
from nexus.core.router import SkillsRouter
import os

class TestDualRouter(unittest.TestCase):
    def setUp(self):
        self.project_root = "/Users/jameschen/Workspace/nexus"
        self.router = SkillsRouter(self.project_root)

    def test_dual_mode_palace_hit(self):
        """測試 Dual Mode: 當 Palace Hit >= 0.8 時，不應觸發 Fallback。"""
        context = {"mode": "dual", "tenant_id": "nexus_test", "min_palace_hit": 0.8}
        
        # 模擬 Palace 命中 0.9
        self.router._palace_search = MagicMock(return_value={"status": "SUCCESS", "hit_rate": 0.9, "results": ["palace_data"]})
        self.router._semantic_search = MagicMock()
        
        result = self.router.memory_route("test query", context)
        
        self.assertEqual(result["mode_used"], "palace")
        self.router._semantic_search.assert_not_called()

    def test_dual_mode_fallback(self):
        """測試 Dual Mode: 當 Palace Hit < 0.8 時，應觸發 Semantic Fallback。"""
        context = {"mode": "dual", "tenant_id": "nexus_test", "min_palace_hit": 0.8}
        
        # 模擬 Palace 命中 0.7
        self.router._palace_search = MagicMock(return_value={"status": "SUCCESS", "hit_rate": 0.7, "results": []})
        self.router._semantic_search = MagicMock(return_value={"status": "SUCCESS", "results": ["semantic_data"]})
        
        result = self.router.memory_route("test query", context)
        
        self.assertEqual(result["mode_used"], "semantic")
        self.router._semantic_search.assert_called_once()

    def test_tenant_isolation_passing(self):
        """測試 Tenant ID 是否正確傳遞至搜尋層。"""
        context = {"mode": "semantic", "tenant_id": "tenant_123"}
        self.router._semantic_search = MagicMock(return_value={"status": "SUCCESS", "tenant": "tenant_123"})
        
        result = self.router.memory_route("test query", context)
        self.assertEqual(result["tenant"], "tenant_123")

if __name__ == "__main__":
    unittest.main()
