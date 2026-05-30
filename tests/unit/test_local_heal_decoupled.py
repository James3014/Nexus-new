import pytest
from nexus.services.local_heal.parser import Normalizer, SlidingWindowMatcher, HealDecisionEngine

def test_normalizer_quotes_and_whitespace():
    norm = Normalizer()
    text = "  hello   \"world\"  and   'everyone'  "
    result = norm.normalize(text)
    # 雙引號應轉單引號，多空格應壓縮，首尾應清理
    assert result == "hello 'world' and 'everyone'"

def test_sliding_window_matcher_exact_and_fuzzy():
    matcher = SlidingWindowMatcher()
    file_content = "def test_func():\n    return 'hello world'\n"
    search_text = "def test_func():\n  return \"hello world\""
    
    # 執行歸一化滑動視窗匹配
    matched_sub, verbatim = matcher.match(file_content, search_text)
    assert matched_sub == "def test_func():\n    return 'hello world'"
    assert verbatim == matched_sub

def test_heal_decision_engine_rules():
    engine = HealDecisionEngine()
    err_syntax = "SyntaxError: invalid syntax. Perhaps you forgot a comma? at line 144"
    err_mismatch = "SEARCH block not found or verbatim mismatch"
    
    prompt_syntax = engine.get_retry_prompt("Original Prompt", err_syntax)
    assert "SyntaxError" in prompt_syntax
    assert "comma" in prompt_syntax
    
    prompt_mismatch = engine.get_retry_prompt("Original Prompt", err_mismatch)
    assert "verbatim mismatch" in prompt_mismatch
