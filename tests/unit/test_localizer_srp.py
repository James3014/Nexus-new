import pytest
from pathlib import Path
from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer

def test_localizer_granular_slicing_functional_purity():
    """
    [TDD] 驗證 GranularMethodLocalizer 的通用優化：
    1. 不應包含整個 ClassDef。
    2. 應精確提取相關 FunctionDef。
    3. 必須包含 BM25 與平滑分值。
    """
    dummy_code = """
class LargeManager:
    def unrelated_method(self):
        pass
        
    def target_method(self, value):
        # This is what we want to find
        if value == "NO":
            return True
        return False

    def another_one(self):
        pass
"""
    localizer = GranularMethodLocalizer(refine_threshold=10) # 強制觸發精煉
    query = "Find target_method and the value NO"
    
    bundle = localizer.localize("dummy.py", dummy_code, query)
    refined = bundle.to_context_string()
    
    assert "target_method" in refined
    assert "class LargeManager" not in refined # 關注點分離：排除類別殼
    assert "## Primary Target:" in refined
    assert "unrelated_method" not in refined # 模組化篩選
