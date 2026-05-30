import pytest
from pathlib import Path
from nexus.services.local_heal.localizer import Localizer

def test_rank_files_returns_max_3_files(tmp_path):
    # 建立一個 mock repository
    (tmp_path / "foo.py").write_text("def my_func():\n    return 'hello'", encoding="utf-8")
    (tmp_path / "bar.py").write_text("def my_other_func():\n    return 'world'", encoding="utf-8")
    (tmp_path / "baz.py").write_text("class MyClass:\n    pass", encoding="utf-8")
    (tmp_path / "qux.py").write_text("def unrelated():\n    pass", encoding="utf-8")
    
    localizer = Localizer()
    ranked = localizer.rank_files("my_func class MyClass", tmp_path, max_files=2)
    
    # 應該只回傳 2 個檔案，且核心檔案 (foo.py 與 baz.py) 應該在其中
    assert len(ranked) == 2
    paths = [doc["path"] for _, doc in ranked]
    assert "foo.py" in paths
    assert "baz.py" in paths
    assert "qux.py" not in paths


def test_extract_relevant_code_formats_correctly(tmp_path):
    file_path = tmp_path / "large.py"
    # 超過 6000 字元
    content = "def test():\n" + "    print('hello')\n" * 500
    file_path.write_text(content, encoding="utf-8")
    
    localizer = Localizer()
    scored_files = [(100.0, {
        "path": "large.py",
        "content": content,
        "file_path": file_path
    })]
    
    extracted = localizer.extract_relevant_code(scored_files)
    
    assert len(extracted) == 1
    path, formatted_content = extracted[0]
    assert path == "large.py"
    assert "... [truncated]" in formatted_content
    assert len(formatted_content) <= 6100
