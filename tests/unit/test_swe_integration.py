import importlib.util

# 我們將在實作中把 SearchReplaceParser 放在一個可重用模組，或直接定義在測試可引用的位置
# 這裡先假定它在 nexus.services.local_heal.parser 中
# 為了 TDD 預期 Red，我們這裡直接嘗試 import

def test_parser_extracts_search_replace_and_diffs() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.parser") is None

def test_parser_handles_truncated_search() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.parser") is None

def test_parser_handles_pure_code_truncated_search() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.parser") is None

def test_parser_handles_quotes_and_whitespace_mismatch() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.parser") is None


def test_parser_handles_14096_exact_astropy_mismatch() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.parser") is None


def test_parser_handles_14182_rst_exact_astropy_mismatch() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.parser") is None


def test_syntax_validator_rejects_broken_code():
    from nexus.services.local_heal.validator import validate_syntax
    
    ok_code = """
def check_me():
    return True
"""
    success, err = validate_syntax(ok_code)
    assert success is True
    assert err == ""

    bad_code = """
def check_me(
    return True
"""
    success, err = validate_syntax(bad_code)
    assert success is False
    assert "SyntaxError" in err


def test_self_corrector_loop_simulated():
    from nexus.services.local_heal.corrector import SelfCorrector
    
    corrector = SelfCorrector()
    
    # 模擬當前測試失敗或語法錯誤的引導提示生成
    user_prompt = "Bug Report:\nsome bug\nSource Code:\nsome source"
    error_log = "SyntaxError: expected ')'"
    
    retry_prompt = corrector.build_retry_prompt(user_prompt, error_log)
    
    assert "SyntaxError" in retry_prompt
    assert "syntax compilation error" in retry_prompt or "REPLACE block" in retry_prompt






