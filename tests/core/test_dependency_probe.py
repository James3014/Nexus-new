import pytest
from pathlib import Path
from nexus.core.dependency_probe import DependencyProbe

def test_dependency_probe_skips_restricted_dirs(tmp_path):
    # Setup: 模擬工作區結構
    workspace = tmp_path / "nexus"
    workspace.mkdir()
    
    # 一般檔案
    (workspace / "nexus").mkdir()
    (workspace / "nexus" / "core.py").write_text("import os", encoding="utf-8")
    
    # 應排除的目錄
    (workspace / ".worktrees").mkdir()
    (workspace / ".worktrees" / "leak.py").write_text("import bad_syntax (", encoding="utf-8") # 語法錯誤
    
    (workspace / "SWE-bench").mkdir()
    (workspace / "SWE-bench" / "eval.py").write_text("def f():\n  finally:\n    return 1", encoding="utf-8") # return in finally
    
    (workspace / ".venv").mkdir()
    (workspace / ".venv" / "lib.py").write_text("import sys", encoding="utf-8")
    
    # 初始化探針
    probe = DependencyProbe(str(workspace))
    probe.build_index()
    
    # 驗證：只有核心檔案被索引，排除清單內的檔案均不應出現在索引中
    indexed_files = list(probe._index.keys())
    
    assert "nexus/core.py" in indexed_files
    assert ".worktrees/leak.py" not in indexed_files
    assert "SWE-bench/eval.py" not in indexed_files
    assert ".venv/lib.py" not in indexed_files
    
    # 確認 _should_skip 直接邏輯
    assert probe._should_skip(workspace / ".worktrees" / "any.py") is True
    assert probe._should_skip(workspace / "SWE-bench" / "any.py") is True
    assert probe._should_skip(workspace / "nexus" / "any.py") is False

def test_dependency_probe_extract_imports_handles_exception(tmp_path):
    # 測試即使檔案損壞，探針也能優雅處理（雖然 _should_skip 已經過濾了大多數）
    workspace = tmp_path / "broken"
    workspace.mkdir()
    broken_file = workspace / "error.py"
    broken_file.write_text("invalid python code", encoding="utf-8")
    
    probe = DependencyProbe(str(workspace))
    imports = probe._extract_imports(broken_file)
    assert imports == [] # 應回傳空清單而非崩潰
