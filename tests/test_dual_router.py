import unittest
from unittest.mock import MagicMock, patch
from nexus.core.router import SkillsRouter
import os


class FakePalace:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def retrieve_from_shards(self, tenant_id, query, artifact_type=None, limit=3):
        self.calls.append({"tenant_id": tenant_id, "query": query, "artifact_type": artifact_type, "limit": limit})
        return list(self.rows)


class FakeCandidate:
    def __init__(self, id, score, tenant_id=None, metadata=None):
        self.id = id
        self.score = score
        self.tenant_id = tenant_id
        self.metadata = metadata or {}

class TestDualRouter(unittest.TestCase):
    def setUp(self):
        self.project_root = str(__import__("pathlib").Path(__file__).resolve().parents[1])
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
        self.router._semantic_search.assert_called_once_with("test query", "tenant_123")

    def test_palace_search_uses_mem_palace_tenant_scope(self):
        palace = FakePalace(rows=[{"tenant_id": "tenant_123", "content": "safe"}])
        router = SkillsRouter(self.project_root, mem_palace=palace)

        result = router._palace_search("safe", "tenant_123")

        self.assertEqual(result["hit_rate"], 1.0)
        self.assertEqual(result["results"], [{"tenant_id": "tenant_123", "content": "safe"}])
        self.assertEqual(palace.calls, [{"tenant_id": "tenant_123", "query": "safe", "artifact_type": None, "limit": 3}])

    def test_palace_search_filters_cross_tenant_rows(self):
        palace = FakePalace(
            rows=[
                {"tenant_id": "tenant_123", "content": "safe"},
                {"tenant_id": "tenant_999", "content": "leak"},
                {"content": "missing tenant"},
            ]
        )
        router = SkillsRouter(self.project_root, mem_palace=palace)

        result = router._palace_search("safe", "tenant_123")

        self.assertEqual(result["results"], [{"tenant_id": "tenant_123", "content": "safe"}])
        self.assertEqual(result["hit_rate"], 1.0)

    @patch("importlib.import_module")
    def test_semantic_search_filters_cross_tenant_candidates(self, import_module):
        module = MagicMock()
        module.LanceDBRetriever.return_value.retrieve.return_value = [
            FakeCandidate("safe", 0.9, tenant_id="tenant_123"),
            FakeCandidate("nested", 0.8, metadata={"tenant_id": "tenant_123"}),
            FakeCandidate("leak", 0.7, tenant_id="tenant_999"),
            FakeCandidate("missing", 0.6),
        ]
        import_module.return_value = module

        result = self.router._semantic_search("safe", "tenant_123")

        self.assertEqual(result["results"], [{"id": "safe", "score": 0.9}, {"id": "nested", "score": 0.8}])

if __name__ == "__main__":
    unittest.main()
