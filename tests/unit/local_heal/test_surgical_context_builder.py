import pytest
from pathlib import Path
from nexus.services.local_heal.surgical_context import SurgicalContextBuilder
from nexus.services.local_heal.interface import RepairPlan

def test_surgical_context_no_crop_for_small_file(tmp_path):
    builder = SurgicalContextBuilder(max_context_lines=10, window_size=5)
    source_text = "line 1\nline 2\nline 3\n"
    
    # 檔案只有 3 行，小於 max_context_lines=10，應該直接全部輸出（加上行號）
    res = builder.build_annotated_context(
        repo_dir=tmp_path,
        rel_path="foo.py",
        source_text=source_text,
        attempt=1,
        failure_reason="",
        plan={}
    )
    
    assert "   1 | line 1" in res
    assert "   2 | line 2" in res
    assert "   3 | line 3" in res
    assert "[truncated]" not in res

def test_surgical_context_crop_by_search_symbols(tmp_path):
    # 檔案有 20 行，大於 max_context_lines=10。
    # _dynamic_window(20, 12) = min(30, 20//2) = 10
    # window_size=3 is overridden by _dynamic_window for small files
    lines = [f"line {i}" for i in range(1, 21)]
    lines[12] = "def target_func():"
    source_text = "\n".join(lines)
    
    builder = SurgicalContextBuilder(max_context_lines=10, window_size=3)
    res = builder.build_annotated_context(
        repo_dir=tmp_path,
        rel_path="foo.py",
        source_text=source_text,
        attempt=1,
        failure_reason="",
        plan=RepairPlan(search_symbols=["target_func"], repair_strategy="fix")
    )
    
    # anchor at index 12, window=10, range [2, 20] -> lines 3 to 20
    assert "   3 | line 3" in res
    assert "  13 | def target_func():" in res
    assert "  20 | line 20" in res
    assert "   1 | line 1" not in res
    assert "truncated" in res

def test_surgical_context_crop_by_retry_fuzzy_matching(tmp_path):
    # 檔案有 30 行，大於 max_context_lines=10。
    # _dynamic_window(30, 18) = min(30, 30//2) = 15
    # window_size=3 is overridden by _dynamic_window for small files
    lines = [f"line {i}" for i in range(1, 31)]
    lines[18] = "    if value == 42:"
    lines[19] = "        return True"
    source_text = "\n".join(lines)
    
    builder = SurgicalContextBuilder(max_context_lines=10, window_size=3)
    
    # 模擬之前的 user_prompt，包含 SEARCH 區塊，但其中的 SEARCH 區塊跟原始程式碼有些微差異（比如縮進或拼寫，這裡模擬極為相似的 SEARCH block）
    user_prompt = (
        "Some details...\n"
        "<<<<<<< SEARCH\n"
        "    if val == 42:\n"  # 故意寫錯成 val，測試 fuzzy 匹配
        "        return True\n"
        "=======\n"
        "    if val == 42:\n"
        "        return False\n"
        ">>>>>>> REPLACE\n"
    )
    
    res = builder.build_annotated_context(
        repo_dir=tmp_path,
        rel_path="foo.py",
        source_text=source_text,
        attempt=2,
        failure_reason="SEARCH_MISMATCH",
        plan={},
        user_prompt=user_prompt
    )
    
    # anchor at index 18, window=15, range [3, 30] -> lines 4 to 30
    assert "   4 | line 4" in res
    assert "  19 |     if value == 42:" in res
    assert "  30 | line 30" in res
    assert "   1 | line 1" not in res
    assert "truncated" in res
