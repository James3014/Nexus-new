import pytest
import difflib
from nexus.services.local_heal.matcher import (
    MatchChain, ASTSemanticMatch, ExactMatch, StrippedMatch, DiffLibFuzzyMatcher
)
from nexus.services.local_heal.closest_snippet import find_closest_snippet

def test_ast_semantic_match():
    matcher = ASTSemanticMatch()
    file_content = "def test_func():\n    if True:\n        print('hello')\n"
    # 引號、換行和空格有差異，但 AST 語意完全一致
    search_text = "def test_func():\n  if True:\n    print(\"hello\")"
    
    res = matcher.match(file_content, search_text)
    assert res is not None
    assert res.strategy_name == "ASTSemanticMatch"
    assert "print('hello')" in res.verbatim_text

def test_match_chain_fallback_flow():
    chain = MatchChain()
    file_content = "x = 42\ny = 100\n"
    
    # level 1 ExactMatch
    res1 = chain.find_match(file_content, "x = 42")
    assert res1 is not None
    assert res1.strategy_name == "ExactMatch"
    
    # level 3 NormalizedMatch
    res3 = chain.find_match(file_content, "  y   =   100  ")
    assert res3 is not None
    assert res3.strategy_name == "NormalizedMatch"

# P0: closest_snippet finder
def test_closest_snippet_finder_returns_actual_nearest():
    file_content = "x = 1\ny = 2\ndef foo():\n    return x + y\n"
    search_text = "def foo():\n    return x + y"  # exact exists
    result = find_closest_snippet(file_content, search_text)
    assert "def foo" in result

# P1: ExactMatch without trailing newline
def test_exact_match_no_trailing_newline_still_works():
    matcher = ExactMatch()
    file_content = "def foo():\n    return 42\n"
    search_text = "return 42"  # no trailing \n
    res = matcher.match(file_content, search_text)
    assert res is not None

# P2: DiffLibFuzzyMatcher
def test_difflib_fuzzy_matcher_whitespace_drift():
    matcher = DiffLibFuzzyMatcher()
    file_content = "def foo():\n    x = 1\n    return x\n"
    search_text = "def foo():\n  x = 1\n  return x"  # indent drift
    res = matcher.match(file_content, search_text)
    assert res is not None
    assert "def foo" in res.verbatim_text

def test_closest_snippet_finder_ratio_threshold():
    file_content = "x = 1\ny = 2\ndef foo():\n    return x + y\n"
    search_text = "def bar_completely_different():\n    pass"
    result = find_closest_snippet(file_content, search_text)
    assert result == ""

