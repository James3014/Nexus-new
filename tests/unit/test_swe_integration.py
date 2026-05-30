import pytest
from pathlib import Path
from nexus.services.local_heal.sandbox import SandboxExecutor
from nexus.services.local_heal.evaluator import PatchTreeEvaluator

# 我們將在實作中把 SearchReplaceParser 放在一個可重用模組，或直接定義在測試可引用的位置
# 這裡先假定它在 nexus.services.local_heal.parser 中
# 為了 TDD 預期 Red，我們這裡直接嘗試 import

def test_parser_extracts_search_replace_and_diffs(tmp_path):
    from nexus.services.local_heal.parser import SearchReplaceParser
    
    file_content = """def dummy_func():
    print("hello world")
    return True
"""
    target_file = tmp_path / "dummy.py"
    target_file.write_text(file_content)

    llm_output = """FILE: dummy.py
SEARCH:
    print("hello world")
    return True
REPLACE:
    print("hello nexus")
    return False
END"""

    parser = SearchReplaceParser()
    blocks = parser.parse_blocks(llm_output)
    
    assert len(blocks) == 1
    assert blocks[0]["file"] == "dummy.py"
    assert "print(\"hello world\")" in blocks[0]["search"]
    
    # 測試套用與生成 git diff
    success, diff = parser.apply_and_diff(target_file, blocks[0]["search"], blocks[0]["replace"])
    
    assert success is True
    assert "--- a/dummy.py" in diff
    assert "+++ b/dummy.py" in diff
    assert "-    print(\"hello world\")" in diff
    assert "+    print(\"hello nexus\")" in diff

    # 驗證實體檔案是否被正確修改
    updated_content = target_file.read_text()
    assert "hello nexus" in updated_content
    assert "hello world" not in updated_content

def test_parser_handles_truncated_search(tmp_path):
    from nexus.services.local_heal.parser import SearchReplaceParser
    
    file_content = """def world_to_array_index(self, *world_objects):
    \"\"\"
    Convert world coordinates (represented by Astropy objects) to array
    indices.

    If `~astropy.wcs.wcsapi.BaseLowLevelWCS.pixel_n_dim` is ``1``, this
    method returns a single scalar or array, otherwise a tuple of scalars or
    arrays is returned. See
    `~astropy.wcs.wcsapi.BaseLowLevelWCS.world_to_array_index_values` ...
"""
    target_file = tmp_path / "dummy.py"
    target_file.write_text(file_content)

    search_text = """def world_to_array_index(self, *world_objects):
    \"\"\"
    Convert world coordinates (represented by Astropy objects) to array
    indices.

    If `~astropy.wcs.wcsapi.BaseLowLevelWCS.pixel_n_dim` is ``1``, this
    method returns a single scalar or array, otherwise a tuple of scalars or
    arrays is returned. See
    `~astropy.wcs.wc"""
    
    replace_text = """def world_to_array_index(self, *world_objects):
    # This is replaced successfully!
    pass"""
    
    parser = SearchReplaceParser()
    success, diff = parser.apply_and_diff(target_file, search_text, replace_text)
    
    assert success is True
    assert "# This is replaced successfully!" in target_file.read_text()

def test_parser_handles_pure_code_truncated_search(tmp_path):
    from nexus.services.local_heal.parser import SearchReplaceParser
    
    file_content = """def calculate_total(price, tax, discount):
    subtotal = price + tax
    total = subtotal - discount
    return total
"""
    target_file = tmp_path / "dummy.py"
    target_file.write_text(file_content)

    search_text = """def calculate_total(price, tax, discount):
    subtotal = price + tax
    total = sub"""
    
    replace_text = """def calculate_total(price, tax, discount):
    subtotal = price + tax
    total = subtotal - discount - 5
    return total"""
    
    parser = SearchReplaceParser()
    success, diff = parser.apply_and_diff(target_file, search_text, replace_text)
    
    assert success is True
    assert target_file.read_text() == """def calculate_total(price, tax, discount):
    subtotal = price + tax
    total = subtotal - discount - 5
    return total
"""



