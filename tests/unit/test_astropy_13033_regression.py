import pytest
from pathlib import Path
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.matcher import MatchChain

def test_astropy_13033_mismatch_drift_repro():
    """
    重現 astropy-13033 的 Mismatch 漂移案例。
    模型產出的 SEARCH 區塊與實際代碼有微小差異。
    """
    file_content = """
class SampledTimeSeries:
    def _check_required_columns(self):
        if self._required_columns is not None:
            if not self._required_columns_relax and len(self.colnames) == 0:
                raise ValueError("{} object is invalid - expected '{}' "
                                 "as the first column{} but time series has no columns".format(
                                     self.__class__.__name__, self._required_columns[0], 
                                     's' if len(self._required_columns) > 1 else ''))
            
            # 這是漂移目標 (TypeError)
            if self._time_column is not None and self._time_start_column is not None:
                raise TypeError("Cannot specify both 'time' and 'time_start'")
"""
    
    # 模擬模型產生的錯誤 SEARCH (Attempt 1)
    # 這裡刻意寫錯以觸發 Mismatch
    search_text = "raise ValueError(\"TimeSeries object is invalid - expected 'time' as the first columns but found 'time'\")"
    replace_text = "raise ValueError(\"Required column 'time' is missing\")"
    
    patcher = Patcher()
    result = patcher.apply_patch(file_content, search_text, replace_text)
    
    # 目前預期會失敗 (Verbatim Mismatch)
    assert result.success is False
    assert "SEARCH block not found" in result.error_message

def test_astropy_13033_mismatch_feedback_drift_fixed():
    """
    驗證修復後的 Matcher：當提供 context_hints 時，應優先選擇正確的函數區域。
    """
    from nexus.services.local_heal.closest_snippet import find_closest_snippet
    
    file_content = """
    def func_a(self):
        # 這是目標區域
        raise ValueError("Target string with small difference")
        
    def func_b(self):
        # 這是容易誤導的區域
        raise TypeError("Cannot specify both 'time' and 'time_start'")
"""
    # 模型想改 func_a，但文字寫錯了
    bad_search = "raise ValueError(\"Target string with Large difference\")"
    
    # 案例 1: 無提示 (可能會漂移，取決於相似度算分)
    # 案例 2: 有提示 (應鎖定 func_a 內部的內容)
    closest_with_hint = find_closest_snippet(file_content, bad_search, context_hints=["func_a"])
    
    print(f"DEBUG: Closest with hint: {closest_with_hint}")
    assert "ValueError" in closest_with_hint
    assert "TypeError" not in closest_with_hint

def test_astropy_13033_semantic_penalty():
    """
    驗證語義懲罰機制：不應跨越異常類型。
    """
    from nexus.services.local_heal.closest_snippet import find_closest_snippet
    
    file_content = """
    raise ValueError("Something went wrong")
    raise TypeError("Something went wrong")
"""
    # 模型明確寫了 ValueError，即使內容不全等，也不應匹配到 TypeError
    bad_search = "raise ValueError(\"Something went wrong indeed\")"
    
    closest = find_closest_snippet(file_content, bad_search)
    
    assert "ValueError" in closest
    assert "TypeError" not in closest
