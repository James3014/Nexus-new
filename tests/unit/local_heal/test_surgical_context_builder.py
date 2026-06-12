import pytest
from pathlib import Path
from nexus.services.local_heal.surgical_context import SurgicalContextBuilder

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
    # window_size=3，我們搜尋 "target_func"
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
        plan={"search_symbols": ["target_func"]}
    )
    
    # 12 是第 13 行 (1-indexed)。
    # 預計 Anchor 是 12。
    # 區間為 [12 - 3, 12 + 3] -> [9, 15] -> lines 10 to 16.
    assert "  10 | line 10" in res
    assert "  13 | def target_func():" in res
    assert "  16 | line 16" in res
    assert "line 5" not in res
    assert "line 18" not in res
    assert "truncated" in res

def test_surgical_context_crop_by_retry_fuzzy_matching(tmp_path):
    # 檔案有 30 行，大於 max_context_lines=10。
    # 重試 SEARCH_MISMATCH，且 user_prompt 中有之前的 SEARCH 區塊。
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
    
    # Anchor 應該定位在 index 18 (第 19 行)。
    # 區間為 [18 - 3, 18 + 3] -> [15, 21] -> lines 16 to 22
    assert "  16 | line 16" in res
    assert "  19 |     if value == 42:" in res
    assert "  22 | line 22" in res
    assert "line 10" not in res
    assert "line 26" not in res
