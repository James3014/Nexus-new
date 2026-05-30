import pytest
from nexus.services.local_heal.hunk_localizer import HunkLocalizer

def test_hunk_localizer_extracts_target_function():
    code = (
        "class Helper:\n"
        "    def run(self):\n"
        "        pass\n\n"
        "def buggy_function(x):\n"
        "    # Some long function content\n"
        "    val = x + 1\n"
        "    return val\n\n"
        "def another_helper():\n"
        "    return True\n"
    )
    
    localizer = HunkLocalizer()
    problem = "Fix buggy_function calculation error"
    
    result = localizer.extract_hunks(code, problem, max_lines=5) # 強制觸發裁剪
    
    assert "buggy_function" in result
    assert "=== Target Definition: def buggy_function ===" in result
    assert "another_helper" in result # 應該作為 context_after 出現
    assert "=== Target Definition: class Helper ===" not in result # Helper 不應是 Target Def
