import pytest
from pathlib import Path
import io
import sys
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

def test_artifact_exclusion(tmp_path):
    repo_dir = tmp_path / "repo_artifact"
    repo_dir.mkdir()
    
    # 建立一個包含符號但應該被排除的檔案
    repro_file = repo_dir / "reproduce_bug.py"
    repro_file.write_text("class TargetSymbol: pass")
    
    # 建立一個真正的源碼檔案
    src_file = repo_dir / "real_code.py"
    src_file.write_text("class TargetSymbol: pass")
    
    localizer = GranularMethodLocalizer()
    ranked = localizer.rank_files("Issue with TargetSymbol", repo_dir, search_symbols=["TargetSymbol"])
    
    paths = [doc["path"] for _, doc in ranked]
    assert "real_code.py" in paths
    assert "reproduce_bug.py" not in paths

def test_definition_boost(tmp_path):
    repo_dir = tmp_path / "repo_boost"
    repo_dir.mkdir()
    
    # Client 檔案：包含多次引用但非定義
    client_file = repo_dir / "client.py"
    client_file.write_text("import target; x = target.TargetClass(); y = target.TargetClass()")
    
    # Definition 檔案：包含定義
    def_file = repo_dir / "target.py"
    def_file.write_text("class TargetClass: pass")
    
    localizer = GranularMethodLocalizer()
    ranked = localizer.rank_files("Where is TargetClass?", repo_dir, search_symbols=["TargetClass"])
    
    # target.py 應該因為 Definition Boost 而排在 client.py 前面
    assert ranked[0][1]["path"] == "target.py"

def test_no_stdout_print(tmp_path, capsys):
    repo_dir = tmp_path / "repo_silent"
    repo_dir.mkdir()
    (repo_dir / "x.py").write_text("pass")
    
    localizer = GranularMethodLocalizer()
    localizer.rank_files("query", repo_dir)
    
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
