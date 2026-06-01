import pytest
from nexus.services.local_heal.patcher import Patcher

def test_patcher_exact_match():
    patcher = Patcher()
    file_content = "def hello():\n    print('world')\n    return True\n"
    search = "    print('world')"
    replace = "    print('nexus')\n    print('universe')"
    
    res = patcher.apply_patch(file_content, search, replace)
    assert res.success is True
    assert "print('nexus')" in res.new_content
    assert "print('world')" not in res.new_content
    assert res.diff.startswith("--- a/file\n+++ b/file")

def test_patcher_truncated_match():
    patcher = Patcher()
    file_content = "def test():\n    val = 123\n    if val:\n        return True\n"
    # 最後一行 truncated
    search = "    val = 123\n    if val:\n        ret"
    replace = "    val = 123\n    if val:\n        return False"
    
    res = patcher.apply_patch(file_content, search, replace)
    assert res.success is True
    assert "return False" in res.new_content
    assert "return True" not in res.new_content

def test_patcher_normalized_match():
    patcher = Patcher()
    file_content = "def run():\n    return \"result\"\n"
    # 僅引號與微小空白變更 (相似度應 > 0.85)
    search = "    return 'result' "
    replace = "    return 'success'"
    
    res = patcher.apply_patch(file_content, search, replace)
    assert res.success is True
    assert "return 'success'" in res.new_content
    assert "result" not in res.new_content
