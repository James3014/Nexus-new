import pytest
from pathlib import Path
from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer

def test_extract_paths_from_traceback():
    localizer = GranularMethodLocalizer()
    text = """
    Traceback (most recent call last):
      File "sympy/core/mul.py", line 465, in flatten
        if o12.is_commutative:
    AttributeError: 'NoneType' object has no attribute 'is_commutative'
    """
    paths = localizer._extract_paths_from_issue(text)
    assert "sympy/core/mul.py" in paths

def test_rank_files_with_explicit_tb_path(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    # 建立目標檔案
    target_file = repo_dir / "sympy" / "core" / "mul.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("class Mul: pass")
    
    localizer = GranularMethodLocalizer()
    
    # 模擬包含 Traceback 的查詢
    query = """
    Evidence:
      File "sympy/core/mul.py", line 465, in flatten
    """
    
    ranked = localizer.rank_files(query, repo_dir)
    assert len(ranked) >= 1
    assert ranked[0][1]["path"] == "sympy/core/mul.py"

def test_localize_with_line_number_bonus():
    # 建立大於 5000 字元的內容以觸發精煉邏輯
    padding = "# " + "x" * 100 + "\n"
    content = (padding * 60) + """
class Target:
    def good_func(self):
        print("hit")
        # Target line is here
        
    def bad_func(self):
        print("miss")
"""
    localizer = GranularMethodLocalizer()
    # 假設 good_func 在第 62 行左右
    query = "Evidence: ... line 63 ..."
    bundle = localizer.localize("test.py", content, query)
    
    # 驗證 good_func 被選中
    assert "good_func" in bundle.primary_snippet
    assert "bad_func" not in bundle.primary_snippet
    assert "Surgical slice based on score" in bundle.slice_reason
